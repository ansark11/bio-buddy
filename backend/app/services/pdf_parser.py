import asyncio
import json
import logging
import re
from io import BytesIO

import pdfplumber
from groq import Groq

from app.config import settings
from app.models.health_metrics import BloodTestExtraction, ExtractedBiomarker
from app.services.groq_utils import groq_call_with_retry

logger = logging.getLogger(__name__)

BIOMARKER_ALIASES = """
Common biomarker name standardizations (use these standardized_name values):
- LDL-C, LDL Cholesterol, Low-Density Lipoprotein, LDL → ldl_cholesterol
- HDL-C, HDL Cholesterol, High-Density Lipoprotein, HDL → hdl_cholesterol
- Total Cholesterol, Cholesterol Total → total_cholesterol
- Triglycerides, TG, TRIG → triglycerides
- HbA1c, Hemoglobin A1c, Glycated Hemoglobin, A1C → hba1c
- Fasting Glucose, Glucose, Blood Glucose, FBG → fasting_glucose
- TSH, Thyroid Stimulating Hormone → tsh
- Free T4, FT4, Free Thyroxine → free_t4
- Free T3, FT3, Free Triiodothyronine → free_t3
- 25-OH Vitamin D, Vitamin D 25-Hydroxy, 25(OH)D, Vitamin D → vitamin_d
- Vitamin B12, Cobalamin, B12 → vitamin_b12
- Folate, Folic Acid, Serum Folate → folate
- Iron, Serum Iron, Fe → iron
- Ferritin, Serum Ferritin → ferritin
- TIBC, Total Iron Binding Capacity → tibc
- Transferrin, Serum Transferrin → transferrin
- Transferrin Saturation, % Saturation, Transferrin Sat → transferrin_saturation
- RDW, Red Cell Distribution Width, RDW-CV → rdw
- Hemoglobin, Hgb, Hb → hemoglobin
- Hematocrit, Hct → hematocrit
- RBC, Red Blood Cell Count, Erythrocytes → rbc_count
- WBC, White Blood Cell Count, Leukocytes → wbc_count
- Platelets, PLT, Platelet Count → platelet_count
- MCV, Mean Corpuscular Volume → mcv
- MCH, Mean Corpuscular Hemoglobin → mch
- MCHC, Mean Corpuscular Hemoglobin Concentration → mchc
- Neutrophils, Neutrophil Count → neutrophils
- Lymphocytes, Lymphocyte Count → lymphocytes
- Monocytes, Monocyte Count → monocytes
- Eosinophils, Eosinophil Count → eosinophils
- Basophils, Basophil Count → basophils
- Creatinine, Serum Creatinine → creatinine
- eGFR, Estimated GFR, Glomerular Filtration Rate → egfr
- BUN, Blood Urea Nitrogen, Urea → bun
- ALT, Alanine Aminotransferase, SGPT → alt
- AST, Aspartate Aminotransferase, SGOT → ast
- ALP, Alkaline Phosphatase → alp
- GGT, Gamma-Glutamyl Transferase → ggt
- Total Bilirubin, Bilirubin Total → total_bilirubin
- Albumin, Serum Albumin → albumin
- Total Protein, Serum Protein → total_protein
- Sodium, Na → sodium
- Potassium, K → potassium
- Chloride, Cl → chloride
- Bicarbonate, CO2, HCO3 → bicarbonate
- Calcium, Ca → calcium
- Magnesium, Mg → magnesium
- Phosphorus, Phosphate, PO4 → phosphorus
- Uric Acid, Urate → uric_acid
- CRP, C-Reactive Protein, hsCRP, hs-CRP → crp
- ESR, Erythrocyte Sedimentation Rate → esr
- Testosterone, Total Testosterone → testosterone
- Free Testosterone → free_testosterone
- SHBG, Sex Hormone Binding Globulin → shbg
- Cortisol, AM Cortisol, Serum Cortisol → cortisol
- Insulin, Fasting Insulin → insulin
- HOMA-IR → homa_ir
- PSA, Prostate-Specific Antigen → psa
- Amylase, Serum Amylase, Pancreatic Amylase → amylase
- Lipase, Serum Lipase → lipase
- Non HDL Cholesterol, Non-HDL Cholesterol, Non-HDL-C → non_hdl_cholesterol
- Cholesterol/HDL Ratio, Total Cholesterol/HDL, Chol/HDL → cholesterol_hdl_ratio
- Hemoglobin A1C/Total Hemoglobin → hba1c
"""

