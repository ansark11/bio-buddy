from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.dependencies import get_current_user
from app.db.supabase_client import get_supabase_client
from app.db.queries import get_metrics, get_latest_metrics
from app.models.health_metrics import HealthMetricCreate, SupplementLogCreate
from app.services.rag import generate_health_insights

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])


@router.post("/metrics/log")
async def log_metric(body: HealthMetricCreate, user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    try:
        row = {
            "metric_name": body.metric_name,
            "metric_value": body.metric_value,
            "unit": body.unit,
            "category": body.category.value,
            "source": body.source.value,
            "recorded_at": body.recorded_at.isoformat(),
            "reference_range_low": body.reference_range_low,
            "reference_range_high": body.reference_range_high,
            "metadata": body.metadata,
        }
        result = client.table("health_metrics").upsert(
            {**row, "user_id": str(user["user_id"])},
            on_conflict="user_id,metric_name,recorded_at,source",
        ).execute()
        return {"id": result.data[0]["id"], "status": "logged"}
    except Exception as e:
        logger.error(f"Log metric error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to log metric")


@router.post("/metrics/log/supplement")
async def log_supplement(body: SupplementLogCreate, user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    try:
        result = client.table("supplement_log").upsert(
            {
                "user_id": str(user["user_id"]),
                "supplement_name": body.supplement_name,
                "dosage": body.dosage,
                "taken": body.taken,
                "recorded_at": body.recorded_at.isoformat(),
                "notes": body.notes,
            },
            on_conflict="user_id,supplement_name,recorded_at",
        ).execute()
        return {"id": result.data[0]["id"], "status": "logged"}
    except Exception as e:
        logger.error(f"Log supplement error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to log supplement")


@router.get("/metrics")
async def list_metrics(
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    metric_names: Optional[str] = Query(None, description="Comma-separated metric names"),
    user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    names = metric_names.split(",") if metric_names else None
    data = await get_metrics(
        client, user["user_id"],
        category=category, source=source, document_id=document_id,
        metric_names=names, start_date=start_date, end_date=end_date,
    )
    return {"metrics": data}


@router.get("/metrics/latest")
async def latest_metrics(
    metric_names: str = Query(..., description="Comma-separated metric names"),
    user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    names = [n.strip() for n in metric_names.split(",") if n.strip()]
    data = await get_latest_metrics(client, user["user_id"], names)
    return {"metrics": data}


@router.get("/metrics/timeseries")
async def timeseries(
    metric_name: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    data = await get_metrics(
        client,
        user["user_id"],
        metric_names=[metric_name],
        start_date=start_date,
        end_date=end_date,
        limit=1000,
    )
    points = [{"date": row["recorded_at"], "value": row["metric_value"]} for row in data]
    return {"metric_name": metric_name, "data": list(reversed(points))}


@router.get("/metrics/summary")
async def metrics_summary(user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    key_metrics = ["weight_kg", "resting_heart_rate", "hrv", "sleep_duration_hours", "daily_calories", "dietary_calories"]
    data = await get_latest_metrics(client, user["user_id"], key_metrics)
    return {"summary": {row["metric_name"]: {"value": row["metric_value"], "unit": row["unit"], "recorded_at": row["recorded_at"]} for row in data}}


def _pearson_r(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 3:
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    den = (sum((xi - mean_x) ** 2 for xi in x) * sum((yi - mean_y) ** 2 for yi in y)) ** 0.5
    return round(num / den, 3) if den else None


@router.get("/metrics/correlate")
async def correlate_metrics(
    metric_a: str = Query(...),
    metric_b: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    user_id = user["user_id"]

    rows_a, rows_b = await asyncio.gather(
        get_metrics(client, user_id, metric_names=[metric_a], start_date=start_date, end_date=end_date, limit=500),
        get_metrics(client, user_id, metric_names=[metric_b], start_date=start_date, end_date=end_date, limit=500),
    )

    def _group_by_date(rows: list[dict]) -> dict[str, float]:
        by_date: dict[str, list[float]] = {}
        for r in rows:
            date = r["recorded_at"][:10]
            by_date.setdefault(date, []).append(float(r["metric_value"]))
        return {d: sum(vals) / len(vals) for d, vals in by_date.items()}

    a_by_date = _group_by_date(rows_a)
    b_by_date = _group_by_date(rows_b)

    shared_dates = sorted(set(a_by_date) & set(b_by_date))
    paired = [{"date": d, "a_value": a_by_date[d], "b_value": b_by_date[d]} for d in shared_dates]

    x_vals = [p["a_value"] for p in paired]
    y_vals = [p["b_value"] for p in paired]

    return {
        "metric_a": metric_a,
        "metric_b": metric_b,
        "correlation": _pearson_r(x_vals, y_vals),
        "n": len(paired),
        "data": paired,
    }


@router.get("/metrics/insights")
async def health_insights(user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    try:
        insight = await generate_health_insights(user["user_id"], client)
        return {"insight": insight, "generated_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        logger.error(f"Insights error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate insights")


@router.get("/metrics/biomarkers/latest")
async def latest_biomarkers(user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    result = (
        client.table("health_metrics")
        .select("*")
        .eq("user_id", str(user["user_id"]))
        .eq("category", "biomarker")
        .order("recorded_at", desc=True)
        .limit(200)
        .execute()
    )
    return {"biomarkers": result.data}
