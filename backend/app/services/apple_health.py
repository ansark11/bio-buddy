from __future__ import annotations
import io
import logging
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from xml.etree.ElementTree import iterparse

logger = logging.getLogger(__name__)

# (metric_name, category, canonical_unit)
RECORD_TYPE_MAP: dict[str, tuple[str, str, str]] = {
    "HKQuantityTypeIdentifierBodyMass":                 ("weight_kg",          "body_composition", "kg"),
    "HKQuantityTypeIdentifierHeartRate":                ("heart_rate",          "cardiovascular",   "bpm"),
    "HKQuantityTypeIdentifierRestingHeartRate":         ("resting_heart_rate",  "cardiovascular",   "bpm"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv",                 "cardiovascular",   "ms"),
    "HKQuantityTypeIdentifierStepCount":                ("step_count",          "activity",         "steps"),
    "HKQuantityTypeIdentifierActiveEnergyBurned":       ("active_calories",     "activity",         "kcal"),
    "HKQuantityTypeIdentifierAppleExerciseTime":        ("exercise_minutes",    "activity",         "min"),
    "HKQuantityTypeIdentifierDietaryEnergyConsumed":    ("dietary_calories",    "nutrition",        "kcal"),
    "HKQuantityTypeIdentifierVO2Max":                   ("vo2_max",             "cardiovascular",   "mL/kg/min"),
}

# Reverse map: metric_name → (category, canonical_unit)
_METRIC_INFO: dict[str, tuple[str, str]] = {v[0]: (v[1], v[2]) for v in RECORD_TYPE_MAP.values()}
_METRIC_INFO["heart_rate_min"] = ("cardiovascular", "bpm")
_METRIC_INFO["heart_rate_max"] = ("cardiovascular", "bpm")
_METRIC_INFO["sleep_duration_hours"] = ("sleep", "hours")

SUM_METRICS = {"step_count", "active_calories", "exercise_minutes", "dietary_calories"}
AVG_METRICS = {"heart_rate", "hrv", "vo2_max"}
LATEST_METRICS = {"weight_kg", "resting_heart_rate"}

SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
SLEEP_ASLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",  # iOS 16+
}

WORKOUT_TYPE_MAP: dict[str, str] = {
    "HKWorkoutActivityTypeElliptical":                    "elliptical",
    "HKWorkoutActivityTypeTraditionalStrengthTraining":   "strength_training",
    "HKWorkoutActivityTypeWalking":                       "walking",
    "HKWorkoutActivityTypeRunning":                       "running",
    "HKWorkoutActivityTypeCycling":                       "cycling",
    "HKWorkoutActivityTypeYoga":                          "yoga",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "hiit",
    "HKWorkoutActivityTypeSwimming":                      "swimming",
    "HKWorkoutActivityTypeFunctionalStrengthTraining":    "functional_strength",
    "HKWorkoutActivityTypeStairClimbing":                 "stair_climbing",
    "HKWorkoutActivityTypePilates":                       "pilates",
    "HKWorkoutActivityTypeRowing":                        "rowing",
}

_WORKOUT_LABELS: dict[str, str] = {
    "elliptical":         "Elliptical",
    "strength_training":  "Strength Training",
    "walking":            "Walking",
    "running":            "Running",
    "cycling":            "Cycling",
    "yoga":               "Yoga",
    "hiit":               "HIIT",
    "swimming":           "Swimming",
    "functional_strength":"Functional Strength",
    "stair_climbing":     "Stair Climbing",
    "pilates":            "Pilates",
    "rowing":             "Rowing",
}

DATE_FMT = "%Y-%m-%d %H:%M:%S %z"


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, DATE_FMT)


def _night_date(dt: datetime) -> str:
    """Assign a sleep record to its 'night date'.
    Records starting at 6 PM or later belong to that evening.
    Records starting before 6 PM belong to the previous evening.
    """
    if dt.hour >= 18:
        return dt.strftime("%Y-%m-%d")
    return (dt - timedelta(days=1)).strftime("%Y-%m-%d")