EXTRACTION_PROMPT = f"""
You are a medical data extraction assistant. Extract all biomarker results from the following blood test report text.

{BIOMARKER_ALIASES}

Return ONLY valid JSON in exactly this format (no markdown, no explanation):
{{
  "lab_name": "string or null",
  "test_date": "YYYY-MM-DD or null",
  "patient_name": "string or null",
  "biomarkers": [
    {{
      "name": "original name from report",
      "standardized_name": "snake_case standardized name from the list above, or make a reasonable snake_case name if not listed",
      "value": 0.0,
      "unit": "string",
      "reference_range_low": 0.0 or null,
      "reference_range_high": 0.0 or null,
      "flag": "normal" or "high" or "low" or null,
      "reference_range_notes": "string or null"
    }}
  ],
  "notes": "any doctor notes, comments, or free text from the report"
}}

Rules:
- Extract every numeric test result you can find
- Reference range formats — handle ALL of these:
  * "3.5 - 5.0" or "3.5-5.0" → reference_range_low=3.5, reference_range_high=5.0
  * ">=1.00" or "=>1.00" or ">= 1.00" → reference_range_low=1.00, reference_range_high=null
  * ">220" → reference_range_low=220, reference_range_high=null
  * "<5.0" or "<=5.0" → reference_range_low=null, reference_range_high=5.0
  * "See below" or blank — scan the surrounding descriptive text for an embedded numeric threshold (e.g. "=>60 mL/min/1.73m2" means reference_range_low=60); extract what you can, leave null if none found
  * Descriptive tier text (e.g. "30-50 ug/L: Probable iron deficiency, 51-100 ug/L: Possible...") — use the lowest tier boundary that indicates "unlikely deficiency/abnormality" as reference_range_low, and leave reference_range_high=null
- Flag detection — check ALL of the following, in priority order:
  1. Explicit flag column value: "HI" or "H" → flag="high"; "LO" or "L" → flag="low"
  2. Symbols adjacent to the value: ↑ or H → flag="high"; ↓ or L → flag="low"
  3. Asterisk (*) adjacent to or following the value (common on Quest/LabCorp) → value is abnormal; set flag based on whether it exceeds the high or low bound
  4. If no explicit flag but value is outside the extracted reference range → set flag accordingly
  5. Otherwise → flag="normal"
- reference_range_notes: capture any tiered thresholds, clinical guideline text, methodology caveats, or
  context-dependent ranges printed alongside this specific biomarker. Condense to one concise string. Examples:
  * Ferritin → "30-50 ug/L: Probable iron deficiency; 51-100: Possible if risk factors present; 101-300: Unlikely; >=600: Consider overload. Inflammation affects interpretation."
  * HbA1c → "Diabetes Canada 2018: <5.5% Normal, 5.5-5.9% At risk, 6.0-6.4% Prediabetes, >=6.5% Diabetes. Monitoring target: <=7.0%"
  * Triglyceride → "Non-fasting sample (2 hours after meal). Fasting reference: <1.70, Non-fasting: <2.00 mmol/L"
  * CRP → ">=2.0 mg/L is a cardiovascular disease risk-enhancing factor (AHA/ACC 2019)"
  * Vitamin B12 → ">220 pmol/L: Normal; 150-220: Borderline; <150: Deficiency"
  * eGFR → "Reference: >=60 mL/min/1.73m2. Rules out CKD stage 3-5. Calculated using CKD-EPI 2021 (no race-based adjustment)."
  * Leave null if no supplementary interpretation text exists for this biomarker.
- If you cannot determine the date, set test_date to null
- value must be a number, never a string

BLOOD TEST REPORT TEXT:
"""

