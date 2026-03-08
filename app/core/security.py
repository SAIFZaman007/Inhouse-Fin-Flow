"""
app/core/security.py
=====================
DEPENDENCY REQUIRED (run once):
  poetry remove python-jose
  poetry add "PyJWT[crypto]"

ROOT CAUSE FIX — hot-reload worker crash:
  The previous version had two module-level RuntimeError traps:
    - if not settings.SECRET_KEY → raise RuntimeError     ← ran at IMPORT TIME
    - Fernet(settings.FERNET_KEY) in try/except           ← ran at IMPORT TIME

  On Windows, uvicorn's hot-reload spawns a NEW subprocess for each reload.
  That subprocess imports security.py at module level BEFORE any lifespan
  or setup functions run. If .env resolution fails even momentarily in the
  subprocess working directory, Settings() raises ValidationError → RuntimeError
  fires → worker crashes → /openapi.json returns 404 → Swagger shows
  "Failed to load API definition."

  FIX: All startup validation is now inside validate_security_config() which
  is called explicitly from the lifespan in main.py — NEVER at import time.
  The module itself is always safe to import regardless of environment state.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt  # PyJWT — NOT python-jose
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from .config import get_settings

settings = get_settings()


# ─── Custom Token Exceptions ──────────────────────────────────────────────────
class TokenError(Exception):
    """Base for all token errors."""

class TokenExpiredError(TokenError):
    """Token is structurally valid but its exp timestamp has passed."""

class TokenInvalidError(TokenError):
    """Bad signature, garbage input, missing claims, wrong algorithm, etc."""


# ─── Password Hashing ─────────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ─── JWT ──────────────────────────────────────────────────────────────────────
_ALGORITHM: str   = settings.ALGORITHM  # "HS256"
_ALLOWED_ALGS     = [_ALGORITHM]        # explicit allowlist — blocks alg:none attacks


def validate_security_config() -> None:
    """
    Validate SECRET_KEY and FERNET_KEY at application startup.

    Called from lifespan() in main.py — deliberately NOT at module import time.
    This prevents the worker from crashing during hot-reload on Windows when
    the subprocess environment hasn't fully resolved the .env path yet.

    Raises RuntimeError with a clear, actionable message on misconfiguration.
    """
    # ── Validate SECRET_KEY ───────────────────────────────────────────────────
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY is missing or too short (minimum 32 characters). "
            "Set a strong value in your .env file.\n"
            "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # ── Validate FERNET_KEY ───────────────────────────────────────────────────
    try:
        Fernet(settings.FERNET_KEY.encode())
    except Exception as exc:
        raise RuntimeError(
            f"FERNET_KEY is missing or invalid: {exc}\n"
            "Generate one: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ) from exc


def _make_token(
    data: dict,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        **data,
        "type": token_type,
        "iat":  now,
        "exp":  now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)


def create_access_token(data: dict) -> str:
    return _make_token(
        data, "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(data: dict) -> str:
    return _make_token(
        data, "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    Fully verify a JWT — signature, expiry, algorithm, required claims.
    Raises TokenExpiredError or TokenInvalidError. Never raises anything else.
    Authentication paths can never produce an unhandled 500 from this function.
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise TokenInvalidError("Token must be a non-empty string.")

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=_ALLOWED_ALGS,
            options={
                "verify_signature": True,  # explicit — never disabled
                "verify_exp":       True,
                "verify_iat":       True,
                "require":          ["exp", "iat", "sub", "type"],
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise TokenInvalidError(f"Token is invalid: {exc}") from exc
    except Exception as exc:
        # Belt-and-suspenders: no unexpected error can bubble as 500
        raise TokenInvalidError(f"Token could not be processed: {exc}") from exc

    return payload


# ─── Fernet (Encryption at Rest) ─────────────────────────────────────────────
# Lazy-initialised — _fernet is None until first actual encrypt/decrypt call.
# validate_security_config() (run at lifespan startup) guarantees the key is
# valid before any real encrypt/decrypt is ever attempted. The lazy init means
# this module is always safe to import.
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(settings.FERNET_KEY.encode())
    return _fernet


def encrypt_value(plain: str) -> str:
    """Encrypt a sensitive value (card number, CVC) before storing in the DB."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """
    Decrypt a sensitive value from the DB.
    Raises ValueError clearly if the value is corrupted or the key has changed.
    """
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "Decryption failed — the value may be corrupted or was encrypted "
            "with a different FERNET_KEY."
        ) from exc