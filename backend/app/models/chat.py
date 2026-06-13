from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatSource(BaseModel):
    type: str  # "chunk" | "metric"
    content: str
    metadata: dict = {}


class ChatResponse(BaseModel):
    response: str
    sources: list[ChatSource] = []


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    sources: list = []
    created_at: datetime
