from __future__ import annotations
import asyncio
import logging
from uuid import UUID

from groq import Groq

from app.config import settings
from app.db.queries import save_chat_message, get_chat_history, get_data_coverage
from app.services.groq_utils import groq_call_with_retry
from app.services.query_router import classify_and_retrieve

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {
    "lose_it": "Nutrition (Lose It)",
    "apple_health": "Apple Health",
    "blood_test": "Blood Tests",
}


SYSTEM_PROMPT = """You are a personal health assistant. Answer the user's question using ONLY the provided context from their health data. Be specific with numbers and dates.

Rules:
- Cite specific values and dates from the context
- If showing trends, mention the direction and magnitude of change
- Flag any values outside reference ranges
- Do not make medical diagnoses or treatment recommendations
- If asked about correlations, note that correlation does not imply causation
- Be concise but thorough
- If the data does not contain enough information to answer, say exactly that — do not guess or fabricate values
"""


def _format_structured_context(rows: list[dict]) -> str:
    if not rows:
        return ""
    lines = ["STRUCTURED DATA (from health metrics database):"]
    for r in rows:
        ref = ""
        low = r.get("reference_range_low")
        high = r.get("reference_range_high")
        if low is not None and high is not None:
            ref = f" (reference range: {low}–{high})"
        elif high is not None:
            ref = f" (reference range: <{high})"
        lines.append(f"- {r['metric_name']}: {r['metric_value']} {r['unit']} on {r['recorded_at'][:10]}{ref}")
    return "\n".join(lines)


def _format_semantic_context(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    lines = ["SEMANTIC CONTEXT (from embedded health documents):"]
    for c in chunks:
        similarity = c.get("similarity", 0)
        lines.append(f"[similarity={similarity:.2f}]\n{c['chunk_text']}")
    return "\n\n".join(lines)


async def answer_question(user_id: UUID, question: str, client, session_id: str | None = None) -> dict:
    retrieval, coverage = await asyncio.gather(
        classify_and_retrieve(user_id, question, client),
        get_data_coverage(client, user_id),
    )

    if coverage:
        lines = ["DATA COVERAGE (full date ranges of your health data):"]
        for c in coverage:
            label = _SOURCE_LABELS.get(c["source"], c["source"])
            lines.append(f"- {label}: {c['first']} through {c['last']}")
        coverage_header = "\n".join(lines)
    else:
        coverage_header = ""

    structured_context = _format_structured_context(retrieval["structured_results"])
    semantic_context = _format_semantic_context(retrieval["semantic_results"])

    context_parts = [p for p in [coverage_header, structured_context, semantic_context] if p]
    full_context = "\n\n".join(context_parts) if context_parts else "No relevant health data found."

    # Include last 5 messages from the current session for conversation context
    history = await get_chat_history(client, user_id, limit=10, session_id=session_id)
    conversation = ""
    if history:
        recent = history[-5:]
        conversation = "\nCONVERSATION HISTORY:\n" + "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in recent
        )

    def _generate():
        client = Groq(api_key=settings.groq_api_key)
        return groq_call_with_retry(
            lambda: client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"CONTEXT:\n{full_context}{conversation}\n\nQUESTION: {question}\n\nANSWER:"},
                ],
                temperature=0.2,
            )
        ).choices[0].message.content

    answer = (await asyncio.get_event_loop().run_in_executor(None, _generate)).strip()

    sources = []
    for r in retrieval["structured_results"]:
        sources.append({
            "type": "metric",
            "content": f"{r['metric_name']}: {r['metric_value']} {r['unit']}",
            "metadata": {"recorded_at": r.get("recorded_at"), "source": r.get("source")},
        })
    for c in retrieval["semantic_results"]:
        sources.append({
            "type": "chunk",
            "content": c["chunk_text"][:200],
            "metadata": {"similarity": c.get("similarity"), "source": c.get("source")},
        })

    await save_chat_message(client, user_id, "user", question, [], session_id=session_id)
    await save_chat_message(client, user_id, "assistant", answer, sources, session_id=session_id)

    return {"response": answer, "sources": sources}


INSIGHTS_PROMPT = """Give me a concise health summary (3–5 bullet points) based on my most recently uploaded data. Highlight any out-of-range biomarkers, notable nutrition patterns, and activity or recovery trends. Be specific with values and dates. Do not make diagnoses or treatment recommendations."""


async def generate_health_insights(user_id: UUID, client) -> str:
    retrieval, coverage = await asyncio.gather(
        classify_and_retrieve(user_id, INSIGHTS_PROMPT, client),
        get_data_coverage(client, user_id),
    )

    if coverage:
        lines = ["DATA COVERAGE (full date ranges of your health data):"]
        for c in coverage:
            label = _SOURCE_LABELS.get(c["source"], c["source"])
            lines.append(f"- {label}: {c['first']} through {c['last']}")
        coverage_header = "\n".join(lines)
    else:
        coverage_header = ""

    structured_context = _format_structured_context(retrieval["structured_results"])
    semantic_context = _format_semantic_context(retrieval["semantic_results"])

    context_parts = [p for p in [coverage_header, structured_context, semantic_context] if p]
    full_context = "\n\n".join(context_parts) if context_parts else "No relevant health data found."

    def _generate():
        client = Groq(api_key=settings.groq_api_key)
        return groq_call_with_retry(
            lambda: client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"CONTEXT:\n{full_context}\n\nQUESTION: {INSIGHTS_PROMPT}\n\nANSWER:"},
                ],
                temperature=0.2,
            )
        ).choices[0].message.content

    return (await asyncio.get_event_loop().run_in_executor(None, _generate)).strip()
