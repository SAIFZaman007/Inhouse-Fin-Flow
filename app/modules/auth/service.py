"""
app/modules/auth/service.py
============================
Authentication business logic.
"""
from fastapi import HTTPException, status
from prisma import Prisma

from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


async def login(db: Prisma, email: str, password: str) -> dict:
    user = await db.user.find_unique(where={"email": email})
    # Always run verify_password even if user not found — prevents timing attacks
    if not user or not verify_password(password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been disabled. Contact administrator.",
        )
    payload = {"sub": user.id, "role": user.role, "email": user.email}
    return {
        "access_token":  create_access_token(payload),
        "refresh_token": create_refresh_token(payload),
    }


async def refresh_tokens(db: Prisma, refresh_token: str) -> dict:
    try:
        payload = decode_token(refresh_token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
        )
    except (TokenInvalidError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

    user = await db.user.find_unique(where={"id": payload["sub"]})
    if not user or not user.isActive:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

    new_payload = {"sub": user.id, "role": user.role, "email": user.email}
    return {
        "access_token":  create_access_token(new_payload),
        "refresh_token": create_refresh_token(new_payload),
    }


async def change_password(
    db: Prisma,
    user_id: str,
    current_password: str,
    new_password: str,
) -> None:
    user = await db.user.find_unique(where={"id": user_id})
    if not user or not verify_password(current_password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    await db.user.update(
        where={"id": user_id},
        data={"passwordHash": hash_password(new_password)},
    )