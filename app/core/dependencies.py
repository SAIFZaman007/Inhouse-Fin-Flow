"""
app/core/dependencies.py
==========================
FastAPI dependency injection — authentication & RBAC.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prisma import Prisma
from prisma.models import User

from .database import get_db
from .security import TokenExpiredError, TokenInvalidError, decode_token

_bearer_scheme = HTTPBearer(auto_error=True)
_WWW_BEARER    = "Bearer"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Prisma = Depends(get_db),
) -> User:
    """
    Authenticate the request. Every failure path → 401. Never 500.

    Steps:
      1. Cryptographically verify JWT (signature, expiry, required claims)
      2. Enforce token type = 'access' (blocks refresh tokens being misused)
      3. Verify user still exists in DB (handles deleted-after-issue edge case)
      4. Verify account is active (403 — identity confirmed, access revoked)
    """
    # ── 1. Decode & verify JWT ────────────────────────────────────────────────
    try:
        payload = decode_token(credentials.credentials)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": f'{_WWW_BEARER} error="invalid_token"'},
        )
    except (TokenInvalidError, Exception):
        # Intentionally vague — do not leak why verification failed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": _WWW_BEARER},
        )

    # ── 2. Enforce token type (prevents refresh-token-as-access-token attack) ─
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": _WWW_BEARER},
        )

    # ── 3. Validate sub claim ─────────────────────────────────────────────────
    user_id: str | None = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": _WWW_BEARER},
        )

    # ── 4. Confirm user exists in DB ──────────────────────────────────────────
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": _WWW_BEARER},
        )

    # ── 5. Confirm account is active ──────────────────────────────────────────
    if not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact your administrator.",
        )

    return user


def require_roles(*roles: str):
    """RBAC dependency factory. Returns the authenticated user on success."""
    async def _role_guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(roles)}.",
            )
        return current_user
    return _role_guard


# ─── Convenience Role Guards ──────────────────────────────────────────────────
CEO_ONLY     = require_roles("CEO")
CEO_DIRECTOR = require_roles("CEO", "DIRECTOR")
ALL_ROLES    = require_roles("CEO", "DIRECTOR", "HR")