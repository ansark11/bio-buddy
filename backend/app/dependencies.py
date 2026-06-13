from __future__ import annotations
import asyncio
import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from gotrue.errors import AuthRetryableError
from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    token = credentials.credentials
    client = get_supabase_client()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = client.auth.get_user(token)
            if not response or not response.user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
            return {"user_id": response.user.id, "email": response.user.email}
        except HTTPException:
            raise
        except AuthRetryableError as e:
            last_exc = e
            if attempt < 2:
                await asyncio.sleep(0.5)
            continue
        except Exception as e:
            logger.error(f"Auth error: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    logger.error(f"Auth retryable error after 3 attempts: {last_exc}", exc_info=True)
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service temporarily unavailable — retry the upload")
