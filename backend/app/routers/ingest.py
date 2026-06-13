from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from app.config import settings
from app.dependencies import get_current_user
from app.db.supabase_client import get_supabase_client
from app.db.queries import (
    insert_document, insert_health_metrics, update_document, get_documents,
    get_document_by_hash, delete_document,
)
from app.services.pdf_parser import parse_blood_test_pdf, generate_biomarker_chunks
from app.services.embeddings import embed_and_store_chunks
from app.services.apple_health import parse_apple_health_zip, generate_apple_health_text_chunks
from app.services.nutrition_parser import parse_nutrition_csv
from app.services.gmail_watcher import (
    get_auth_url, handle_oauth_callback, check_for_nutrition_emails,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ingest"])

_FLAG_MAP = {"hi": "high", "lo": "low", "h": "high", "l": "low"}


def _normalize_flag(raw: str | None) -> str | None:
    if raw is None:
        return None
    return _FLAG_MAP.get(raw.lower(), raw.lower())


@router.post("/ingest/blood-test")
async def upload_blood_test(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    user_id = user["user_id"]
    client = get_supabase_client()
    pdf_bytes = await file.read()

    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    existing = await get_document_by_hash(client, user_id, file_hash)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"message": "duplicate", "document": existing},
        )

    doc_id = await insert_document(
        client,
        user_id,
        {
            "filename": file.filename,
            "file_type": "pdf",
            "source": "blood_test",
            "processed": False,
            "file_hash": file_hash,
        },
    )

    try:
        extraction, summaries = await parse_blood_test_pdf(pdf_bytes)
    except Exception as e:
        logger.error(f"PDF parsing failed for doc {doc_id}: {e}", exc_info=True)
        await update_document(client, doc_id, {"processed": False, "processing_error": str(e)})
        raise HTTPException(status_code=422, detail=f"Failed to extract data from PDF: {str(e)}")

    # Store biomarkers in health_metrics
    metric_rows = []
    for b in extraction.biomarkers:
        try:
            recorded_at = datetime.strptime(extraction.test_date, "%Y-%m-%d").isoformat() if extraction.test_date else datetime.now(timezone.utc).isoformat()
        except (ValueError, TypeError):
            recorded_at = datetime.now(timezone.utc).isoformat()

        metric_rows.append(
            {
                "metric_name": b.standardized_name,
                "metric_value": b.value,
                "unit": b.unit or "",
                "category": "biomarker",
                "source": "blood_test",
                "recorded_at": recorded_at,
                "reference_range_low": b.reference_range_low,
                "reference_range_high": b.reference_range_high,
                "flag": _normalize_flag(b.flag),
                "reference_range_notes": b.reference_range_notes,
                "metadata": {
                    "lab_name": extraction.lab_name,
                    "original_name": b.name,
                    "document_id": doc_id,
                },
            }
        )

    if not metric_rows:
        logger.warning(f"Blood test doc {doc_id}: LLM extracted 0 biomarkers")
        await update_document(client, doc_id, {"processing_error": "No biomarkers extracted"})

    inserted_count = await insert_health_metrics(client, user_id, metric_rows)

    # Embed one chunk per biomarker plus the overall summary for broad queries
    base_meta = {"test_date": extraction.test_date, "lab_name": extraction.lab_name}
    biomarker_chunks = generate_biomarker_chunks(extraction)
    embed_chunks = summaries[0:1] + biomarker_chunks
    embed_meta = [base_meta] + [
        {
            "test_date": extraction.test_date,
            "lab_name": extraction.lab_name,
            "biomarker_name": b.standardized_name,
            "flag": b.flag,
        }
        for b in extraction.biomarkers
    ]
    embed_prefix = f"Blood test, {extraction.lab_name or 'lab'}, {extraction.test_date or 'unknown date'}. "
    try:
        await embed_and_store_chunks(
            client=client,
            document_id=doc_id,
            text_chunks=embed_chunks,
            user_id=user_id,
            source="blood_test",
            metadata=embed_meta,
            embed_prefix=embed_prefix,
        )
    except Exception as e:
        logger.error(f"Embedding failed for doc {doc_id}: {e}", exc_info=True)
        await update_document(client, doc_id, {"processing_error": f"Embedding failed: {str(e)}"})

    await update_document(
        client,
        doc_id,
        {
            "processed": True,
            "metadata": {
                "lab_name": extraction.lab_name,
                "test_date": extraction.test_date,
                "biomarker_count": len(extraction.biomarkers),
            },
        },
    )

    return {
        "document_id": doc_id,
        "lab_name": extraction.lab_name,
        "test_date": extraction.test_date,
        "biomarkers_extracted": len(extraction.biomarkers),
        "biomarkers_stored": inserted_count,
        "chunks_embedded": len(embed_chunks),
        "biomarkers": [
            {
                "name": b.name,
                "standardized_name": b.standardized_name,
                "value": b.value,
                "unit": b.unit or "",
                "flag": _normalize_flag(b.flag),
                "reference_range_low": b.reference_range_low,
                "reference_range_high": b.reference_range_high,
            }
            for b in extraction.biomarkers
        ],
    }


