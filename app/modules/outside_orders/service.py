"""
app/modules/outside_orders/service.py
================================================================================
v2 — Enterprise Edition
================================================================================
Key design decisions
────────────────────
• createdAt / updatedAt are native Prisma columns on OutsideOrder — no raw-SQL
  bootstrap is needed.  Both fields are returned directly from ORM objects.

• Search (``search`` param):
    Performs a case-insensitive OR search across BOTH ``orderDetails`` AND
    ``orderSheet`` columns simultaneously.  A single keyword matches either
    column.

• ``client_name`` filter:
    Case-insensitive partial match on ``clientName`` — mirroring the ``?name=``
    convention used across all other modules.

• ``order_status`` filter:
    Exact enum match: PENDING | IN_PROGRESS | COMPLETED | CANCELLED.

• Totals guarantee:
    totalOrders, totalOrderAmount, totalReceiveAmount, totalDueAmount and
    byStatus are computed across the FULL matching set before pagination is
    applied, so page 2+ always returns the same correct aggregates as page 1.
================================================================================
"""
from __future__ import annotations

import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from prisma import Prisma
from prisma.enums import OrderStatus

from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from .schema import OutsideOrderCreate, OutsideOrderUpdate

_ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _d(v: Any) -> Decimal:
    return _ZERO if v is None else Decimal(str(v))


def _to_dt(d: date) -> datetime:
    """Convert a bare date to midnight datetime — Prisma rejects bare dates."""
    if isinstance(d, datetime):
        return d
    return datetime.combine(d, time.min)


def _serialize(order: Any) -> dict:
    """ORM OutsideOrder → serialisable dict with all fields including timestamps."""
    return {
        "id":                  order.id,
        "date":                order.date.date() if isinstance(order.date, datetime) else order.date,
        "clientId":            order.clientId,
        "clientName":          order.clientName,
        "clientLink":          order.clientLink,
        "orderDetails":        order.orderDetails,
        "orderSheet":          order.orderSheet,
        "assignTeam":          order.assignTeam,
        "orderStatus":         order.orderStatus if isinstance(order.orderStatus, str) else order.orderStatus.value,
        "orderAmount":         _d(order.orderAmount),
        "receiveAmount":       _d(order.receiveAmount),
        "dueAmount":           _d(order.dueAmount),
        "paymentMethod":       order.paymentMethod,
        "paymentMethodDetails": order.paymentMethodDetails,
        "createdAt":           order.createdAt,   # native Prisma column
        "updatedAt":           order.updatedAt,   # native Prisma column (@updatedAt)
    }


def _pagination_meta(pagination: Optional[PageParams], total: int) -> dict:
    if pagination is None:
        return {"page": 1, "pageSize": total, "total": total, "totalPages": 1}
    page_size = pagination.page_size
    return {
        "page":       pagination.page,
        "pageSize":   page_size,
        "total":      total,
        "totalPages": math.ceil(total / page_size) if total > 0 else 1,
    }


def _empty_by_status() -> dict:
    return {
        "PENDING":     {"count": 0, "totalAmount": 0.0},
        "IN_PROGRESS": {"count": 0, "totalAmount": 0.0},
        "COMPLETED":   {"count": 0, "totalAmount": 0.0},
        "CANCELLED":   {"count": 0, "totalAmount": 0.0},
    }


def _build_where(
    date_filter:  Optional[dict],
    client_name:  Optional[str],
    search:       Optional[str],
    order_status: Optional[str],
) -> dict:
    """
    Build the Prisma ``where`` clause from all active filter parameters.

    ``client_name`` — case-insensitive partial match on ``clientName``.
    ``search``       — case-insensitive OR match on ``orderDetails`` OR
                       ``orderSheet``.  A single keyword matches either column.
    ``order_status`` — exact enum: PENDING | IN_PROGRESS | COMPLETED | CANCELLED.
    """
    where: dict = {}

    if date_filter:
        where["date"] = date_filter

    if client_name:
        where["clientName"] = {"contains": client_name, "mode": "insensitive"}

    if order_status:
        valid = {"PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
        normalised = order_status.upper()
        if normalised not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order_status '{order_status}'. "
                       f"Valid values: {', '.join(sorted(valid))}",
            )
        where["orderStatus"] = normalised

    if search:
        # OR search across orderDetails AND orderSheet simultaneously
        where["OR"] = [
            {"orderDetails": {"contains": search, "mode": "insensitive"}},
            {"orderSheet":   {"contains": search, "mode": "insensitive"}},
        ]

    return where


async def _get_order_or_404(db: Prisma, order_id: str):
    order = await db.outsideorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Outside order not found.")
    return order


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

async def create_order(db: Prisma, data: OutsideOrderCreate) -> dict:
    """
    POST /outside-orders — persist a new order.

    ``createdAt`` and ``updatedAt`` are set automatically by PostgreSQL /
    Prisma — no manual assignment required.
    """
    order = await db.outsideorder.create(
        data={
            "date":                _to_dt(data.date),
            "clientId":            data.clientId,
            "clientName":          data.clientName,
            "clientLink":          data.clientLink,
            "orderDetails":        data.orderDetails,
            "orderSheet":          data.orderSheet,
            "assignTeam":          data.assignTeam,
            "orderStatus":         data.orderStatus.value,
            "orderAmount":         data.orderAmount,
            "receiveAmount":       data.receiveAmount,
            "dueAmount":           data.dueAmount,
            "paymentMethod":       data.paymentMethod,
            "paymentMethodDetails": data.paymentMethodDetails,
        }
    )
    return _serialize(order)


