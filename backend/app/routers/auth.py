import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


class AuthRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str


@router.post("/auth/signup", response_model=AuthResponse)
async def signup(body: AuthRequest):
    client = get_supabase_client()
    try:
        response = client.auth.sign_up({"email": body.email, "password": body.password})
        if not response.user:
            raise HTTPException(status_code=400, detail="Signup failed")
        session = response.session
        if not session:
            raise HTTPException(status_code=400, detail="Signup succeeded but no session returned — check email confirmation settings")
        return AuthResponse(
            access_token=session.access_token,
            user_id=response.user.id,
            email=response.user.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/auth/login", response_model=AuthResponse)
async def login(body: AuthRequest):
    client = get_supabase_client()
    try:
        response = client.auth.sign_in_with_password({"email": body.email, "password": body.password})
        if not response.user or not response.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return AuthResponse(
            access_token=response.session.access_token,
            user_id=response.user.id,
            email=response.user.email,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Invalid credentials")
