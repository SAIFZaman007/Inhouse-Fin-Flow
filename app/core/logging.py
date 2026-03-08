"""
app/core/logging.py
====================
Structured logging — quiet third-party libraries, keep our code and
uvicorn startup messages fully visible.

IMPORTANT: uvicorn.error must NEVER be silenced below WARNING.
The new subprocess worker launched during hot-reload logs its startup errors
(including import failures) through uvicorn.error BEFORE our setup_logging()
runs. If those messages are suppressed, the real crash reason is invisible
and the only visible output is the asyncio CancelledError noise from the
old worker's teardown — completely masking the actual problem.
"""
import logging
import sys

from .config import get_settings

settings = get_settings()


def setup_logging() -> None:
    # ── Root logger: WARNING — third-party libs quiet by default ─────────────
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # override any prior basicConfig calls (e.g. from libraries)
    )

    # ── Our application code: verbose in dev, INFO in prod ───────────────────
    app_level = logging.DEBUG if settings.APP_ENV == "development" else logging.INFO
    logging.getLogger("app").setLevel(app_level)

    # ── Silence genuinely noisy libraries ────────────────────────────────────
    _silence_to_error = [
        "uvicorn.access",      # per-request access log (we use our own middleware)
        "uvicorn.lifespan",    # internal lifespan machinery
        "fastapi",
        "starlette",
        "prisma",
        "prisma.http",
        "httpx",
        "httpcore",
        "httpcore.http11",
        "httpcore.connection",
        "aiosmtplib",
        "asyncio",
        "multipart",
        "python_multipart",
    ]
    for name in _silence_to_error:
        logging.getLogger(name).setLevel(logging.ERROR)

    # ── Keep uvicorn startup/error messages visible ───────────────────────────
    # uvicorn.error carries:
    #   - "Application startup complete." / "Shutdown complete."
    #   - Import errors and RuntimeErrors from new worker subprocesses
    #   - Any exception that prevents the app from starting after a hot-reload
    # These MUST remain at WARNING so they appear in the terminal.
    # Setting this to ERROR would hide the real cause of hot-reload crashes.
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)