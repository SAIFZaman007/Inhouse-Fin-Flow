"""
app/modules/auth/router.py
===========================
Authentication endpoints.

Endpoints:
  POST /auth/login           — Obtain access + refresh tokens
  POST /auth/refresh         — Exchange refresh token for new token pair
  GET  /auth/me              — Current user info (requires valid access token)
  GET  /auth/verify          — Lightweight server-side token probe (requires valid access token)
  POST /auth/change-password — Change own password (requires valid access token)
"""
from fastapi import APIRouter, Depends
from prisma import Prisma
from prisma.models import User

from app.core.database import get_db
from app.core.dependencies import get_current_user

from .schema import ChangePasswordRequest, LoginRequest, MeResponse, RefreshRequest, TokenResponse
from .service import change_password, login, refresh_tokens

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login — obtain access & refresh tokens",
)
async def login_endpoint(body: LoginRequest, db: Prisma = Depends(get_db)):
    return await login(db, body.email, body.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh — exchange refresh token for a new token pair",
)
async def refresh_endpoint(body: RefreshRequest, db: Prisma = Depends(get_db)):
    return await refresh_tokens(db, body.refresh_token)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Me — get current authenticated user's profile",
)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get(
    "/verify",
    summary="Verify — confirm your token is genuinely valid on the server",
    description=(
        "A lightweight, zero-side-effect endpoint that validates your access token "
        "server-side and returns your identity.\n\n"
        "**Use this after clicking Authorize in Swagger** to confirm the server "
        "actually accepts your token — Swagger's 'Authorized' badge only means "
        "the token is stored in the browser, NOT that the server has validated it.\n\n"
        "- ✅ **200** — token is valid, returns your identity\n"
        "- ❌ **401** — token is invalid, expired, or missing\n"
        "- ❌ **403** — token is valid but account is disabled"
    ),
)
async def verify_token(current_user: User = Depends(get_current_user)):
    """
    Server-side token probe. Returns 200 + identity if token is valid, 401 if not.
    This is the correct way to test authentication — NOT Swagger's Authorize dialog,
    which only stores the token client-side without any server validation.
    """
    return {
        "valid":    True,
        "id":       current_user.id,
        "email":    current_user.email,
        "name":     current_user.name,
        "role":     current_user.role,
        "isActive": current_user.isActive,
    }


@router.post(
    "/change-password",
    summary="Change your own password",
)
async def change_password_endpoint(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Prisma = Depends(get_db),
):
    await change_password(db, current_user.id, body.current_password, body.new_password)
    return {"success": True, "message": "Password changed successfully."}