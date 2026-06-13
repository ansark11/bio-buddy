from __future__ import annotations
import asyncio
import logging
from uuid import UUID

import ollama

from app.config import settings
from app.db.queries import insert_document_chunks

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768


async def _call_with_retry(fn, max_retries: int = 3, base_delay: float = 1.0):
    for attempt in range(max_retries):
        try:
            return await asyncio.get_event_loop().run_in_executor(None, fn)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = base_delay * (2**attempt)
            logger.warning(f"Embedding attempt {attempt + 1} failed ({e}), retrying in {wait}s")
            await asyncio.sleep(wait)


async def generate_embedding(text: str) -> list[float]:
    client = ollama.Client(host=settings.ollama_base_url)

    def _embed():
        result = client.embed(model=EMBEDDING_MODEL, input=text)
        return result.embeddings[0]

    return await _call_with_retry(_embed)


def chunk_text(text: str, max_chars: int = 500, overlap: int = 50) -> list[str]:
    """Split free-form text into sentence-aware chunks."""
    sentences = []
    current = ""
    for part in text.replace("\n", " ").split(". "):
        part = part.strip()
        if not part:
            continue
        candidate = (current + ". " + part).strip() if current else part
        if len(candidate) > max_chars and current:
            sentences.append(current.strip())
            current = current[-overlap:] + ". " + part if len(current) > overlap else part
        else:
            current = candidate
    if current.strip():
        sentences.append(current.strip())
    return [s for s in sentences if s]


async def embed_and_store_chunks(
    client,
    document_id: str,
    text_chunks: list[str],
    user_id: UUID,
    source: str,
    metadata: dict | list[dict],
    embed_prefix: str = "",
) -> None:
    rows = []
    for idx, chunk_text_val in enumerate(text_chunks):
        if not chunk_text_val.strip():
            continue
        chunk_meta = metadata[idx] if isinstance(metadata, list) else metadata
        text_to_embed = (embed_prefix + chunk_text_val) if embed_prefix else chunk_text_val
        embedding = await generate_embedding(text_to_embed)
        rows.append(
            {
                "document_id": document_id,
                "chunk_text": chunk_text_val,
                "chunk_index": idx,
                "embedding": embedding,
                "source": source,
                "metadata": chunk_meta,
            }
        )

    await insert_document_chunks(client, user_id, rows)
    logger.info(f"Stored {len(rows)} chunks for document {document_id}")