@router.get("/ingest/documents")
async def list_documents(user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    docs = await get_documents(client, user["user_id"])
    return {"documents": docs}


@router.delete("/ingest/documents/{doc_id}")
async def delete_document_endpoint(doc_id: str, user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    docs = await get_documents(client, user["user_id"])
    if not any(d["id"] == doc_id for d in docs):
        raise HTTPException(status_code=404, detail="Document not found")
    await delete_document(client, user["user_id"], doc_id)
    return {"status": "deleted"}


@router.post("/ingest/nutrition")
async def upload_nutrition(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    user_id = user["user_id"]
    client = get_supabase_client()
    csv_bytes = await file.read()

    file_hash = hashlib.sha256(csv_bytes).hexdigest()
    existing = await get_document_by_hash(client, user_id, file_hash)
    if existing:
        raise HTTPException(status_code=409, detail={"message": "duplicate", "document": existing})

    try:
        metric_rows, text_chunks = parse_nutrition_csv(csv_bytes)
    except Exception as e:
        logger.error("Nutrition CSV parse failed: %s", e, exc_info=True)
        raise HTTPException(status_code=422, detail=f"Failed to parse CSV: {str(e)}")

    if not metric_rows:
        raise HTTPException(status_code=422, detail="No valid nutrition data found in CSV")

    dates = [r["recorded_at"][:10] for r in metric_rows]
    first_date, last_date = min(dates), max(dates)
    days_parsed = len(text_chunks)

    doc_id = await insert_document(
        client,
        user_id,
        {
            "filename": file.filename,
            "file_type": "csv",
            "source": "lose_it",
            "processed": False,
            "file_hash": file_hash,
            "metadata": {"first_date": first_date, "last_date": last_date},
        },
    )

    for row in metric_rows:
        row["metadata"] = {**row.get("metadata", {}), "document_id": doc_id}

    try:
        metrics_stored = await insert_health_metrics(client, user_id, metric_rows)
    except Exception as e:
        logger.error("Nutrition metrics insert failed: %s", e, exc_info=True)
        await update_document(client, doc_id, {"processing_error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to store nutrition metrics")

    chunk_meta = {"first_date": first_date, "last_date": last_date}
    nutrition_prefix = f"Nutrition log, {first_date} to {last_date}. "
    try:
        await embed_and_store_chunks(
            client=client,
            document_id=doc_id,
            text_chunks=text_chunks,
            user_id=user_id,
            source="lose_it",
            metadata=chunk_meta,
            embed_prefix=nutrition_prefix,
        )
    except Exception as e:
        logger.error("Nutrition embedding failed for doc %s: %s", doc_id, e, exc_info=True)
        await update_document(client, doc_id, {"processing_error": f"Embedding failed: {str(e)}"})

    await update_document(
        client,
        doc_id,
        {"processed": True, "metadata": {"first_date": first_date, "last_date": last_date, "days": days_parsed}},
    )

    return {
        "document_id": doc_id,
        "days_parsed": days_parsed,
        "metrics_stored": metrics_stored,
        "chunks_embedded": len(text_chunks),
        "date_range": {"first": first_date, "last": last_date},
    }


@router.get("/ingest/nutrition/gmail-init")
async def gmail_init(user: dict = Depends(get_current_user)):
    if not settings.gmail_client_id or not settings.gmail_client_secret:
        raise HTTPException(
            status_code=400,
            detail="GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be set in .env",
        )
    try:
        auth_url = get_auth_url()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build auth URL: {str(e)}")
    return {"auth_url": auth_url}


@router.get("/ingest/nutrition/gmail-callback")
async def gmail_callback(code: str = Query(...)):
    try:
        handle_oauth_callback(code)
    except Exception as e:
        logger.error("Gmail OAuth callback failed: %s", e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")
    return {"status": "authenticated", "message": "Gmail connected. You can now use POST /api/ingest/nutrition/check-email"}


@router.post("/ingest/nutrition/check-email")
async def check_nutrition_email(user: dict = Depends(get_current_user)):
    token_path = Path(settings.gmail_token_file)
    if not token_path.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                "Gmail is not connected. Visit GET /api/ingest/nutrition/gmail-init "
                "to start the OAuth flow."
            ),
        )
    client = get_supabase_client()
    try:
        result = await check_for_nutrition_emails(user["user_id"], client)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Gmail email check failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Email check failed: {str(e)}")
    return result


@router.post("/ingest/apple-health")
async def upload_apple_health(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload the export.zip file from Apple Health")

    user_id = user["user_id"]
    client = get_supabase_client()
    zip_bytes = await file.read()

    file_hash = hashlib.sha256(zip_bytes).hexdigest()
    existing = await get_document_by_hash(client, user_id, file_hash)
    if existing:
        raise HTTPException(status_code=409, detail={"message": "duplicate", "document": existing})

    doc_id = await insert_document(client, user_id, {
        "filename": file.filename,
        "file_type": "zip",
        "source": "apple_health",
        "processed": False,
        "file_hash": file_hash,
        "metadata": {},
    })

    try:
        metric_rows, summary = parse_apple_health_zip(zip_bytes)
    except Exception as e:
        logger.error(f"Apple Health parse failed: {e}", exc_info=True)
        await update_document(client, doc_id, {"processing_error": str(e)})
        raise HTTPException(status_code=422, detail=f"Failed to parse Apple Health export: {str(e)}")

    dates = [row["recorded_at"][:10] for row in metric_rows]
    first_date = min(dates) if dates else "unknown"
    last_date = max(dates) if dates else "unknown"

    for row in metric_rows:
        row["metadata"] = {**row.get("metadata", {}), "document_id": doc_id}

    inserted = await insert_health_metrics(client, user_id, metric_rows)

    # Embed weekly summary chunks so semantic search works for Apple Health questions
    ah_chunks = generate_apple_health_text_chunks(metric_rows, first_date, last_date)
    if ah_chunks:
        ah_meta = {"first_date": first_date, "last_date": last_date}
        ah_prefix = f"Apple Health data, {first_date} to {last_date}. "
        try:
            await embed_and_store_chunks(
                client=client,
                document_id=doc_id,
                text_chunks=ah_chunks,
                user_id=user_id,
                source="apple_health",
                metadata=ah_meta,
                embed_prefix=ah_prefix,
            )
        except Exception as e:
            logger.error(f"Apple Health embedding failed for doc {doc_id}: {e}", exc_info=True)

    await update_document(client, doc_id, {
        "processed": True,
        "metadata": {"breakdown": summary, "first_date": first_date, "last_date": last_date},
    })

    return {
        "document_id": doc_id,
        "metrics_inserted": inserted,
        "chunks_embedded": len(ah_chunks),
        "breakdown": summary,
    }