BIOMARKER_PANELS = {
    "lipids": ["ldl_cholesterol", "hdl_cholesterol", "total_cholesterol", "triglycerides", "non_hdl_cholesterol", "cholesterol_hdl_ratio"],
    "thyroid": ["tsh", "free_t4", "free_t3"],
    "vitamins_minerals": ["vitamin_d", "vitamin_b12", "folate", "iron", "ferritin", "tibc", "transferrin", "transferrin_saturation", "magnesium", "calcium", "phosphorus"],
    "cbc": ["hemoglobin", "hematocrit", "rbc_count", "wbc_count", "platelet_count", "mcv", "mch", "mchc", "rdw", "neutrophils", "lymphocytes", "monocytes", "eosinophils", "basophils"],
    "metabolic": ["fasting_glucose", "hba1c", "insulin", "homa_ir", "creatinine", "egfr", "bun", "sodium", "potassium", "chloride", "bicarbonate", "uric_acid", "amylase", "lipase"],
    "liver": ["alt", "ast", "alp", "ggt", "total_bilirubin", "albumin", "total_protein"],
    "hormones": ["testosterone", "free_testosterone", "shbg", "cortisol", "psa"],
    "inflammation": ["crp", "esr"],
}


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    pages = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True)
            if text:
                pages.append(text)
    full_text = "\n".join(pages)
    logger.info(f"Extracted {len(full_text)} chars from PDF ({len(pages)} pages)")
    return full_text


def _correct_flags(biomarkers: list[ExtractedBiomarker]) -> list[ExtractedBiomarker]:
    """Override LLM flag with numeric comparison when a reference range is available."""
    corrected = []
    for b in biomarkers:
        low, high = b.reference_range_low, b.reference_range_high
        if low is not None and b.value < low:
            flag = "low"
        elif high is not None and b.value > high:
            flag = "high"
        elif low is not None or high is not None:
            flag = "normal"
        else:
            flag = b.flag  # no reference range — trust the LLM
        corrected.append(b.model_copy(update={"flag": flag}))
    return corrected


async def extract_biomarkers_with_llm(raw_text: str) -> BloodTestExtraction:
    logger.info(f"Sending {len(raw_text)} chars of PDF text to llama-3.3-70b-versatile for extraction")

    def _call():
        client = Groq(api_key=settings.groq_api_key)
        return groq_call_with_retry(
            lambda: client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": EXTRACTION_PROMPT + raw_text}],
                response_format={"type": "json_object"},
                temperature=0,
            )
        ).choices[0].message.content

    text = await asyncio.get_event_loop().run_in_executor(None, _call)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    logger.info(f"llama-3.3-70b-versatile extraction response (first 300 chars): {text[:300]}")
    data = json.loads(text)
    biomarkers = [ExtractedBiomarker.from_llm_dict(b) for b in data.get("biomarkers", [])]
    biomarkers = _correct_flags(biomarkers)
    return BloodTestExtraction(
        lab_name=data.get("lab_name"),
        test_date=data.get("test_date"),
        patient_name=data.get("patient_name"),
        biomarkers=biomarkers,
        notes=data.get("notes"),
    )


