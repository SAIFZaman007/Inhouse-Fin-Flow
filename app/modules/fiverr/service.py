"""
app/modules/fiverr/service.py
════════════════════════════════════════════════════════════════════════════════
v10 — Enterprise Edition

Changes vs v9
─────────────
list_profiles_summary   NEW FIELDS — ``totalActiveOrders`` and
                          ``totalActiveOrderAmount`` in ``totals``
                            • ``totalActiveOrders``     = total count of order
                              records across all active profiles in the period.
                              Computed as len(p.orders) summed per profile — no
                              extra DB round-trip.
                            • ``totalActiveOrderAmount`` = Σ order.amount across
                              every order in the selected period for all active
                              profiles.  Summed in the same aggregation loop
                              that already computes t_revenue.

                          Also added ``activeOrders`` and ``activeOrderAmount``
                          to each per-profile ``periodTotals`` dict so the
                          single-profile breakdown is consistent with the
                          combined totals.

get_profile_detail      NEW FIELDS — ``activeOrders`` and ``activeOrderAmount``
                          in ``periodTotals``, scoped to a single profile.

Everything else is unchanged from v9.
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import io
import logging
import math
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from prisma import Prisma

from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from .schema import (
    FiverrOrderCreate,
    FiverrOrderUpdate,
    FiverrProfileCreate,
    FiverrProfileUpdate,
    FiverrSnapshotCreate,
)

logger = logging.getLogger(__name__)

_FIVERR_FEE = Decimal("0.20")
_AFTER_RATE = Decimal("1") - _FIVERR_FEE   # 0.80
_ZERO       = Decimal("0")

# Snapshot field names present on FiverrProfileUpdate (used for presence check)
_SNAPSHOT_FIELDS = frozenset({
    "available_withdraw",
    "not_cleared",
    "active_orders",
    "active_order_amount",
    "submitted",
    "withdrawn",
    "seller_plus",
    "promotion",
})


# ── Private helpers ───────────────────────────────────────────────────────────

def _d(v: Any) -> Decimal:
    return _ZERO if v is None else Decimal(str(v))


def _after_fee(amount: Any) -> Decimal:
    return (_d(amount) * _AFTER_RATE).quantize(Decimal("0.01"))


def _entry_to_dict(entry: Any, profile_name: str) -> dict:
    aw = _d(entry.availableWithdraw)
    return {
        "id":                        entry.id,
        "profileId":                 entry.profileId,
        "profileName":               profile_name,
        "date":                      entry.date.date() if isinstance(entry.date, datetime) else entry.date,
        "availableWithdraw":         float(aw),
        "availableWithdrawAfterFee": float(_after_fee(aw)),
        "notCleared":                float(_d(entry.notCleared)),
        "activeOrders":              entry.activeOrders,
        "activeOrderAmount":         float(_d(entry.activeOrderAmount)),
        "submitted":                 float(_d(entry.submitted)),
        "withdrawn":                 float(_d(entry.withdrawn)),
        "sellerPlus":                entry.sellerPlus,
        "promotion":                 float(_d(entry.promotion)),
        "createdAt":                 entry.createdAt,
    }


def _order_to_dict(order: Any) -> dict:
    return {
        "id":          order.id,
        "profileId":   order.profileId,
        "date":        order.date.date() if isinstance(order.date, datetime) else order.date,
        "buyerName":   order.buyerName,
        "orderId":     order.orderId,
        "amount":      float(_d(order.amount)),
        "afterFiverr": float(_d(order.afterFiverr)),
        "createdAt":   order.createdAt,
    }


def _pagination_meta(pagination: Optional[PageParams], total: int) -> dict:
    if pagination is None:
        return {"page": 1, "pageSize": total, "total": total, "totalPages": 1}
    return {
        "page":       pagination.page,
        "pageSize":   pagination.page_size,
        "total":      total,
        "totalPages": math.ceil(total / pagination.page_size) if total > 0 else 1,
    }


async def _get_profile_or_404(db: Prisma, profile_id: str):
    profile = await db.fiverrprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Fiverr profile not found.")
    return profile


async def _resolve_profile_by_name(db: Prisma, profile_name: str):
    profile = await db.fiverrprofile.find_first(
        where={
            "profileName": {"equals": profile_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Fiverr profile '{profile_name}' not found.",
        )
    return profile


# ── Profile CRUD ──────────────────────────────────────────────────────────────

async def create_profile(db: Prisma, data: FiverrProfileCreate) -> dict:
    existing = await db.fiverrprofile.find_unique(
        where={"profileName": data.profileName}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists.")

    profile = await db.fiverrprofile.create(
        data={"profileName": data.profileName}
    )

    snapshot: Optional[dict] = None
    if data.available_withdraw is not None:
        snap_date = data.snapshot_date or date.today()
        entry = await db.fiverrentry.upsert(
            where={"profileId_date": {
                "profileId": profile.id,
                "date":      datetime.combine(snap_date, time.min),
            }},
            data={
                "create": {
                    "profileId":         profile.id,
                    "date":              datetime.combine(snap_date, time.min),
                    "availableWithdraw": data.available_withdraw,
                    "notCleared":        data.not_cleared,
                    "activeOrders":      data.active_orders,
                    "activeOrderAmount": data.active_order_amount,
                    "submitted":         data.submitted,
                    "withdrawn":         data.withdrawn,
                    "sellerPlus":        data.seller_plus,
                    "promotion":         data.promotion,
                },
                "update": {
                    "availableWithdraw": data.available_withdraw,
                    "notCleared":        data.not_cleared,
                    "activeOrders":      data.active_orders,
                    "activeOrderAmount": data.active_order_amount,
                    "submitted":         data.submitted,
                    "withdrawn":         data.withdrawn,
                    "sellerPlus":        data.seller_plus,
                    "promotion":         data.promotion,
                },
            },
        )
        snapshot = _entry_to_dict(entry, profile.profileName)

    return {
        "id":              profile.id,
        "profileName":     profile.profileName,
        "isActive":        profile.isActive,
        "initialSnapshot": snapshot,
    }


async def update_profile(
    db: Prisma,
    profile_id: str,
    data: FiverrProfileUpdate,
) -> dict:
    """
    PATCH /profiles/{id} — partial profile update (v7).

    Handles two independent concerns in one atomic-ish call:

    1. Profile metadata  — rename (with uniqueness check) and/or isActive toggle.
    2. Snapshot upsert   — if any snapshot field is supplied, upsert the
                           FiverrEntry for ``snapshot_date`` (defaults to today).

    Returns the updated profile dict plus the upserted snapshot (if any).
    """
    profile = await _get_profile_or_404(db, profile_id)

    # ── 1. Profile metadata patch ─────────────────────────────────────────────
    profile_patch: dict = {}

    if data.profileName is not None and data.profileName != profile.profileName:
        conflict = await db.fiverrprofile.find_first(
            where={
                "profileName": {"equals": data.profileName, "mode": "insensitive"},
                "id":          {"not": profile_id},
            }
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Profile name '{data.profileName}' is already taken.",
            )
        profile_patch["profileName"] = data.profileName

    if data.isActive is not None:
        profile_patch["isActive"] = data.isActive

    if profile_patch:
        profile = await db.fiverrprofile.update(
            where={"id": profile_id},
            data=profile_patch,
        )

    # ── 2. Snapshot upsert (only when at least one snapshot field was sent) ───
    sent            = data.model_fields_set
    snapshot_fields = sent & _SNAPSHOT_FIELDS
    upserted_snapshot: Optional[dict] = None

    if snapshot_fields:
        snap_date = data.snapshot_date or date.today()

        # Fetch the existing entry (if any) to use as fallback for unsent fields
        existing_entry = await db.fiverrentry.find_unique(
            where={"profileId_date": {
                "profileId": profile_id,
                "date":      datetime.combine(snap_date, time.min),
            }}
        )

        # Build the upsert payload — fall back to existing values for unsent fields
        def _pick(field: str, existing_attr: str, default: Any) -> Any:
            """Return the new value if sent, else existing value, else default."""
            if field in sent:
                return getattr(data, field)
            if existing_entry is not None:
                return getattr(existing_entry, existing_attr)
            return default

        aw               = _pick("available_withdraw",  "availableWithdraw",  _ZERO)
        not_cleared      = _pick("not_cleared",         "notCleared",         _ZERO)
        active_orders    = _pick("active_orders",       "activeOrders",       0)
        active_order_amt = _pick("active_order_amount", "activeOrderAmount",  _ZERO)
        submitted        = _pick("submitted",           "submitted",          _ZERO)
        withdrawn        = _pick("withdrawn",           "withdrawn",          _ZERO)
        seller_plus      = _pick("seller_plus",         "sellerPlus",         False)
        promotion        = _pick("promotion",           "promotion",          _ZERO)

        entry_data = {
            "availableWithdraw": aw,
            "notCleared":        not_cleared,
            "activeOrders":      active_orders,
            "activeOrderAmount": active_order_amt,
            "submitted":         submitted,
            "withdrawn":         withdrawn,
            "sellerPlus":        seller_plus,
            "promotion":         promotion,
        }

        entry = await db.fiverrentry.upsert(
            where={"profileId_date": {
                "profileId": profile_id,
                "date":      datetime.combine(snap_date, time.min),
            }},
            data={
                "create": {"profileId": profile_id, "date": datetime.combine(snap_date, time.min), **entry_data},
                "update": entry_data,
            },
        )
        upserted_snapshot = _entry_to_dict(entry, profile.profileName)

    return {
        "id":               profile.id,
        "profileName":      profile.profileName,
        "isActive":         profile.isActive,
        "snapshotUpserted": upserted_snapshot,
    }


async def deactivate_profile(db: Prisma, profile_id: str) -> None:
    profile = await db.fiverrprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Fiverr profile not found.")
    await db.fiverrprofile.update(
        where={"id": profile_id}, data={"isActive": False}
    )


# ── Snapshot CRUD ─────────────────────────────────────────────────────────────

async def create_snapshot(db: Prisma, data: FiverrSnapshotCreate) -> dict:
    """
    POST /snapshots — additive daily snapshot (v9).

    Behaviour
    ─────────
    • First submission for (profileName, date)
        → INSERT the row with the incoming values as-is.
    • Subsequent submission for the same (profileName, date)
        → ADD the incoming numeric values to the existing stored values.
        → seller_plus uses OR semantics: once True for the day it stays True.

    This ensures that multiple HR inputs throughout the same day accumulate
    into a running total rather than silently overwriting previous entries.
    The response always reflects the current accumulated state of the row.
    """
    profile = await _resolve_profile_by_name(db, data.profile_name)

    snap_dt = datetime.combine(data.date, time.min)

    # ── Fetch existing row (if any) ───────────────────────────────────────────
    existing = await db.fiverrentry.find_unique(
        where={"profileId_date": {
            "profileId": profile.id,
            "date":      snap_dt,
        }}
    )

    if existing is None:
        # ── First entry for this (profile, date) — plain INSERT ───────────────
        entry = await db.fiverrentry.create(
            data={
                "profileId":         profile.id,
                "date":              snap_dt,
                "availableWithdraw": data.available_withdraw,
                "notCleared":        data.not_cleared,
                "activeOrders":      data.active_orders,
                "activeOrderAmount": data.active_order_amount,
                "submitted":         data.submitted,
                "withdrawn":         data.withdrawn,
                "sellerPlus":        data.seller_plus,
                "promotion":         data.promotion,
            }
        )
    else:
        # ── Row already exists — ADD (accumulate) the incoming values ─────────
        #
        # Numeric fields: new_total = existing + incoming
        # Boolean fields: OR semantics (True is sticky for the day)
        #
        new_aw          = _d(existing.availableWithdraw) + _d(data.available_withdraw)
        new_not_cleared = _d(existing.notCleared)        + _d(data.not_cleared)
        new_act_orders  = existing.activeOrders          + data.active_orders
        new_act_amt     = _d(existing.activeOrderAmount) + _d(data.active_order_amount)
        new_submitted   = _d(existing.submitted)         + _d(data.submitted)
        new_withdrawn   = _d(existing.withdrawn)         + _d(data.withdrawn)
        new_seller_plus = existing.sellerPlus            or data.seller_plus
        new_promotion   = _d(existing.promotion)         + _d(data.promotion)

        entry = await db.fiverrentry.update(
            where={"profileId_date": {
                "profileId": profile.id,
                "date":      snap_dt,
            }},
            data={
                "availableWithdraw": new_aw,
                "notCleared":        new_not_cleared,
                "activeOrders":      new_act_orders,
                "activeOrderAmount": new_act_amt,
                "submitted":         new_submitted,
                "withdrawn":         new_withdrawn,
                "sellerPlus":        new_seller_plus,
                "promotion":         new_promotion,
            },
        )

    return _entry_to_dict(entry, profile.profileName)


async def get_profile_snapshots(
    db: Prisma,
    profile_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)

    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter

    total   = await db.fiverrentry.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    entries = await db.fiverrentry.find_many(**find_kw)
    return {
        "profileId":   profile_id,
        "profileName": profile.profileName,
        "pagination":  _pagination_meta(pagination, total),
        "snapshots":   [_entry_to_dict(e, profile.profileName) for e in entries],
    }


# ── Order CRUD ────────────────────────────────────────────────────────────────

async def add_order(db: Prisma, data: FiverrOrderCreate) -> dict:
    profile = await _resolve_profile_by_name(db, data.profile_name)

    existing = await db.fiverrorder.find_unique(where={"orderId": data.order_id})
    if existing:
        raise HTTPException(status_code=409, detail="Order ID already exists.")

    order = await db.fiverrorder.create(
        data={
            "profileId":   profile.id,
            "date":        datetime.combine(data.date, time.min),
            "buyerName":   data.buyer_name,
            "orderId":     data.order_id,
            "amount":      data.amount,
            "afterFiverr": _after_fee(data.amount),
        }
    )
    return _order_to_dict(order)


async def update_order(
    db: Prisma,
    order_id: str,
    data: FiverrOrderUpdate,
) -> dict:
    order = await db.fiverrorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Fiverr order not found.")

    patch: dict = {}
    sent = data.model_fields_set

    if "date" in sent and data.date is not None:
        patch["date"] = datetime.combine(data.date, time.min)

    if data.buyer_name is not None:
        patch["buyerName"] = data.buyer_name

    if data.order_id is not None and data.order_id != order.orderId:
        conflict = await db.fiverrorder.find_unique(where={"orderId": data.order_id})
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Order ID '{data.order_id}' is already taken.",
            )
        patch["orderId"] = data.order_id

    if data.amount is not None:
        patch["amount"]      = data.amount
        patch["afterFiverr"] = _after_fee(data.amount)

    if not patch:
        return _order_to_dict(order)

    updated = await db.fiverrorder.update(where={"id": order_id}, data=patch)
    return _order_to_dict(updated)


async def get_profile_orders(
    db: Prisma,
    profile_id: str,
    date_filter: dict,
    pagination: Optional[PageParams] = None,
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)

    where: dict = {"profileId": profile_id}
    if date_filter:
        where["date"] = date_filter

    total   = await db.fiverrorder.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    orders = await db.fiverrorder.find_many(**find_kw)
    return {
        "profileId":   profile_id,
        "profileName": profile.profileName,
        "pagination":  _pagination_meta(pagination, total),
        "orders":      [_order_to_dict(o) for o in orders],
    }


# ── List / detail ─────────────────────────────────────────────────────────────

async def list_profiles_summary(
    db: Prisma,
    filters: DateRangeFilter,
    name: Optional[str] = None,
    pagination: Optional[PageParams] = None,
) -> dict:
    date_f = filters.to_prisma_filter()

    where: dict = {"isActive": True}
    if name:
        where["profileName"] = {"contains": name, "mode": "insensitive"}

    total_profiles = await db.fiverrprofile.count(where=where)

    find_kw: dict = dict(
        where=where,
        include={
            "entries": {
                "where":    {"date": date_f} if date_f else {},
                "order_by": {"date": "desc"},
            },
            "orders": {
                "where":    {"date": date_f} if date_f else {},
                "order_by": {"date": "desc"},
            },
        },
    )
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    profiles = await db.fiverrprofile.find_many(**find_kw)

    t_avail = t_not_cleared = t_act_amt = t_submitted = t_withdrawn = t_promotion = _ZERO
    t_active_orders    = 0
    t_active_order_amt = _ZERO                                           # v10: Σ order.amount
    t_revenue          = _ZERO

    summaries = []
    for p in profiles:
        latest = p.entries[0] if p.entries else None
        aw     = _d(latest.availableWithdraw) if latest else _ZERO

        t_avail        += aw
        t_not_cleared  += _d(latest.notCleared)        if latest else _ZERO
        t_act_amt      += _d(latest.activeOrderAmount)  if latest else _ZERO
        t_submitted    += _d(latest.submitted)          if latest else _ZERO
        t_withdrawn    += _d(latest.withdrawn)          if latest else _ZERO
        t_promotion    += _d(latest.promotion)          if latest else _ZERO

        period_revenue       = sum((_d(o.afterFiverr) for o in p.orders), _ZERO)
        period_order_count   = len(p.orders)                                     # v10
        period_order_amount  = sum((_d(o.amount)      for o in p.orders), _ZERO) # v10
        t_revenue           += period_revenue
        t_active_orders     += period_order_count                                # v10
        t_active_order_amt  += period_order_amount                               # v10

        period_totals = {
            "availableWithdraw":         float(aw),
            "availableWithdrawAfterFee": float(_after_fee(aw)),
            "notCleared":                float(_d(latest.notCleared)        if latest else _ZERO),
            "activeOrders":              period_order_count,                     # v10
            "activeOrderAmount":         float(period_order_amount),             # v10
            "submitted":                 float(_d(latest.submitted)          if latest else _ZERO),
            "withdrawn":                 float(_d(latest.withdrawn)          if latest else _ZERO),
            "promotion":                 float(_d(latest.promotion)          if latest else _ZERO),
            "revenueInPeriod":           float(period_revenue),
        }

        summaries.append({
            "id":              p.id,
            "profileName":     p.profileName,
            "isActive":        p.isActive,
            "latestSnapshot":  _entry_to_dict(latest, p.profileName) if latest else None,
            "periodTotals":    period_totals,
            "snapshotCount":   len(p.entries),
            "orderCount":      len(p.orders),
            "revenueInPeriod": float(period_revenue),
            "orders":          [_order_to_dict(o) for o in p.orders],
        })

    return {
        "filter": filters.meta(),
        "totals": {
            "totalAvailableWithdraw":         float(t_avail),
            "totalAvailableWithdrawAfterFee": float(_after_fee(t_avail)),
            "totalNotCleared":                float(t_not_cleared),
            "totalActiveOrders":              t_active_orders,                   # v10
            "totalActiveOrderAmount":         float(t_active_order_amt),         # v10
            "totalSubmitted":                 float(t_submitted),
            "totalWithdrawn":                 float(t_withdrawn),
            "totalPromotion":                 float(t_promotion),
            "totalRevenueInPeriod":           float(t_revenue),
            "activeProfileCount":             total_profiles,
        },
        "pagination": _pagination_meta(pagination, total_profiles),
        "profiles":   summaries,
    }


async def get_profile_detail(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
    pagination: Optional[PageParams] = None,
    name: Optional[str] = None,
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)

    # Optional name filter — 404 if profile exists but name doesn't match
    if name and name.lower() not in profile.profileName.lower():
        raise HTTPException(
            status_code=404,
            detail=f"Fiverr profile not found matching name '{name}'.",
        )

    date_f = filters.to_prisma_filter()

    snap_where:  dict = {"profileId": profile_id}
    order_where: dict = {"profileId": profile_id}
    if date_f:
        snap_where["date"]  = date_f
        order_where["date"] = date_f

    snap_total  = await db.fiverrentry.count(where=snap_where)
    order_total = await db.fiverrorder.count(where=order_where)

    snap_kw: dict  = dict(where=snap_where,  order={"date": "desc"})
    order_kw: dict = dict(where=order_where, order={"date": "desc"})
    if pagination:
        snap_kw["skip"]  = order_kw["skip"] = pagination.skip
        snap_kw["take"]  = order_kw["take"] = pagination.take

    entries = await db.fiverrentry.find_many(**snap_kw)
    orders  = await db.fiverrorder.find_many(**order_kw)

    latest             = entries[0] if entries else None
    aw                 = _d(latest.availableWithdraw) if latest else _ZERO
    revenue            = sum((_d(o.afterFiverr) for o in orders), _ZERO)
    active_order_count = len(orders)                                     # v10
    active_order_amt   = sum((_d(o.amount)      for o in orders), _ZERO) # v10

    return {
        "filter": filters.meta(),
        "profile": {
            "id":          profile.id,
            "profileName": profile.profileName,
            "isActive":    profile.isActive,
        },
        "periodTotals": {
            "availableWithdraw":         float(aw),
            "availableWithdrawAfterFee": float(_after_fee(aw)),
            "notCleared":                float(_d(latest.notCleared)        if latest else _ZERO),
            "activeOrders":              active_order_count,                     # v10
            "activeOrderAmount":         float(active_order_amt),               # v10
            "submitted":                 float(_d(latest.submitted)          if latest else _ZERO),
            "withdrawn":                 float(_d(latest.withdrawn)          if latest else _ZERO),
            "promotion":                 float(_d(latest.promotion)          if latest else _ZERO),
            "revenueInPeriod":           float(revenue),
            "snapshotCount":             snap_total,
            "orderCount":                order_total,
        },
        "pagination": _pagination_meta(pagination, max(snap_total, order_total)),
        "snapshots":  [_entry_to_dict(e, profile.profileName) for e in entries],
        "orders":     [_order_to_dict(o) for o in orders],
    }


# ── Excel export ──────────────────────────────────────────────────────────────

async def export_profile_excel(
    db: Prisma,
    profile_id: str,
    filters: DateRangeFilter,
) -> tuple[bytes, str]:
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="openpyxl not installed — cannot generate Excel export.",
        )

    detail   = await get_profile_detail(db, profile_id, filters)
    pname    = detail["profile"]["profileName"]
    start, end = filters.window()

    wb          = openpyxl.Workbook()
    HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
    HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
    ALT_FILL    = PatternFill("solid", fgColor="EBF3FB")

    def _header(ws, cols):
        for c, h in enumerate(cols, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.font      = HEADER_FONT
            cell.fill      = HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 20

    def _autofit(ws):
        for col in ws.columns:
            w = max((len(str(cell.value or "")) for cell in col), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 4, 40)

    # Sheet 1 — Snapshots
    ws1 = wb.active
    ws1.title = "Snapshots"
    _header(ws1, [
        "Date", "Available Withdraw ($)", "After Fee ($)", "Not Cleared ($)",
        "Active Orders", "Active Order Amount ($)", "Submitted ($)",
        "Withdrawn ($)", "Seller Plus", "Promotion ($)",
    ])
    for ri, s in enumerate(detail["snapshots"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(s["date"]),
            s["availableWithdraw"], s["availableWithdrawAfterFee"],
            s["notCleared"], s["activeOrders"], s["activeOrderAmount"],
            s["submitted"], s["withdrawn"], s["sellerPlus"], s["promotion"],
        ], 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws1)

    # Sheet 2 — Orders
    ws2 = wb.create_sheet("Orders")
    _header(ws2, ["Date", "Buyer", "Order ID", "Amount ($)", "After Fiverr ($)"])
    for ri, o in enumerate(detail["orders"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(o["date"]), o["buyerName"], o["orderId"],
            o["amount"], o["afterFiverr"],
        ], 1):
            cell = ws2.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws2)

    buf      = io.BytesIO()
    wb.save(buf)
    tag      = f"{start}_{end}" if start else "all"
    filename = f"fiverr_{pname.replace(' ', '_')}_{tag}.xlsx"
    return buf.getvalue(), filename