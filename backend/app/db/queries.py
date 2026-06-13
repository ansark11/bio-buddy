from __future__ import annotations
import logging
from datetime import datetime
from uuid import UUID
from supabase import Client

logger = logging.getLogger(__name__)


async def insert_health_metrics(client: Client, user_id: UUID, metrics: list[dict]) -> int:
    if not metrics:
        return 0
    rows = [{**m, "user_id": str(user_id)} for m in metrics]
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row["metric_name"], row["recorded_at"], row.get("source", ""))
        seen[key] = row
    rows = list(seen.values())
    result = client.table("health_metrics").upsert(rows, on_conflict="user_id,metric_name,recorded_at,source").execute()
    return len(result.data)


async def insert_document(client: Client, user_id: UUID, doc: dict) -> str:
    row = {**doc, "user_id": str(user_id)}
    result = client.table("documents").insert(row).execute()
    return result.data[0]["id"]


async def update_document(client: Client, doc_id: str, updates: dict) -> None:
    client.table("documents").update(updates).eq("id", doc_id).execute()


async def insert_document_chunks(client: Client, user_id: UUID, chunks: list[dict]) -> None:
    if not chunks:
        return
    rows = [{**c, "user_id": str(user_id)} for c in chunks]
    client.table("document_chunks").insert(rows).execute()


async def get_documents(client: Client, user_id: UUID) -> list[dict]:
    result = (
        client.table("documents")
        .select("id,filename,file_type,source,upload_date,processed,processing_error,metadata")
        .eq("user_id", str(user_id))
        .order("upload_date", desc=True)
        .execute()
    )
    return result.data


async def get_metrics(
    client: Client,
    user_id: UUID,
    category: str | None = None,
    metric_names: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    ascending: bool = False,
    source: str | None = None,
    document_id: str | None = None,
) -> list[dict]:
    q = (
        client.table("health_metrics")
        .select("*")
        .eq("user_id", str(user_id))
        .order("recorded_at", desc=not ascending)
        .limit(limit)
    )
    if category:
        q = q.eq("category", category)
    if source:
        q = q.eq("source", source)
    if document_id:
        q = q.eq("metadata->>document_id", document_id)
    if start_date:
        q = q.gte("recorded_at", start_date)
    if end_date:
        q = q.lte("recorded_at", end_date)
    if metric_names:
        q = q.in_("metric_name", metric_names)
    return q.execute().data


async def get_data_coverage(client: Client, user_id: UUID) -> list[dict]:
    """Return first/last recorded_at per source so the LLM always knows data date ranges."""
    coverage = []
    for source in ("lose_it", "apple_health", "blood_test"):
        first = (
            client.table("health_metrics")
            .select("recorded_at")
            .eq("user_id", str(user_id))
            .eq("source", source)
            .order("recorded_at", desc=False)
            .limit(1)
            .execute()
        )
        if not first.data:
            continue
        last = (
            client.table("health_metrics")
            .select("recorded_at")
            .eq("user_id", str(user_id))
            .eq("source", source)
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        )
        coverage.append({
            "source": source,
            "first": first.data[0]["recorded_at"][:10],
            "last": last.data[0]["recorded_at"][:10],
        })
    return coverage


async def get_latest_metrics(client: Client, user_id: UUID, metric_names: list[str]) -> list[dict]:
    results = []
    for name in metric_names:
        row = (
            client.table("health_metrics")
            .select("*")
            .eq("user_id", str(user_id))
            .eq("metric_name", name)
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        )
        if row.data:
            results.append(row.data[0])
    return results


async def semantic_search(
    client: Client,
    user_id: UUID,
    query_embedding: list[float],
    match_threshold: float = 0.7,
    match_count: int = 10,
    source: str | None = None,
) -> list[dict]:
    params: dict = {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count,
        "p_user_id": str(user_id),
    }
    if source:
        params["p_source"] = source
    result = client.rpc("match_document_chunks", params).execute()
    return result.data


async def save_chat_message(
    client: Client, user_id: UUID, role: str, content: str, sources: list, session_id: str | None = None
) -> str:
    result = (
        client.table("chat_messages")
        .insert({"user_id": str(user_id), "role": role, "content": content, "sources": sources, "session_id": session_id})
        .execute()
    )
    return result.data[0]["id"]


async def get_chat_history(client: Client, user_id: UUID, limit: int = 50, session_id: str | None = None) -> list[dict]:
    q = (
        client.table("chat_messages")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .limit(limit)
    )
    if session_id:
        q = q.eq("session_id", session_id)
    return list(reversed(q.execute().data))


async def get_chat_sessions(client: Client, user_id: UUID) -> list[dict]:
    result = (
        client.table("chat_messages")
        .select("session_id,role,content,created_at")
        .eq("user_id", str(user_id))
        .order("created_at", desc=False)
        .execute()
    )
    sessions: dict[str, dict] = {}
    for row in result.data:
        sid = row.get("session_id") or "legacy"
        if sid not in sessions:
            sessions[sid] = {"session_id": sid, "created_at": row["created_at"], "preview": None, "message_count": 0}
        sessions[sid]["message_count"] += 1
        if sessions[sid]["preview"] is None and row["role"] == "user":
            sessions[sid]["preview"] = row["content"][:60]
    return sorted(sessions.values(), key=lambda s: s["created_at"], reverse=True)


async def clear_chat_history(client: Client, user_id: UUID) -> None:
    client.table("chat_messages").delete().eq("user_id", str(user_id)).execute()


async def get_document_by_hash(client: Client, user_id: UUID, file_hash: str) -> dict | None:
    result = (
        client.table("documents")
        .select("id,filename,metadata,upload_date,processed")
        .eq("user_id", str(user_id))
        .eq("file_hash", file_hash)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def delete_document(client: Client, user_id: UUID, doc_id: str) -> None:
    client.table("document_chunks").delete().eq("document_id", doc_id).execute()
    client.table("health_metrics").delete().eq("user_id", str(user_id)).eq("metadata->>document_id", doc_id).execute()
    client.table("documents").delete().eq("id", doc_id).eq("user_id", str(user_id)).execute()
