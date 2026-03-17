"""
app/modules/upwork/service.py
════════════════════════════════════════════════════════════════════════════════
v7 — Enterprise Edition

Changes vs v6
─────────────
update_profile   EXTENDED — PATCH /profiles/{id}
                   Now accepts the full snapshot field set from UpworkProfileUpdate.
                   When any snapshot field is present the service upserts today's
                   (or snapshot_date's) UpworkEntry in the same call, so callers
                   never need a separate POST /snapshots round-trip.

Everything else is unchanged from v6.
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
    UpworkOrderCreate,
    UpworkOrderUpdate,
    UpworkProfileCreate,
    UpworkProfileUpdate,
    UpworkSnapshotCreate,
)

logger = logging.getLogger(__name__)

_UPWORK_FEE = Decimal("0.10")
_AFTER_RATE = Decimal("1") - _UPWORK_FEE   # 0.90
_ZERO       = Decimal("0")

# Snapshot field names present on UpworkProfileUpdate (used for presence check)
_SNAPSHOT_FIELDS = frozenset({
    "available_withdraw",
    "pending",
    "in_review",
    "work_in_progress",
    "withdrawn",
    "connects",
    "upwork_plus",
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
        "pending":                   float(_d(entry.pending)),
        "inReview":                  float(_d(entry.inReview)),
        "workInProgress":            float(_d(entry.workInProgress)),
        "withdrawn":                 float(_d(entry.withdrawn)),
        "connects":                  entry.connects,
        "upworkPlus":                entry.upworkPlus,
        "createdAt":                 entry.createdAt,
    }


def _order_to_dict(order: Any) -> dict:
    return {
        "id":          order.id,
        "profileId":   order.profileId,
        "date":        order.date.date() if isinstance(order.date, datetime) else order.date,
        "clientName":  order.clientName,
        "orderId":     order.orderId,
        "amount":      float(_d(order.amount)),
        "afterUpwork": float(_d(order.afterUpwork)),
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
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found.")
    return profile


async def _resolve_profile_by_name(db: Prisma, profile_name: str):
    profile = await db.upworkprofile.find_first(
        where={
            "profileName": {"equals": profile_name, "mode": "insensitive"},
            "isActive":    True,
        }
    )
    if not profile:
        raise HTTPException(
            status_code=404,
            detail=f"Upwork profile '{profile_name}' not found.",
        )
    return profile


# ── Profile CRUD ──────────────────────────────────────────────────────────────

async def create_profile(db: Prisma, data: UpworkProfileCreate) -> dict:
    existing = await db.upworkprofile.find_unique(
        where={"profileName": data.profileName}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Profile name already exists.")

    profile = await db.upworkprofile.create(
        data={"profileName": data.profileName}
    )

    snapshot: Optional[dict] = None
    if data.available_withdraw is not None:
        snap_date = data.snapshot_date or date.today()
        entry = await db.upworkentry.upsert(
            where={"profileId_date": {
                "profileId": profile.id,
                "date":      datetime.combine(snap_date, time.min),
            }},
            data={
                "create": {
                    "profileId":        profile.id,
                    "date":             datetime.combine(snap_date, time.min),
                    "availableWithdraw": data.available_withdraw,
                    "pending":          data.pending,
                    "inReview":         data.in_review,
                    "workInProgress":   data.work_in_progress,
                    "withdrawn":        data.withdrawn,
                    "connects":         data.connects,
                    "upworkPlus":       data.upwork_plus,
                },
                "update": {
                    "availableWithdraw": data.available_withdraw,
                    "pending":          data.pending,
                    "inReview":         data.in_review,
                    "workInProgress":   data.work_in_progress,
                    "withdrawn":        data.withdrawn,
                    "connects":         data.connects,
                    "upworkPlus":       data.upwork_plus,
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
    data: UpworkProfileUpdate,
) -> dict:
    """
    PATCH /profiles/{id} — partial profile update (v7).

    Handles two independent concerns in one atomic-ish call:

    1. Profile metadata  — rename (with uniqueness check) and/or isActive toggle.
    2. Snapshot upsert   — if any snapshot field is supplied, upsert the
                           UpworkEntry for ``snapshot_date`` (defaults to today).

    Returns the updated profile dict plus the upserted snapshot (if any).
    """
    profile = await _get_profile_or_404(db, profile_id)

    # ── 1. Profile metadata patch ─────────────────────────────────────────────
    profile_patch: dict = {}

    if data.profileName is not None and data.profileName != profile.profileName:
        conflict = await db.upworkprofile.find_first(
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
        profile = await db.upworkprofile.update(
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
        existing_entry = await db.upworkentry.find_unique(
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

        aw              = _pick("available_withdraw", "availableWithdraw", _ZERO)
        pending         = _pick("pending",            "pending",           _ZERO)
        in_review       = _pick("in_review",          "inReview",          _ZERO)
        work_in_progress= _pick("work_in_progress",   "workInProgress",    _ZERO)
        withdrawn       = _pick("withdrawn",           "withdrawn",         _ZERO)
        connects        = _pick("connects",            "connects",          0)
        upwork_plus     = _pick("upwork_plus",         "upworkPlus",        False)

        entry_data = {
            "availableWithdraw": aw,
            "pending":           pending,
            "inReview":          in_review,
            "workInProgress":    work_in_progress,
            "withdrawn":         withdrawn,
            "connects":          connects,
            "upworkPlus":        upwork_plus,
        }

        entry = await db.upworkentry.upsert(
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
    profile = await db.upworkprofile.find_unique(where={"id": profile_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Upwork profile not found.")
    await db.upworkprofile.update(
        where={"id": profile_id}, data={"isActive": False}
    )


# ── Snapshot CRUD ─────────────────────────────────────────────────────────────

async def create_snapshot(db: Prisma, data: UpworkSnapshotCreate) -> dict:
    profile = await _resolve_profile_by_name(db, data.profile_name)

    entry = await db.upworkentry.upsert(
        where={"profileId_date": {
            "profileId": profile.id,
            "date":      datetime.combine(data.date, time.min),
        }},
        data={
            "create": {
                "profileId":        profile.id,
                "date":             datetime.combine(data.date, time.min),
                "availableWithdraw": data.available_withdraw,
                "pending":          data.pending,
                "inReview":         data.in_review,
                "workInProgress":   data.work_in_progress,
                "withdrawn":        data.withdrawn,
                "connects":         data.connects,
                "upworkPlus":       data.upwork_plus,
            },
            "update": {
                "availableWithdraw": data.available_withdraw,
                "pending":          data.pending,
                "inReview":         data.in_review,
                "workInProgress":   data.work_in_progress,
                "withdrawn":        data.withdrawn,
                "connects":         data.connects,
                "upworkPlus":       data.upwork_plus,
            },
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

    total   = await db.upworkentry.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    entries = await db.upworkentry.find_many(**find_kw)
    return {
        "profileId":   profile_id,
        "profileName": profile.profileName,
        "pagination":  _pagination_meta(pagination, total),
        "snapshots":   [_entry_to_dict(e, profile.profileName) for e in entries],
    }


# ── Order CRUD ────────────────────────────────────────────────────────────────

async def add_order(db: Prisma, data: UpworkOrderCreate) -> dict:
    profile = await _resolve_profile_by_name(db, data.profile_name)

    existing = await db.upworkorder.find_unique(where={"orderId": data.order_id})
    if existing:
        raise HTTPException(status_code=409, detail="Order ID already exists.")

    order = await db.upworkorder.create(
        data={
            "profileId":  profile.id,
            "date":       datetime.combine(data.date, time.min),
            "clientName": data.client_name,
            "orderId":    data.order_id,
            "amount":     data.amount,
            "afterUpwork": _after_fee(data.amount),
        }
    )
    return _order_to_dict(order)


async def update_order(
    db: Prisma,
    order_id: str,
    data: UpworkOrderUpdate,
) -> dict:
    order = await db.upworkorder.find_unique(where={"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Upwork order not found.")

    patch: dict = {}
    sent = data.model_fields_set

    if "date" in sent and data.date is not None:
        patch["date"] = datetime.combine(data.date, time.min)

    if data.client_name is not None:
        patch["clientName"] = data.client_name

    if data.order_id is not None and data.order_id != order.orderId:
        conflict = await db.upworkorder.find_unique(where={"orderId": data.order_id})
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Order ID '{data.order_id}' is already taken.",
            )
        patch["orderId"] = data.order_id

    if data.amount is not None:
        patch["amount"]     = data.amount
        patch["afterUpwork"] = _after_fee(data.amount)

    if not patch:
        return _order_to_dict(order)

    updated = await db.upworkorder.update(where={"id": order_id}, data=patch)
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

    total   = await db.upworkorder.count(where=where)
    find_kw = dict(where=where, order={"date": "desc"})
    if pagination:
        find_kw["skip"] = pagination.skip
        find_kw["take"] = pagination.take

    orders = await db.upworkorder.find_many(**find_kw)
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

    total_profiles = await db.upworkprofile.count(where=where)

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

    profiles = await db.upworkprofile.find_many(**find_kw)

    t_avail = t_pending = t_in_review = t_wip = t_withdrawn = _ZERO
    t_connects = 0
    t_revenue  = _ZERO

    summaries = []
    for p in profiles:
        latest = p.entries[0] if p.entries else None
        aw     = _d(latest.availableWithdraw) if latest else _ZERO

        t_avail     += aw
        t_pending   += _d(latest.pending)        if latest else _ZERO
        t_in_review += _d(latest.inReview)       if latest else _ZERO
        t_wip       += _d(latest.workInProgress) if latest else _ZERO
        t_withdrawn += _d(latest.withdrawn)      if latest else _ZERO
        t_connects  += latest.connects            if latest else 0

        period_revenue = sum((_d(o.afterUpwork) for o in p.orders), _ZERO)
        t_revenue     += period_revenue

        period_totals = {
            "availableWithdraw":         float(aw),
            "availableWithdrawAfterFee": float(_after_fee(aw)),
            "pending":                   float(_d(latest.pending)        if latest else _ZERO),
            "inReview":                  float(_d(latest.inReview)       if latest else _ZERO),
            "workInProgress":            float(_d(latest.workInProgress) if latest else _ZERO),
            "withdrawn":                 float(_d(latest.withdrawn)      if latest else _ZERO),
            "connects":                  latest.connects                  if latest else 0,
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
            "totalPending":                   float(t_pending),
            "totalInReview":                  float(t_in_review),
            "totalWorkInProgress":            float(t_wip),
            "totalWithdrawn":                 float(t_withdrawn),
            "totalConnects":                  t_connects,
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
) -> dict:
    profile = await _get_profile_or_404(db, profile_id)
    date_f  = filters.to_prisma_filter()

    snap_where:  dict = {"profileId": profile_id}
    order_where: dict = {"profileId": profile_id}
    if date_f:
        snap_where["date"]  = date_f
        order_where["date"] = date_f

    snap_total  = await db.upworkentry.count(where=snap_where)
    order_total = await db.upworkorder.count(where=order_where)

    snap_kw: dict  = dict(where=snap_where,  order={"date": "desc"})
    order_kw: dict = dict(where=order_where, order={"date": "desc"})
    if pagination:
        snap_kw["skip"]  = order_kw["skip"] = pagination.skip
        snap_kw["take"]  = order_kw["take"] = pagination.take

    entries = await db.upworkentry.find_many(**snap_kw)
    orders  = await db.upworkorder.find_many(**order_kw)

    latest  = entries[0] if entries else None
    aw      = _d(latest.availableWithdraw) if latest else _ZERO
    revenue = sum((_d(o.afterUpwork) for o in orders), _ZERO)

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
            "pending":                   float(_d(latest.pending)        if latest else _ZERO),
            "inReview":                  float(_d(latest.inReview)       if latest else _ZERO),
            "workInProgress":            float(_d(latest.workInProgress) if latest else _ZERO),
            "withdrawn":                 float(_d(latest.withdrawn)      if latest else _ZERO),
            "connects":                  latest.connects                  if latest else 0,
            "revenueInPeriod":           float(revenue),
            "snapshotCount":             snap_total,
            "orderCount":               order_total,
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
        "Date", "Available Withdraw ($)", "After Fee ($)", "Pending ($)",
        "In Review ($)", "Work in Progress ($)", "Withdrawn ($)",
        "Connects", "Upwork Plus",
    ])
    for ri, s in enumerate(detail["snapshots"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(s["date"]),
            s["availableWithdraw"], s["availableWithdrawAfterFee"],
            s["pending"], s["inReview"], s["workInProgress"],
            s["withdrawn"], s["connects"], s["upworkPlus"],
        ], 1):
            cell = ws1.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws1)

    # Sheet 2 — Orders
    ws2 = wb.create_sheet("Orders")
    _header(ws2, ["Date", "Client", "Order ID", "Amount ($)", "After Upwork ($)"])
    for ri, o in enumerate(detail["orders"], 2):
        fill = ALT_FILL if ri % 2 == 0 else None
        for ci, v in enumerate([
            str(o["date"]), o["clientName"], o["orderId"],
            o["amount"], o["afterUpwork"],
        ], 1):
            cell = ws2.cell(row=ri, column=ci, value=v)
            if fill:
                cell.fill = fill
    _autofit(ws2)

    buf      = io.BytesIO()
    wb.save(buf)
    tag      = f"{start}_{end}" if start else "all"
    filename = f"upwork_{pname.replace(' ', '_')}_{tag}.xlsx"
    return buf.getvalue(), filename