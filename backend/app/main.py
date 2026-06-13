from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.supabase_client import get_supabase_client
from app.routers import auth, ingest, query, metrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _daily_nutrition_check() -> None:
    from app.services.gmail_watcher import check_for_nutrition_emails
    client = get_supabase_client()
    try:
        result = await check_for_nutrition_emails(UUID(settings.scheduled_user_id), client)
        logger.info("Scheduled nutrition check complete: %s", result)
    except Exception as e:
        logger.error("Scheduled nutrition check failed: %s", e, exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.scheduled_user_id:
        scheduler.add_job(
            _daily_nutrition_check,
            "cron",
            hour=9,
            minute=0,
            id="daily_nutrition_check",
        )
        scheduler.start()
        logger.info("APScheduler started — daily nutrition email check at 09:00")
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Health RAG API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
