"""
app/modules/fiverr/schema.py
════════════════════════════════════════════════════════════════════════════════
v1 — Enterprise Edition

Pydantic models for the Fiverr module.

FiverrSnapshotCreate  POST /snapshots — additive daily snapshot.
                        ``active_order_amount`` maps to the DB column
                        ``activeOrderAmount``.  ``active_orders`` is the
                        integer count of active orders.

FiverrOrderCreate     POST /orders — log a new Fiverr order.
                        ``after_fiverr`` is ALWAYS server-computed as
                        ``amount × 0.80`` (Fiverr's 20 % platform fee).
                        Any caller-supplied value is ignored.
                        After persisting the order the service additively
                        syncs the snapshot for the same (profile, date):
                          activeOrders      += 1
                          activeOrderAmount += order.amount

FiverrProfileCreate / FiverrProfileUpdate  — profile lifecycle management.

FiverrOrderUpdate     — partial update; all fields optional.
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

class FiverrProfileCreate(BaseModel):
    """
    Create a new Fiverr profile.

    If ``available_withdraw`` is provided, an initial snapshot is recorded
    immediately, seeding the ledger with the correct opening values.
    """
    profileName:       str               = Field(..., min_length=1, max_length=100)
    # Optional initial snapshot fields
    snapshot_date:     Optional[date]    = Field(
        default=None,
        description="Date for the initial snapshot. Defaults to today.",
    )
    available_withdraw: Optional[Decimal] = Field(default=None, ge=0)
    not_cleared:        Optional[Decimal] = Field(default=None, ge=0)
    active_orders:      Optional[int]     = Field(default=None, ge=0)
    active_order_amount: Optional[Decimal] = Field(default=None, ge=0)
    submitted:          Optional[Decimal] = Field(default=None, ge=0)
    withdrawn:          Optional[Decimal] = Field(default=None, ge=0)
    seller_plus:        bool              = Field(default=False)
    promotion:          Optional[Decimal] = Field(default=None, ge=0)


class FiverrProfileUpdate(BaseModel):
    """
    PATCH /profiles/{id} — partial update for a Fiverr profile.

    All fields are optional — only supplied fields are written.

    ### Profile metadata
    ``profileName``  Renames the profile (uniqueness enforced server-side).
    ``isActive``     ``false`` soft-deletes; ``true`` restores a deactivated profile.

    ### Snapshot upsert fields
    When any snapshot field is supplied the service performs an **upsert**
    on the ``FiverrEntry`` for ``snapshot_date`` (defaults to today).

    Sending an empty body ``{}`` is idempotent.
    """
    # ── Profile metadata ──────────────────────────────────────────────────────
    profileName: Optional[str]  = Field(default=None, min_length=1, max_length=100)
    isActive:    Optional[bool] = Field(default=None)

    # ── Snapshot upsert fields ────────────────────────────────────────────────
    snapshot_date:       Optional[date]    = Field(default=None)
    available_withdraw:  Optional[Decimal] = Field(default=None, ge=0)
    not_cleared:         Optional[Decimal] = Field(default=None, ge=0)
    active_orders:       Optional[int]     = Field(default=None, ge=0)
    active_order_amount: Optional[Decimal] = Field(default=None, ge=0)
    submitted:           Optional[Decimal] = Field(default=None, ge=0)
    withdrawn:           Optional[Decimal] = Field(default=None, ge=0)
    seller_plus:         Optional[bool]    = Field(default=None)
    promotion:           Optional[Decimal] = Field(default=None, ge=0)


class FiverrProfileResponse(BaseModel):
    """Lightweight profile row."""
    id:          str
    profileName: str
    isActive:    bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot
# ─────────────────────────────────────────────────────────────────────────────

class FiverrSnapshotCreate(BaseModel):
    """
    POST /snapshots — additive daily snapshot.

    ### Accumulation behaviour
    • First submission for ``(profile_name, date)``  → INSERT with incoming values.
    • Subsequent submission for the same pair         → ADD incoming values to stored
      values (numeric fields accumulate; ``seller_plus`` uses OR semantics).

    ``profile_name``  Human-readable profile name (case-insensitive lookup).
    """
    profile_name:        str             = Field(
        ..., min_length=1, max_length=100,
        description="Fiverr profile name (case-insensitive match).",
    )
    date:                date
    available_withdraw:  Decimal         = Field(default=Decimal("0"), ge=0)
    not_cleared:         Decimal         = Field(default=Decimal("0"), ge=0)
    active_orders:       int             = Field(default=0, ge=0)
    active_order_amount: Decimal         = Field(default=Decimal("0"), ge=0)
    submitted:           Decimal         = Field(default=Decimal("0"), ge=0)
    withdrawn:           Decimal         = Field(default=Decimal("0"), ge=0)
    seller_plus:         bool            = Field(default=False)
    promotion:           Decimal         = Field(default=Decimal("0"), ge=0)


class FiverrSnapshotResponse(BaseModel):
    """Full snapshot row — includes ``profileName`` for client convenience."""
    id:                 str
    profileId:          str
    profileName:        str
    date:               date
    availableWithdraw:  Decimal
    notCleared:         Decimal
    activeOrders:       int
    activeOrderAmount:  Decimal
    submitted:          Decimal
    withdrawn:          Decimal
    sellerPlus:         bool
    promotion:          Decimal
    createdAt:          datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

class FiverrOrderCreate(BaseModel):
    """
    POST /orders — log a new Fiverr order.

    ``profile_name``  Human-readable profile name (case-insensitive lookup).

    ``after_fiverr`` behaviour  (system-computed, always)
    ──────────────────────────────────────────────────────
    This field is NOT accepted from the caller.  The service always computes:
        after_fiverr = amount × 0.80
    (Fiverr charges a 20 % platform fee on all orders.)

    ### Automatic snapshot sync
    After the order is persisted the service additively updates the
    ``FiverrEntry`` for the same ``(profile_name, date)``:
        activeOrders      += 1
        activeOrderAmount += order.amount
    The snapshot is upserted if it doesn't yet exist for that date.
    """
    profile_name: str     = Field(
        ..., min_length=1, max_length=100,
        description="Fiverr profile name (case-insensitive match).",
    )
    date:         date
    buyer_name:   str     = Field(..., min_length=1)
    order_id:     str     = Field(..., min_length=1)
    amount:       Decimal = Field(..., gt=0)


class FiverrOrderUpdate(BaseModel):
    """
    PATCH /orders/{id} — partial update for a Fiverr order.

    All fields are optional — only supplied fields are written.
    ``after_fiverr`` is always recomputed when ``amount`` is updated.

    Sending an empty body ``{}`` is idempotent.
    """
    date:       date
    buyer_name: Optional[str]     = Field(default=None, min_length=1)
    order_id:   Optional[str]     = Field(default=None, min_length=1)
    amount:     Optional[Decimal] = Field(default=None, gt=0)


class FiverrOrderResponse(BaseModel):
    """Full order row."""
    id:          str
    profileId:   str
    date:        date
    buyerName:   str
    orderId:     str
    amount:      Decimal
    afterFiverr: Decimal
    createdAt:   datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Combined-totals envelope  GET /profiles
# ─────────────────────────────────────────────────────────────────────────────

class FiverrTotals(BaseModel):
    """Cross-profile aggregate for the selected period."""
    totalAvailableWithdraw:  float
    totalNotCleared:         float
    totalActiveOrders:       int
    totalActiveOrderAmount:  float
    totalSubmitted:          float
    totalWithdrawn:          float
    totalPromotion:          float
    totalRevenueInPeriod:    float   # Σ afterFiverr in period
    totalOrderAmount:        float   # Σ order.amount in period
    activeProfileCount:      int


class FiverrProfileSummary(BaseModel):
    """Per-profile row in the list response."""
    id:                str
    profileName:       str
    isActive:          bool
    latestSnapshot:    Optional[FiverrSnapshotResponse]
    periodTotals:      Dict[str, Any]
    snapshotCount:     int
    orderCount:        int
    revenueInPeriod:   float
    orders:            List[FiverrOrderResponse]


class FiverrListResponse(BaseModel):
    """Top-level envelope for GET /profiles."""
    filter:   Dict[str, Any]
    totals:   FiverrTotals
    profiles: List[FiverrProfileSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Single-profile detail  GET /profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────

class FiverrProfileDetailResponse(BaseModel):
    """Paginated snapshot + order list with profile metadata."""
    filter:        Dict[str, Any]
    profile:       FiverrProfileResponse
    periodTotals:  Dict[str, Any]
    pagination:    Dict[str, Any]
    snapshots:     List[FiverrSnapshotResponse]
    orders:        List[FiverrOrderResponse]