def generate_blood_test_summary(extracted: BloodTestExtraction) -> list[str]:
    summaries = []
    lab = extracted.lab_name or "Unknown Lab"
    date_str = extracted.test_date or "unknown date"
    biomarkers = extracted.biomarkers

    # Overall summary
    total = len(biomarkers)
    flagged = [b for b in biomarkers if b.flag in ("high", "low")]
    flag_lines = []
    for b in flagged:
        direction = "high" if b.flag == "high" else "low"
        ref_low = b.reference_range_low
        ref_high = b.reference_range_high
        ref_str = ""
        if ref_low is not None and ref_high is not None:
            ref_str = f" (reference range {ref_low}–{ref_high})"
        elif ref_high is not None:
            ref_str = f" (reference range <{ref_high})"
        flag_lines.append(f"{b.name} was {b.value} {b.unit} ({direction}{ref_str})")

    overall = (
        f"Blood test from {lab} on {date_str}. "
        f"{total} biomarker{'s' if total != 1 else ''} measured. "
    )
    if flagged:
        overall += f"{len(flagged)} value{'s' if len(flagged) != 1 else ''} flagged: " + "; ".join(flag_lines) + ". "
    else:
        overall += "All values within normal range."

    if extracted.notes:
        overall += f" Notes: {extracted.notes}"

    summaries.append(overall)

    # Build lookup for quick panel assignment
    biomarker_map: dict[str, ExtractedBiomarker] = {b.standardized_name: b for b in biomarkers}
    assigned: set[str] = set()

    for panel_name, panel_keys in BIOMARKER_PANELS.items():
        panel_members = [biomarker_map[k] for k in panel_keys if k in biomarker_map]
        if not panel_members:
            continue

        lines = [f"{panel_name.replace('_', ' ').title()} panel — {lab}, {date_str}."]
        for b in panel_members:
            ref_low = b.reference_range_low
            ref_high = b.reference_range_high
            if ref_low is not None and ref_high is not None:
                ref_str = f"reference range {ref_low}–{ref_high}"
            elif ref_high is not None:
                ref_str = f"reference range <{ref_high}"
            else:
                ref_str = "no reference range"

            flag_str = b.flag or "unknown"
            note_str = f" Context: {b.reference_range_notes}" if b.reference_range_notes else ""
            lines.append(
                f"{b.name}: {b.value} {b.unit} — {ref_str}, {flag_str}.{note_str}"
            )

        summaries.append("\n".join(lines))
        for b in panel_members:
            assigned.add(b.standardized_name)

    # Unassigned biomarkers get their own chunk
    unassigned = [b for b in biomarkers if b.standardized_name not in assigned]
    if unassigned:
        lines = [f"Other results — {lab}, {date_str}."]
        for b in unassigned:
            ref_low = b.reference_range_low
            ref_high = b.reference_range_high
            if ref_low is not None and ref_high is not None:
                ref_str = f"reference range {ref_low}–{ref_high}"
            elif ref_high is not None:
                ref_str = f"reference range <{ref_high}"
            else:
                ref_str = "no reference range"
            flag_str = b.flag or "unknown"
            lines.append(f"{b.name}: {b.value} {b.unit} — {ref_str}, {flag_str}.")
        summaries.append("\n".join(lines))

    return summaries


def generate_biomarker_chunks(extracted: BloodTestExtraction) -> list[str]:
    """One focused chunk per biomarker for high-precision semantic retrieval."""
    lab = extracted.lab_name or "Unknown Lab"
    date_str = extracted.test_date or "unknown date"
    chunks = []
    for b in extracted.biomarkers:
        ref_low, ref_high = b.reference_range_low, b.reference_range_high
        if ref_low is not None and ref_high is not None:
            range_str = f"Reference range: {ref_low}–{ref_high}."
        elif ref_high is not None:
            range_str = f"Reference range: <{ref_high}."
        elif ref_low is not None:
            range_str = f"Reference range: >={ref_low}."
        else:
            range_str = "No reference range."
        flag_str = b.flag or "unknown"
        notes_str = f" Context: {b.reference_range_notes}" if b.reference_range_notes else ""
        chunks.append(
            f"{b.name} ({b.standardized_name}): {b.value} {b.unit} — {flag_str}. "
            f"{range_str} Blood test on {date_str} by {lab}.{notes_str}"
        )
    return chunks


async def parse_blood_test_pdf(pdf_bytes: bytes) -> tuple[BloodTestExtraction, list[str]]:
    raw_text = extract_text_from_pdf(pdf_bytes)
    if len(raw_text.strip()) < 50:
        raise ValueError(
            "PDF appears to contain no extractable text. It may be a scanned or image-based PDF. "
            "Please upload a text-based PDF."
        )
    extraction = await extract_biomarkers_with_llm(raw_text)
    summaries = generate_blood_test_summary(extraction)
    return extraction, summaries