async def get_order(db: Prisma, order_id: str) -> dict:
    """
    GET /outside-orders/{id} — return a single order by ID.

    Raises HTTP 404 if not found.
    ``createdAt`` and ``updatedAt`` are included in the response.
    """
    order = await _get_order_or_404(db, order_id)
    return _serialize(order)


async def update_order(db: Prisma, order_id: str, data: OutsideOrderUpdate) -> dict:
    """
    PATCH /outside-orders/{id} — partial update.

    Only fields present in ``data.model_fields_set`` are written to the DB.
    Sending an empty body is idempotent — the current row is returned unchanged.

    ``updatedAt`` is bumped automatically by Prisma's ``@updatedAt`` directive
    on every successful write — no manual timestamp management required.
    """
    order = await _get_order_or_404(db, order_id)

    patch: dict = {}
    sent = data.model_fields_set

    if "date" in sent and data.date is not None:
        patch["date"] = _to_dt(data.date)
    if "clientId" in sent and data.clientId is not None:
        patch["clientId"] = data.clientId
    if "clientName" in sent and data.clientName is not None:
        patch["clientName"] = data.clientName
    if "clientLink" in sent:
        patch["clientLink"] = data.clientLink          # may be None → explicit clear
    if "orderDetails" in sent and data.orderDetails is not None:
        patch["orderDetails"] = data.orderDetails
    if "orderSheet" in sent:
        patch["orderSheet"] = data.orderSheet           # may be None → explicit clear
    if "assignTeam" in sent:
        patch["assignTeam"] = data.assignTeam           # may be None → explicit clear
    if "orderStatus" in sent and data.orderStatus is not None:
        patch["orderStatus"] = data.orderStatus.value
    if "orderAmount" in sent and data.orderAmount is not None:
        patch["orderAmount"] = data.orderAmount
    if "receiveAmount" in sent and data.receiveAmount is not None:
        patch["receiveAmount"] = data.receiveAmount
    if "dueAmount" in sent and data.dueAmount is not None:
        patch["dueAmount"] = data.dueAmount
    if "paymentMethod" in sent:
        patch["paymentMethod"] = data.paymentMethod     # may be None → explicit clear
    if "paymentMethodDetails" in sent:
        patch["paymentMethodDetails"] = data.paymentMethodDetails

    # Idempotent — nothing changed
    if not patch:
        return _serialize(order)

    updated = await db.outsideorder.update(
        where={"id": order_id},
        data=patch,
    )
    return _serialize(updated)


async def delete_order(db: Prisma, order_id: str) -> None:
    """DELETE /outside-orders/{id} — hard delete."""
    order = await db.outsideorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Outside order not found.")
    await db.outsideorder.delete(where={"id": order_id})


# ─────────────────────────────────────────────────────────────────────────────
# List
# ─────────────────────────────────────────────────────────────────────────────

async def list_orders(
    db:           Prisma,
    filters:      DateRangeFilter,
    client_name:  Optional[str]      = None,
    search:       Optional[str]      = None,
    order_status: Optional[str]      = None,
    pagination:   Optional[PageParams] = None,
) -> dict:
    """
    GET /outside-orders — combined totals + paginated order list.

    Filters (all combinable)
    ────────────────────────
    ``client_name``  — case-insensitive partial match on ``clientName``.
    ``search``       — case-insensitive keyword search across BOTH
                       ``orderDetails`` AND ``orderSheet`` simultaneously
                       (OR logic — matches either column).
    ``order_status`` — exact enum: PENDING | IN_PROGRESS | COMPLETED | CANCELLED.
    Period params    — daily | weekly | monthly | yearly | all (default).

    Totals guarantee
    ────────────────
    Aggregates (totalOrderAmount, totalReceiveAmount, totalDueAmount, byStatus)
    are computed across the FULL matching set before pagination is applied,
    so values are stable across all pages.
    """
    date_filter = filters.to_prisma_filter()
    where       = _build_where(date_filter, client_name, search, order_status)

    # ── Full matching set — for stable cross-page totals ──────────────────────
    all_orders = await db.outsideorder.find_many(
        where=where,
        order={"date": "desc"},
    )

    total               = len(all_orders)
    t_order_amount      = _ZERO
    t_receive_amount    = _ZERO
    t_due_amount        = _ZERO
    by_status           = _empty_by_status()

    for o in all_orders:
        t_order_amount   += _d(o.orderAmount)
        t_receive_amount += _d(o.receiveAmount)
        t_due_amount     += _d(o.dueAmount)
        key = o.orderStatus if isinstance(o.orderStatus, str) else o.orderStatus.value
        if key in by_status:
            by_status[key]["count"]       += 1
            by_status[key]["totalAmount"] += float(_d(o.orderAmount))

    # ── Paginated slice ───────────────────────────────────────────────────────
    if pagination:
        page_orders = all_orders[pagination.skip: pagination.skip + pagination.take]
    else:
        page_orders = all_orders

    return {
        "filter": filters.meta(),
        "totals": {
            "totalOrders":        total,
            "totalOrderAmount":   float(t_order_amount),
            "totalReceiveAmount": float(t_receive_amount),
            "totalDueAmount":     float(t_due_amount),
            "byStatus":           by_status,
        },
        "pagination": _pagination_meta(pagination, total),
        "orders":     [_serialize(o) for o in page_orders],
    }