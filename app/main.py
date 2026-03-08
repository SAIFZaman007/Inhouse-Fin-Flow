"""
app/main.py
============
Application factory.

FIXES in this version vs previous:
  1. Health router imported and registered — /health now comes from
     app/core/router.py, not a closure inside create_app(). This keeps
     the factory clean and the health endpoints testable in isolation.

  2. validate_security_config() called in lifespan (unchanged from v7) —
     never at import time.

  3. Root GET / added as a proper welcome/redirect endpoint.
"""
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import connect_db, disconnect_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import setup_middleware
from app.core.security import validate_security_config

# ── Module Routers ────────────────────────────────────────────────────────────
from app.modules.health.router import router as health_router
from app.modules.auth.router import router as auth_router
from app.modules.card_sharing.router import router as card_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.dollar_exchange.router import router as exchange_router
from app.modules.export.router import router as export_router
from app.modules.fiverr.router import router as fiverr_router
from app.modules.hr_expense.router import router as hr_router
from app.modules.inventory.router import router as inventory_router
from app.modules.outside_orders.router import router as outside_router
from app.modules.payoneer.router import router as payoneer_router
from app.modules.pmak.router import router as pmak_router
from app.modules.upwork.router import router as upwork_router
from app.modules.users.router import router as users_router

# ── Windows: ProactorEventLoop ────────────────────────────────────────────────
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

settings = get_settings()
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:  validate config → connect DB.
    Shutdown: disconnect DB.
    """
    validate_security_config()
    await connect_db()
    yield
    await disconnect_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="MAKTech Financial Flow API",
        description=(
            "Enterprise finance management system for MAKTech outsourcing company.\n\n"
            "---\n\n"
            "## How to Authenticate\n\n"
            "1. **POST** `/api/v1/auth/login` — get your `access_token`.\n"
            "2. Click **Authorize 🔒** above → paste the token → click **Authorize**.\n"
            "3. **GET** `/api/v1/auth/verify` — confirms the server accepts your token.\n\n"
            "> **Note:** Swagger's **'Authorized'** badge only means the token is "
            "*stored in the browser*. It does **not** mean the server validated it. "
            "Always use `/auth/verify` to confirm."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    setup_middleware(app)
    register_exception_handlers(app)

    # ── Health endpoints (no prefix — must be reachable at /health) ──────────
    app.include_router(health_router)

    # ── API v1 endpoints ──────────────────────────────────────────────────────
    API_PREFIX = "/api/v1"
    for router in [
        auth_router, users_router, dashboard_router,
        fiverr_router, upwork_router, payoneer_router,
        pmak_router, outside_router, exchange_router,
        card_router, hr_router, inventory_router, export_router,
    ]:
        app.include_router(router, prefix=API_PREFIX)

    # ── Root route ────────────────────────────────────────────────────────────
    @app.get("/", tags=["Health"], include_in_schema=False)
    async def root():
        return JSONResponse({
            "service": settings.APP_NAME,
            "version": "1.0.0",
            "docs":    "/docs",
            "health":  "Healthy!!",
            "ready":   "TRUE. Ready for action!!",
        })

    return app


app = create_app()