import asyncio
import json
import logging
import re
from uuid import UUID

import cohere
from groq import Groq

from app.config import settings
from app.db.queries import get_metrics, get_latest_metrics, semantic_search
from app.services.embeddings import generate_embedding
from app.services.groq_utils import groq_call_with_retry

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """
Given this user question about their personal health data, classify the query type.

Question: "{question}"

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "query_type": "structured" | "semantic" | "hybrid",
  "structured_query": {{
    "metric_names": [],
    "categories": [],
    "source": null,
    "date_range": {{"start": null, "end": null}},
    "aggregation": "latest" | "trend" | "average" | "min" | "max" | null
  }},
  "semantic_search_query": "rephrased query optimized for embedding search, or null",
  "reasoning": "one sentence explanation"
}}

Classification rules:
- "structured" = questions about specific numbers, trends, or comparisons that can be answered by querying the health_metrics table (e.g. "what was my LDL?", "how has my weight changed?", "what is my latest HRV?")
- "semantic" = questions about qualitative content, notes, food details, or context that require searching embedded text (e.g. "what did my doctor flag?", "when did I eat sushi?", "what did the lab report say?")
- "hybrid" = questions needing both structured numbers AND semantic context (e.g. "are my vitamin D levels improving and could my diet explain it?", "why might my sleep be poor?")

Source values (set "source" in structured_query when the question clearly targets one data type):
- "blood_test" — biomarkers, lab results, reference ranges, flagged values, cholesterol, glucose, hormones, vitamins, liver enzymes, kidney function. Any question about values being "outside normal range", "flagged", "high", or "low" refers to blood test data.
- "apple_health" — steps, active calories, exercise minutes, resting heart rate, HRV, sleep
- "lose_it" — nutrition, calories, macros, protein, carbs, fat, sodium, fiber, food intake
- null — leave null when the question spans multiple sources or source is ambiguous

Common metric_names to use in structured_query (use these exact strings):
ldl_cholesterol, hdl_cholesterol, total_cholesterol, triglycerides, hba1c, fasting_glucose,
tsh, free_t4, vitamin_d, vitamin_b12, iron, ferritin, hemoglobin, creatinine, egfr,
alt, ast, crp, testosterone, cortisol, weight_kg, resting_heart_rate, hrv, heart_rate,
step_count, active_calories, exercise_minutes, sleep_duration_hours, sleep_deep_minutes,
sleep_rem_minutes, daily_calories, daily_protein_g, daily_carbs_g, daily_fat_g,
daily_sodium_mg, daily_fiber_g, dietary_calories

Questions about data coverage, date ranges, or data span MUST be classified as structured:
- "What food logs do I have?" → structured, categories=["nutrition"], source="lose_it", aggregation="trend"
- "How far back does my nutrition data go?" → structured, source="lose_it", aggregation="trend"
- "When does my Apple Health data start?" → structured, source="apple_health", aggregation="trend"
- "What data do you have on me?" → structured, categories=["nutrition","activity","cardiovascular"], source=null, aggregation="trend"
- "Are any biomarkers outside the normal range?" → structured, source="blood_test", aggregation="latest"
"""


async def _generate_hyde_passage(question: str) -> str:
    """Generate a hypothetical health data passage to improve embedding match quality."""
    def _call():
        client = Groq(api_key=settings.groq_api_key)
        return groq_call_with_retry(
            lambda: client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": (
                    "Write a short (2-3 sentence) hypothetical health data passage that would "
                    "directly answer this question. Write it as if it were an excerpt from a "
                    f"health report or data summary.\n\nQuestion: {question}"
                )}],
                temperature=0.3,
                max_tokens=120,
            )
        ).choices[0].message.content.strip()

    return await asyncio.get_event_loop().run_in_executor(None, _call)


async def _rerank(query: str, chunks: list[dict], top_n: int = 8) -> list[dict]:
    """Re-rank retrieved chunks using Cohere Rerank for cross-encoder precision."""
    if not chunks or not settings.cohere_api_key:
        return chunks[:top_n]

    def _call():
        co = cohere.ClientV2(api_key=settings.cohere_api_key)
        return co.rerank(
            model="rerank-v3.5",
            query=query,
            documents=[c["chunk_text"] for c in chunks],
            top_n=top_n,
        )

    try:
        results = await asyncio.get_event_loop().run_in_executor(None, _call)
        return [chunks[r.index] for r in results.results]
    except Exception as e:
        logger.warning(f"Cohere rerank failed ({e}), returning original order")
        return chunks[:top_n]


async def classify_and_retrieve(user_id: UUID, question: str, client) -> dict:
    def _classify():
        groq_client = Groq(api_key=settings.groq_api_key)
        return groq_call_with_retry(
            lambda: groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": CLASSIFICATION_PROMPT.format(question=question)}],
                response_format={"type": "json_object"},
                temperature=0,
            )
        ).choices[0].message.content

    text = (await asyncio.get_event_loop().run_in_executor(None, _classify)).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        classification = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"Classification JSON parse failed: {e}, defaulting to hybrid")
        classification = {"query_type": "hybrid", "structured_query": {}, "semantic_search_query": question}

    query_type = classification.get("query_type", "hybrid")
    structured_q = classification.get("structured_query", {})
    semantic_q = classification.get("semantic_search_query") or question

    structured_results = []
    semantic_results = []

    if query_type in ("structured", "hybrid"):
        _VALID_CATEGORIES = {"biomarker", "body_composition", "cardiovascular", "sleep", "nutrition", "activity", "subjective", "supplement"}
        metric_names = structured_q.get("metric_names") or []
        categories = [c for c in (structured_q.get("categories") or []) if c in _VALID_CATEGORIES]
        source = structured_q.get("source") or None
        date_range = structured_q.get("date_range") or {}
        aggregation = structured_q.get("aggregation") or "latest"

        if metric_names and aggregation == "latest" and not source:
            rows = await get_latest_metrics(client, user_id, metric_names)
        else:
            is_trend = aggregation == "trend"
            rows = await get_metrics(
                client,
                user_id,
                category=categories[0] if categories else None,
                metric_names=metric_names if metric_names else None,
                source=source,
                start_date=date_range.get("start"),
                end_date=date_range.get("end"),
                limit=500 if is_trend else 50,
                ascending=is_trend,
            )
        structured_results = rows

    if query_type in ("semantic", "hybrid"):
        try:
            source = structured_q.get("source") or None
            source_for_semantic = source if source else None

            hyde_passage = await _generate_hyde_passage(semantic_q)
            embedding = await generate_embedding(hyde_passage)

            match_count = 20 if source == "blood_test" else 12
            chunks = await semantic_search(
                client, user_id, embedding,
                match_threshold=0.55,
                match_count=match_count,
                source=source_for_semantic,
            )
            semantic_results = await _rerank(semantic_q, chunks)
        except Exception as e:
            logger.error(f"Semantic search failed: {e}", exc_info=True)

    return {
        "query_type": query_type,
        "classification": classification,
        "structured_results": structured_results,
        "semantic_results": semantic_results,
    }
