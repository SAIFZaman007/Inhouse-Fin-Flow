"""
app/modules/outside_orders/router.py
========================================
v2 — Additions:
  • GET /outside-orders   — new query params: client_name, assign_team
  • GET /outside-orders/export — dedicated Excel export (replaces export module route)

Role matrix:
  GET  (list / detail)  → HR_AND_ABOVE
  POST                  → HR_AND_ABOVE
  PATCH                 → HR_AND_ABOVE
  DELETE                → CEO_DIRECTOR
  GET  /export          → HR_AND_ABOVE
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter

from .schema import OutsideOrderCreate, OutsideOrderResponse, OutsideOrderUpdate
from .service import (
    create_order, delete_order, export_orders,
    get_order, list_orders, update_order,
)

router = APIRouter(prefix="/outside-orders", tags=["Outside Orders"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[OutsideOrderResponse])
async def get_orders(
    status:      Optional[str] = Query(default=None, description="Filter by order status (e.g. PENDING, COMPLETED)"),
    client_name: Optional[str] = Query(default=None, description="Partial / case-insensitive match on client name"),
    assign_team: Optional[str] = Query(default=None, description="Partial / case-insensitive match on assigned team"),
    filters:     DateRangeFilter = Depends(),
    db:          Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    List outside orders with optional filters.

    All filters are combinable:
    - `status`       — exact enum match (PENDING | COMPLETED | …)
    - `client_name`  — case-insensitive substring search
    - `assign_team`  — case-insensitive substring search
    - Date filters   — period (daily/weekly/monthly/yearly) or explicit from/to
    """
    return await list_orders(
        db,
        date_filter=filters.to_prisma_filter(),
        status=status,
        client_name=client_name,
        assign_team=assign_team,
    )


# ── Export ────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export outside orders to Excel (.xlsx)",
    response_description="Excel workbook download",
)
async def export_orders_endpoint(
    status:      Optional[str] = Query(default=None, description="Filter by order status"),
    client_name: Optional[str] = Query(default=None, description="Partial match on client name"),
    assign_team: Optional[str] = Query(default=None, description="Partial match on assigned team"),
    filters:     DateRangeFilter = Depends(),
    db:          Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    """
    Export filtered outside orders to an Excel file.

    Supports the same filters as GET /outside-orders.
    Period query (daily/weekly/monthly/yearly/all) or explicit from/to date range.

    Returns Content-Disposition: attachment with a dated filename.
    """
    meta     = filters.meta()
    date_str = (meta["dateRange"]["from"] or "all").replace("-", "")
    label    = f"outside_orders_{date_str}"

    data, filename = await export_orders(
        db,
        date_filter=filters.to_prisma_filter(),
        status=status,
        client_name=client_name,
        assign_team=assign_team,
        label=label,
    )
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=OutsideOrderResponse, status_code=201)
async def add_order(
    body: OutsideOrderCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_order(db, body)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{order_id}", response_model=OutsideOrderResponse)
async def get_order_detail(
    order_id: str,
    db:       Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_order(db, order_id)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{order_id}", response_model=OutsideOrderResponse)
async def update_order_endpoint(
    order_id: str,
    body:     OutsideOrderUpdate,
    db:       Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_order(db, order_id, body)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{order_id}", status_code=204)
async def delete_order_endpoint(
    order_id: str,
    db:       Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_order(db, order_id)