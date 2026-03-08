"""
app/core/database.py
=====================
Prisma client management.

ARCHITECTURE NOTE — why a global singleton:
  prisma-client-py maintains one long-lived async TCP connection to the
  query-engine binary. Connecting on every request adds ~5-10ms overhead
  per call and can exhaust PostgreSQL's connection limit under load.

  The global singleton pattern is the recommended approach for single-worker
  deployments (which is what we use — see Dockerfile CMD comment on --workers).

FORK SAFETY:
  If you ever move to multiple uvicorn workers (--workers N), replace the
  global singleton with a per-worker lifespan that stores the client in
  app.state, and pass it via request.app.state in get_db(). The current
  pattern is intentionally kept simple for the single-worker model.
"""
from prisma import Prisma

_client: Prisma | None = None


async def connect_db() -> None:
    """Called once at application startup (lifespan)."""
    global _client
    if _client is not None and _client.is_connected():
        return  # idempotent — safe to call twice
    _client = Prisma()
    await _client.connect()


async def disconnect_db() -> None:
    """Called once at application shutdown (lifespan)."""
    global _client
    if _client is not None:
        try:
            if _client.is_connected():
                await _client.disconnect()
        finally:
            _client = None


async def get_db() -> Prisma:
    """
    FastAPI dependency — yields the shared Prisma client.

    Raises RuntimeError if called before lifespan startup (shouldn't happen
    in normal operation, but gives a clear message during test setup errors).
    """
    if _client is None or not _client.is_connected():
        raise RuntimeError(
            "Database client is not connected. "
            "Ensure connect_db() completed successfully in the lifespan startup."
        )
    return _client