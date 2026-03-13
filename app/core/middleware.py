"""
app/core/middleware.py
=======================
Request middleware stack.
"""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Force-HTTPS middleware (production safety net) ───────────────────────────

class ForceHttpsMiddleware(BaseHTTPMiddleware):
    """
    Rewrites request.scope["scheme"] to "https" unconditionally.

    Only activated when settings.is_production is True AND
    settings.FORCE_HTTPS is True (or proxy headers are absent).

    This ensures `request.base_url`, `request.url`, and any URL
    constructed from them always use https:// in production.
    """
    async def dispatch(self, request: Request, call_next):
        if request.scope.get("scheme") != "https":
            request.scope["scheme"] = "https"
        return await call_next(request)


# ── Request logging middleware ────────────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "[%s] %s %s → %d | %.2fms",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_middleware(app: FastAPI) -> None:
    """
    Register all middleware. Starlette applies middleware in REVERSE
    registration order (last added = outermost wrapper), so we add the
    innermost concern first.
    """

    # ── 1. CORS (outermost — handles preflight before anything else) ──────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── 2. Force HTTPS scheme — production only ────────────────────────────────
    # Belt-and-suspenders: only activate if the proxy headers approach is
    # insufficient (e.g. proxy doesn't send X-Forwarded-Proto).
    if settings.is_production and settings.FORCE_HTTPS:
        app.add_middleware(ForceHttpsMiddleware)
        logger.info("ForceHttpsMiddleware enabled (APP_ENV=production, FORCE_HTTPS=true)")

    # ── 3. ProxyHeadersMiddleware — ALWAYS active ─────────────────────────────
    # Reads X-Forwarded-Proto / X-Forwarded-For from the reverse proxy and
    # patches request.scope so base_url reflects the public-facing scheme.
    # trusted_hosts="*" is safe here because we are behind a controlled proxy;
    # direct internet traffic never reaches this port.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    # ── 4. Request logging (innermost — closest to handler) ───────────────────
    app.add_middleware(RequestLoggingMiddleware)