def _open_xml(zip_bytes: bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml_name = next((n for n in zf.namelist() if n.endswith("export.xml")), None)
        if not xml_name:
            raise ValueError("Could not find export.xml inside the ZIP file")
        return io.BytesIO(zf.read(xml_name))


def _metric_row(metric_name: str, date_str: str, value: float) -> dict:
    category, unit = _METRIC_INFO[metric_name]
    return {
        "metric_name": metric_name,
        "metric_value": round(value, 4),
        "unit": unit,
        "category": category,
        "source": "apple_health",
        "recorded_at": f"{date_str}T12:00:00+00:00",
        "metadata": {},
    }


def _format_workout_label(name: str) -> str:
    return _WORKOUT_LABELS.get(name, name.replace("_", " ").title())


def parse_apple_health_zip(zip_bytes: bytes) -> tuple[list[dict], dict[str, int]]:
    xml_stream = _open_xml(zip_bytes)

    sums: dict[tuple[str, str], float] = defaultdict(float)
    avgs: dict[tuple[str, str], list[float]] = defaultdict(list)
    latests: dict[tuple[str, str], tuple[datetime, float]] = {}
    sleep_minutes: dict[str, float] = defaultdict(float)
    workout_rows: list[dict] = []

    for _event, elem in iterparse(xml_stream, events=("end",)):
        if elem.tag in {"WorkoutEvent", "MetadataEntry"}:
            # Don't clear — parent Workout needs to read these children
            continue

        if elem.tag == "Workout":
            activity_type = elem.get("workoutActivityType", "")
            workout_name = WORKOUT_TYPE_MAP.get(
                activity_type,
                activity_type.removeprefix("HKWorkoutActivityType").lower(),
            )
            try:
                duration = float(elem.get("duration", 0))
                energy = float(elem.get("totalEnergyBurned") or 0)
                distance_raw = elem.get("totalDistance")
                distance = float(distance_raw) if distance_raw else None
                start_dt = _parse_dt(elem.get("startDate", ""))
                end_dt = _parse_dt(elem.get("endDate", ""))
            except (ValueError, TypeError):
                elem.clear()
                continue

            indoor = None
            for child in elem:
                if child.tag == "MetadataEntry" and child.get("key") == "HKMetadataKeyIndoorWorkout":
                    indoor = child.get("value") == "1"

            meta: dict = {
                "energy_kcal": round(energy, 1),
                "indoor": indoor,
                "end_date": end_dt.isoformat(),
            }
            if distance is not None:
                meta["distance_km"] = round(distance, 2)

            workout_rows.append({
                "metric_name": workout_name,
                "metric_value": round(duration, 1),
                "unit": "min",
                "category": "workout",
                "source": "apple_health",
                "recorded_at": start_dt.isoformat(),
                "metadata": meta,
            })
            elem.clear()
            continue

        if elem.tag != "Record":
            elem.clear()
            continue

        rec_type = elem.get("type", "")

        if rec_type == SLEEP_TYPE:
            stage = elem.get("value", "")
            if stage in SLEEP_ASLEEP_VALUES:
                try:
                    start = _parse_dt(elem.get("startDate", ""))
                    end = _parse_dt(elem.get("endDate", ""))
                    mins = (end - start).total_seconds() / 60
                    if 0 < mins < 720:
                        sleep_minutes[_night_date(start)] += mins
                except (ValueError, TypeError):
                    pass
            elem.clear()
            continue

        if rec_type not in RECORD_TYPE_MAP:
            elem.clear()
            continue

        metric_name, _cat, _unit = RECORD_TYPE_MAP[rec_type]

        try:
            value = float(elem.get("value", "0"))
            raw_unit = elem.get("unit", "")
            start_dt = _parse_dt(elem.get("startDate", ""))
        except (ValueError, TypeError):
            elem.clear()
            continue

        if metric_name == "weight_kg" and raw_unit in ("lb", "lbs"):
            value *= 0.453592

        date_str = start_dt.strftime("%Y-%m-%d")

        if metric_name in SUM_METRICS:
            sums[(metric_name, date_str)] += value
        elif metric_name in AVG_METRICS:
            avgs[(metric_name, date_str)].append(value)
        elif metric_name in LATEST_METRICS:
            key = (metric_name, date_str)
            if key not in latests or start_dt > latests[key][0]:
                latests[key] = (start_dt, value)

        elem.clear()

    rows: list[dict] = []
    summary: dict[str, int] = defaultdict(int)

    for (metric_name, date_str), total in sums.items():
        rows.append(_metric_row(metric_name, date_str, total))
        summary[metric_name] += 1

    for (metric_name, date_str), values in avgs.items():
        rows.append(_metric_row(metric_name, date_str, sum(values) / len(values)))
        summary[metric_name] += 1
        if metric_name == "heart_rate":
            rows.append(_metric_row("heart_rate_min", date_str, min(values)))
            rows.append(_metric_row("heart_rate_max", date_str, max(values)))

    for (metric_name, date_str), (_, value) in latests.items():
        rows.append(_metric_row(metric_name, date_str, value))
        summary[metric_name] += 1

    for date_str, total_mins in sleep_minutes.items():
        rows.append(_metric_row("sleep_duration_hours", date_str, total_mins / 60))
        summary["sleep_duration_hours"] += 1

    rows.extend(workout_rows)
    for wr in workout_rows:
        summary[wr["metric_name"]] += 1

    logger.info(f"Apple Health parsed {len(rows)} metric rows across {len(summary)} metric types")
    return rows, dict(summary)


_AH_FORMAT: dict[str, str] = {
    "step_count": "{:,.0f} steps/day",
    "active_calories": "{:.0f} active kcal/day",
    "exercise_minutes": "{:.0f} exercise min/day",
    "sleep_duration_hours": "{:.1f} hrs sleep/night",
    "resting_heart_rate": "{:.0f} bpm resting HR",
    "hrv": "{:.0f} ms HRV",
    "heart_rate": "{:.0f} bpm avg HR",
    "weight_kg": "{:.1f} kg weight",
    "vo2_max": "{:.1f} mL/kg/min VO2max",
    "dietary_calories": "{:.0f} dietary kcal/day",
}


def _workout_chunk(row: dict) -> str:
    label = _format_workout_label(row["metric_name"])
    duration = row["metric_value"]
    meta = row.get("metadata", {})
    energy = meta.get("energy_kcal")
    distance = meta.get("distance_km")
    indoor = meta.get("indoor")

    parts: list[str] = [f"{duration:.0f} min"]
    if energy:
        parts.append(f"{energy:.0f} kcal")
    if distance:
        parts.append(f"{distance:.1f} km")
    if indoor is not None:
        parts.append("indoor" if indoor else "outdoor")

    date_str = row["recorded_at"][:10]
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_label = dt.strftime("%B %-d, %Y")
    except ValueError:
        date_label = date_str

    return f"{label} workout on {date_label}: {', '.join(parts)}."


def generate_apple_health_text_chunks(
    metric_rows: list[dict], first_date: str, last_date: str
) -> list[str]:
    """Build one text chunk per calendar week, one per workout session, plus an overview chunk."""
    weekly: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    # week_start → workout_name → list of (duration, energy)
    weekly_workouts: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    workout_rows: list[dict] = []

    for row in metric_rows:
        date_str = row["recorded_at"][:10]
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")

        if row.get("category") == "workout":
            workout_rows.append(row)
            meta = row.get("metadata", {})
            energy = meta.get("energy_kcal", 0.0) or 0.0
            weekly_workouts[week_start][row["metric_name"]].append((row["metric_value"], energy))
        else:
            weekly[week_start][row["metric_name"]].append(row["metric_value"])

    chunks = []
    for week_start in sorted(set(list(weekly.keys()) + list(weekly_workouts.keys()))):
        wm = weekly.get(week_start, {})
        parts = []
        for metric, fmt in _AH_FORMAT.items():
            if metric not in wm:
                continue
            avg = sum(wm[metric]) / len(wm[metric])
            parts.append(fmt.format(avg))

        ww = weekly_workouts.get(week_start, {})
        for workout_name in sorted(ww.keys()):
            sessions = ww[workout_name]
            count = len(sessions)
            avg_dur = sum(d for d, _ in sessions) / count
            total_kcal = sum(e for _, e in sessions)
            label = _format_workout_label(workout_name)
            session_word = "session" if count == 1 else "sessions"
            parts.append(f"{count} {label} {session_word} (avg {avg_dur:.0f} min, {total_kcal:.0f} kcal)")

        if parts:
            chunks.append(f"Apple Health week of {week_start}: " + ", ".join(parts) + ".")

    if not chunks:
        return []

    metric_names = sorted({row["metric_name"] for row in metric_rows})
    overview = (
        f"Apple Health data from {first_date} to {last_date}. "
        f"Tracks: {', '.join(metric_names)}. "
        f"Data spans {len(set(list(weekly.keys()) + list(weekly_workouts.keys())))} weeks "
        f"with {len(metric_rows)} total measurements."
    )

    per_workout = [_workout_chunk(r) for r in sorted(workout_rows, key=lambda r: r["recorded_at"])]

    return [overview] + chunks + per_workout
