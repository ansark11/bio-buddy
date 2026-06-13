from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel
from enum import Enum


class DataSource(str, Enum):
    blood_test = "blood_test"
    apple_health = "apple_health"
    lose_it = "lose_it"
    manual = "manual"


class MetricCategory(str, Enum):
    biomarker = "biomarker"
    body_composition = "body_composition"
    cardiovascular = "cardiovascular"
    sleep = "sleep"
    nutrition = "nutrition"
    activity = "activity"
    subjective = "subjective"
    supplement = "supplement"


class HealthMetricCreate(BaseModel):
    metric_name: str
    metric_value: float
    unit: str
    category: MetricCategory
    recorded_at: datetime
    source: DataSource = DataSource.manual
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    metadata: dict = {}


class SupplementLogCreate(BaseModel):
    supplement_name: str
    dosage: Optional[str] = None
    taken: bool = True
    recorded_at: date
    notes: Optional[str] = None


class ExtractedBiomarker(BaseModel):
    name: str
    standardized_name: str
    value: float
    unit: Optional[str] = ""
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    flag: Optional[str] = None
    reference_range_notes: Optional[str] = None

    @classmethod
    def from_llm_dict(cls, d: dict) -> "ExtractedBiomarker":
        """Normalize LLM output field name variations before validation."""
        d = dict(d)
        if "name" not in d:
            d["name"] = d.pop("original_name", d.pop("biomarker_name", d.pop("test_name", "")))
        if "standardized_name" not in d:
            d["standardized_name"] = d["name"].lower().replace(" ", "_").replace("-", "_")
        if not d.get("flag"):
            d["flag"] = None
        return cls(**d)


class BloodTestExtraction(BaseModel):
    lab_name: Optional[str] = None
    test_date: Optional[str] = None
    patient_name: Optional[str] = None
    biomarkers: list[ExtractedBiomarker] = []
    notes: Optional[str] = None
