"""
app/modules/export/router.py
==============================
Excel export endpoints — one per module + a combined dashboard export.

All endpoints return application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
as a file download (Content-Disposition: attachment).

Period query param: daily | weekly | monthly | yearly
Optional: from / to (date override), export_date, year, month

Role enforcement mirrors the source module:
  Dashboard        → ALL_ROLES
  Fiverr           → HR_AND_ABOVE  (HR, CEO, DIRECTOR — not BDev)
  Upwork           → HR_AND_ABOVE
  Payoneer         → CEO_DIRECTOR
  PMAK             → PMAK_EDITORS  (all roles including BDev)
  Outside Orders   → HR_AND_ABOVE
  Dollar Exchange  → CEO_DIRECTOR
  Card Sharing     → CEO_DIRECTOR  (sensitive module)
  HR Expense       → HR_AND_ABOVE
  Inventory        → HR_AND_ABOVE
"""
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import (
    ALL_ROLES, CEO_DIRECTOR, HR_AND_ABOVE, PMAK_EDITORS,
)

from .schema import ExportQueryParams
from .service import (
    export_card_sharing,
    export_dashboard,
    export_dollar_exchange,
    export_fiverr,
    export_hr_expense,
    export_inventory,
    export_outside_orders,
    export_payoneer,
    export_pmak,
    export_upwork,
)

router = APIRouter(prefix="/export", tags=["Export"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx_response(data: bytes, filename: str) -> Response:
    """Wrap raw bytes in a proper Excel download response."""
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get(
    "/dashboard",
    summary="Export dashboard summary (multi-sheet Excel)",
    response_description="Excel workbook with one sheet per module",
)
async def export_dashboard_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    data, filename = await export_dashboard(db, params)
    return _xlsx_response(data, filename)


# ── Fiverr ────────────────────────────────────────────────────────────────────

@router.get("/fiverr", summary="Export Fiverr snapshots to Excel")
async def export_fiverr_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    data, filename = await export_fiverr(db, params)
    return _xlsx_response(data, filename)


# ── Upwork ────────────────────────────────────────────────────────────────────

@router.get("/upwork", summary="Export Upwork snapshots to Excel")
async def export_upwork_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    data, filename = await export_upwork(db, params)
    return _xlsx_response(data, filename)


# ── Payoneer ──────────────────────────────────────────────────────────────────

@router.get("/payoneer", summary="Export Payoneer transactions to Excel")
async def export_payoneer_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_payoneer(db, params)
    return _xlsx_response(data, filename)


# ── PMAK ──────────────────────────────────────────────────────────────────────

@router.get(
    "/pmak",
    summary="Export PMAK transactions to Excel (BDev accessible)",
)
async def export_pmak_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    data, filename = await export_pmak(db, params)
    return _xlsx_response(data, filename)


# ── Outside Orders ────────────────────────────────────────────────────────────

@router.get("/outside-orders", summary="Export outside orders to Excel")
async def export_outside_orders_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    data, filename = await export_outside_orders(db, params)
    return _xlsx_response(data, filename)


# ── Dollar Exchange ───────────────────────────────────────────────────────────

@router.get("/dollar-exchange", summary="Export dollar exchange records to Excel")
async def export_dollar_exchange_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_dollar_exchange(db, params)
    return _xlsx_response(data, filename)


# ── Card Sharing ──────────────────────────────────────────────────────────────

@router.get(
    "/card-sharing",
    summary="Export card sharing records to Excel (sensitive fields excluded)",
)
async def export_card_sharing_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_card_sharing(db, params)
    return _xlsx_response(data, filename)


# ── HR Expense ────────────────────────────────────────────────────────────────

@router.get("/hr-expense", summary="Export HR expenses to Excel")
async def export_hr_expense_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    data, filename = await export_hr_expense(db, params)
    return _xlsx_response(data, filename)


# ── Inventory ─────────────────────────────────────────────────────────────────

@router.get("/inventory", summary="Export inventory items to Excel")
async def export_inventory_endpoint(
    params: ExportQueryParams = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    data, filename = await export_inventory(db, params)
    return _xlsx_response(data, filename)