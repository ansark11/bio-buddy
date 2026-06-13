import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.dependencies import get_current_user
from app.db.supabase_client import get_supabase_client
from app.db.queries import get_chat_history, get_chat_sessions, clear_chat_history
from app.models.chat import ChatRequest, ChatResponse
from app.services.rag import answer_question

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    try:
        result = await answer_question(user["user_id"], body.message, client, session_id=body.session_id)
        return ChatResponse(response=result["response"], sources=result["sources"])
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate response")


@router.get("/chat/sessions")
async def chat_sessions(user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    sessions = await get_chat_sessions(client, user["user_id"])
    return {"sessions": sessions}


@router.get("/chat/history")
async def chat_history(
    limit: int = 50,
    session_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    client = get_supabase_client()
    messages = await get_chat_history(client, user["user_id"], limit=limit, session_id=session_id)
    return {"messages": messages}


@router.delete("/chat/history")
async def delete_chat_history(user: dict = Depends(get_current_user)):
    client = get_supabase_client()
    await clear_chat_history(client, user["user_id"])
    return {"status": "cleared"}
