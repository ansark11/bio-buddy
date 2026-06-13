from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Maps normalised CSV header → (metric_name, unit)
_COLUMN_MAP: dict[str, tuple[str, str]] = {
    "calories": ("daily_calories", "cal"),
    "fat (g)": ("daily_fat_g", "g"),
    "protein (g)": ("daily_protein_g", "g"),
    "carbohydrates (g)": ("daily_carbs_g", "g"),
    "saturated fat (g)": ("daily_saturated_fat_g", "g"),
    "sugars (g)": ("daily_sugars_g", "g"),
    "fiber (g)": ("daily_fiber_g", "g"),
    "cholesterol (mg)": ("daily_cholesterol_mg", "mg"),
    "sodium (mg)": ("daily_sodium_mg", "mg"),
}

_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y")


def _parse_date(raw: str) -> datetime | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _safe_float(val: str) -> float | None:
    try:
        return float(val.strip())
    except (ValueError, AttributeError):
        return None


def _format_date_label(dt: datetime) -> str:
    return dt.strftime("%B %-d, %Y")


def parse_nutrition_csv(file_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Parse a Lose It food log CSV (one row per food item) into daily totals.

    Returns (metric_rows, text_chunks).
    metric_rows go into health_metrics (one row per nutrient per day).
    text_chunks are natural-language summaries for RAG embedding (one per day).
    """
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("Could not decode CSV file")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")

    # Build a normalised header → original header map
    norm_to_orig: dict[str, str] = {
        h.strip().lower(): h for h in reader.fieldnames if h
    }

    # Aggregate nutrient totals per date. Key: "YYYY-MM-DD", value: metric_name → running total
    daily_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    date_objects: dict[str, datetime] = {}

    deleted_col = norm_to_orig.get("deleted")

    for row in reader:
        # Skip soft-deleted entries
        if deleted_col and _safe_float(row.get(deleted_col, "0") or "0") == 1:
            continue

        date_raw = row.get("Date", "").strip()
        if not date_raw:
            continue

        dt = _parse_date(date_raw)
        if dt is None:
            logger.warning("Could not parse date: %s — skipping row", date_raw)
            continue

        date_key = dt.strftime("%Y-%m-%d")
        date_objects[date_key] = dt

        for norm_col, (metric_name, _) in _COLUMN_MAP.items():
            orig_col = norm_to_orig.get(norm_col)
            if orig_col is None:
                continue
            val = _safe_float(row.get(orig_col, ""))
            if val is not None:
                daily_totals[date_key][metric_name] += val

    metric_rows: list[dict] = []
    text_chunks: list[str] = []
    days_parsed = 0

    for date_key in sorted(daily_totals.keys()):
        day = daily_totals[date_key]
        dt = date_objects[date_key]

        if not day.get("daily_calories"):
            continue  # skip days with no calorie data

        recorded_at = dt.isoformat()
        day_values: dict[str, tuple[float, str]] = {}

        for norm_col, (metric_name, unit) in _COLUMN_MAP.items():
            if metric_name in day:
                total = round(day[metric_name], 2)
                day_values[metric_name] = (total, unit)
                metric_rows.append(
                    {
                        "metric_name": metric_name,
                        "metric_value": total,
                        "unit": unit,
                        "category": "nutrition",
                        "source": "lose_it",
                        "recorded_at": recorded_at,
                        "metadata": {},
                    }
                )

        text_chunks.append(_build_day_chunk(dt, day_values))
        days_parsed += 1

    logger.info("Parsed %d days of nutrition data, %d metric rows", days_parsed, len(metric_rows))
    return metric_rows, text_chunks


def _build_day_chunk(dt: datetime, values: dict[str, tuple[float, str]]) -> str:
    def v(key: str, decimals: int = 0) -> str:
        val = values.get(key, (None,))[0]
        if val is None:
            return "N/A"
        return f"{round(val, decimals)}" if decimals else f"{int(round(val))}"

    label = _format_date_label(dt)
    carbs = v("daily_carbs_g")
    sugars = v("daily_sugars_g", 1)
    fiber = v("daily_fiber_g", 1)
    fat = v("daily_fat_g")
    sat_fat = v("daily_saturated_fat_g", 1)

    return (
        f"Nutrition log for {label}: "
        f"Calories: {v('daily_calories')}, "
        f"Protein: {v('daily_protein_g')}g, "
        f"Carbohydrates: {carbs}g ({sugars}g sugars, {fiber}g fiber), "
        f"Fat: {fat}g ({sat_fat}g saturated), "
        f"Cholesterol: {v('daily_cholesterol_mg')}mg, "
        f"Sodium: {v('daily_sodium_mg')}mg."
    )
