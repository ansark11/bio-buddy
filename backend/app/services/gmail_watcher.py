from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from uuid import UUID

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from supabase import Client

from app.config import settings
from app.db.queries import insert_health_metrics, insert_document, update_document
from app.services.embeddings import embed_and_store_chunks
from app.services.nutrition_parser import parse_nutrition_csv

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.gmail_redirect_uri],
        }
    }


def get_auth_url() -> str:
    """Return the Google OAuth2 consent URL. User must open this in a browser."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.gmail_redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def handle_oauth_callback(code: str) -> None:
    """Exchange the auth code for credentials and save to the token file."""
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.gmail_redirect_uri,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    Path(settings.gmail_token_file).write_text(creds.to_json())
    logger.info("Gmail token saved to %s", settings.gmail_token_file)


def get_gmail_service():
    """Load stored credentials, refresh if needed, return a Gmail API resource."""
    token_path = Path(settings.gmail_token_file)
    if not token_path.exists():
        raise FileNotFoundError(
            f"Gmail token file not found at '{settings.gmail_token_file}'. "
            "Complete OAuth setup via GET /api/ingest/nutrition/gmail-init first."
        )

    creds = Credentials.from_authorized_user_info(
        json.loads(token_path.read_text()), SCOPES
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        logger.info("Gmail token refreshed")

    return build("gmail", "v1", credentials=creds)


def _search_messages(service, query: str, max_results: int = 10) -> list[dict]:
    result = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return result.get("messages", [])


def _get_csv_attachment(service, msg_id: str) -> tuple[str, bytes] | None:
    """Return (filename, bytes) for the first .csv attachment in the message, or None."""
    msg = service.users().messages().get(userId="me", id=msg_id).execute()
    parts = msg.get("payload", {}).get("parts", [])

    for part in parts:
        filename = part.get("filename", "")
        if not filename.lower().endswith(".csv"):
            continue
        body = part.get("body", {})
        attachment_id = body.get("attachmentId")
        if not attachment_id:
            data = body.get("data", "")
        else:
            att = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=msg_id, id=attachment_id)
                .execute()
            )
            data = att.get("data", "")
        raw = base64.urlsafe_b64decode(data + "==")
        return filename, raw

    return None


def _mark_read(service, msg_id: str) -> None:
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()


async def check_for_nutrition_emails(user_id: UUID, db_client: Client) -> dict:
    """Search Gmail for Lose It CSV attachments, parse them, and store metrics.

    Safe to call repeatedly — deduplication is handled by upsert in insert_health_metrics.
    """
    loop = asyncio.get_event_loop()

    service = await loop.run_in_executor(None, get_gmail_service)

    sender = settings.lose_it_sender_email
    query = f"has:attachment{f' from:{sender}' if sender else ''}"

    messages = await loop.run_in_executor(None, _search_messages, service, query, 10)

    if not messages:
        logger.info("No Lose It emails found matching query: %s", query)
        return {"emails_processed": 0, "metrics_inserted": 0, "date_range": None}

    total_metrics = 0
    emails_processed = 0
    all_dates: list[str] = []

    for msg_stub in messages:
        msg_id = msg_stub["id"]
        try:
            result = await loop.run_in_executor(
                None, _get_csv_attachment, service, msg_id
            )
            if result is None:
                continue
            filename, csv_bytes = result

            metric_rows, text_chunks = parse_nutrition_csv(csv_bytes)
            if not metric_rows:
                continue

            doc_id = await insert_document(
                db_client,
                user_id,
                {
                    "filename": filename,
                    "file_type": "csv",
                    "source": "lose_it",
                    "processed": False,
                    "metadata": {"source": "gmail"},
                },
            )

            inserted = await insert_health_metrics(db_client, user_id, metric_rows)
            total_metrics += inserted

            dates = [r["recorded_at"][:10] for r in metric_rows]
            if dates:
                first, last = min(dates), max(dates)
                all_dates.extend([first, last])
                meta = {"first_date": first, "last_date": last}
            else:
                meta = {}

            try:
                await embed_and_store_chunks(
                    client=db_client,
                    document_id=doc_id,
                    text_chunks=text_chunks,
                    user_id=user_id,
                    source="lose_it",
                    metadata=meta,
                )
            except Exception as e:
                logger.error("Embedding failed for Gmail email %s: %s", msg_id, e, exc_info=True)

            await update_document(
                db_client,
                doc_id,
                {"processed": True, "metadata": {**meta, "source": "gmail", "gmail_message_id": msg_id}},
            )

            await loop.run_in_executor(None, _mark_read, service, msg_id)
            emails_processed += 1

        except Exception as e:
            logger.error("Failed to process Gmail message %s: %s", msg_id, e, exc_info=True)

    date_range = (
        {"first": min(all_dates), "last": max(all_dates)} if all_dates else None
    )
    logger.info(
        "Gmail check complete: %d emails processed, %d metrics inserted",
        emails_processed,
        total_metrics,
    )
    return {
        "emails_processed": emails_processed,
        "metrics_inserted": total_metrics,
        "date_range": date_range,
    }
