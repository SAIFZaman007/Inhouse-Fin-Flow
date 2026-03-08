"""
app/core/exceptions.py
========================
Centralised exception handlers — consistent JSON envelope for ALL responses.

Response shape:
    { "success": false, "message": "...", "detail": <optional> }
"""
import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prisma.errors import PrismaError

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    message: str,
    detail: object = None,
    headers: dict | None = None,
) -> JSONResponse:
    body: dict = {"success": False, "message": message}
    if detail is not None:
        body["detail"] = detail
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:

    # ── HTTPException ─────────────────────────────────────────────────────────
    # This handler was MISSING in the original code — all 401/403 from the auth
    # layer bypassed the envelope and returned FastAPI's raw {"detail": "..."} format.
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        _messages: dict[int, str] = {
            status.HTTP_400_BAD_REQUEST:           "Bad request.",
            status.HTTP_401_UNAUTHORIZED:          "Authentication required.",
            status.HTTP_403_FORBIDDEN:             "Access denied.",
            status.HTTP_404_NOT_FOUND:             "Resource not found.",
            status.HTTP_405_METHOD_NOT_ALLOWED:    "Method not allowed.",
            status.HTTP_409_CONFLICT:              "Conflict — resource already exists.",
            status.HTTP_422_UNPROCESSABLE_ENTITY:  "Validation failed.",
            status.HTTP_429_TOO_MANY_REQUESTS:     "Too many requests.",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "An unexpected error occurred.",
            status.HTTP_503_SERVICE_UNAVAILABLE:   "Service temporarily unavailable.",
        }
        message = _messages.get(exc.status_code, "An error occurred.")
        detail  = exc.detail if exc.detail != message else None
        headers = dict(exc.headers) if exc.headers else None
        return _error_response(exc.status_code, message, detail, headers)

    # ── RequestValidationError (422) ─────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = [
            {"field": " → ".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Validation failed. Please check your input.",
            errors,
        )

    # ── PrismaError ───────────────────────────────────────────────────────────
    @app.exception_handler(PrismaError)
    async def prisma_error_handler(request: Request, exc: PrismaError):
        logger.error("PrismaError on %s %s: %s", request.method, request.url.path, exc)
        msg = str(exc)

        # ── Unique constraint violation (409) ─────────────────────────────────
        if "Unique constraint" in msg:
            return _error_response(
                status.HTTP_409_CONFLICT,
                "A record with that value already exists.",
            )

        # ── Application-level record-not-found (404) ─────────────────────────
        # "Record to update not found." — update() on a missing row
        # "Record to delete does not exist." — delete() on a missing row
        # Both are app-logic errors → 404
        if "Record to update not found" in msg or "Record to delete does not exist" in msg:
            return _error_response(
                status.HTTP_404_NOT_FOUND,
                "The requested record was not found.",
            )

        # ── Infrastructure-level table missing (500) ──────────────────────────
        # "The table `public.X` does not exist in the current database."
        # This means the Prisma client was not regenerated after schema changes
        # (e.g. missing `enable_experimental_decimal = true` caused `prisma generate` to fail).
        # This is a server-side infra error → 500, and should surface clearly in logs.
        if "does not exist in the current database" in msg:
            logger.critical(
                "TABLE MISSING — Prisma client is out of sync with the database schema. "
                "Run: prisma generate && prisma migrate deploy. Error: %s", msg
            )
            return _error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "A database configuration error occurred. Please contact support.",
            )

        # ── Required related record not found (404) ───────────────────────────
        # "An operation failed because it depends on one or more records
        #  that were required but not found."
        if "depends on one or more records that were required but not found" in msg:
            return _error_response(
                status.HTTP_404_NOT_FOUND,
                "A required related record was not found.",
            )

        # ── Foreign key constraint (409) ──────────────────────────────────────
        if "Foreign key constraint" in msg:
            return _error_response(
                status.HTTP_409_CONFLICT,
                "Cannot complete the operation — a related record constraint was violated.",
            )

        # ── All other Prisma errors (500) ─────────────────────────────────────
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "A database error occurred.",
        )

    # ── Final safety net ──────────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "An unexpected error occurred.",
        )