"""
app/core/router.py  (Health endpoints)
========================================
IMPORTANT FIX vs previous version:
  The old /health handler opened a NEW Prisma connection on every health-check
  call (every 30 seconds). This:
    1. Created unnecessary TCP connections to the query-engine binary
    2. Could leave dangling connections if the health-check was interrupted
    3. Made the health endpoint SLOW (connection overhead ~50-100ms)
    4. Would fail if the DB was momentarily unavailable, causing Coolify to
       mark the container unhealthy and roll back a perfectly working deploy

  NEW behaviour:
    - /health is a LIVENESS probe — it only checks if the process is running.
      It returns 200 immediately without touching the DB. Coolify uses this
      to decide if the container should be killed and restarted.

    - /health/ready is a READINESS probe — it checks the DB connection using
      the already-connected global client (not a new connection). Use this
      endpoint if you need to verify the full stack is healthy.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from prisma import Prisma

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "/health",
    summary="Liveness probe",
    description=(
        "Lightweight liveness probe used by Coolify's HEALTHCHECK. "
        "Returns 200 immediately — does NOT check the database. "
        "If this endpoint is slow or returns non-200, the container is restarted."
    ),
)
async def health_liveness():
    """
    Liveness probe — is the process alive and the event loop responsive?
    Zero I/O. Must return in < 10ms at all times including during migrations.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": settings.APP_NAME,
            "version": "1.0.0",
        },
    )


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description=(
        "Full readiness probe — checks DB connectivity via the live Prisma client. "
        "Returns 200 when the application is fully ready to serve traffic. "
        "Returns 503 if the database is unreachable."
    ),
)
async def health_readiness(db: Prisma = Depends(get_db)):
    """
    Readiness probe — reuses the existing Prisma connection (no new connection).
    Use this to verify the full stack before routing traffic to a new instance.
    """
    try:
        # Lightest possible query — single round-trip, no table scan
        await db.execute_raw("SELECT 1")
        db_status = "connected"
        http_status = 200
    except Exception as exc:
        db_status = f"unreachable: {exc}"
        http_status = 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ready" if http_status == 200 else "degraded",
            "service": settings.APP_NAME,
            "database": db_status,
        },
    )