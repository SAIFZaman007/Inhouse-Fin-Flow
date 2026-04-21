"""
app/modules/fiverr/schema.py
================================================================================
v3 — Enterprise Edition
================================================================================
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

class FiverrProfileCreate(BaseModel):
    """
    Create a new Fiverr profile.

    If any snapshot field is provided an initial snapshot is recorded
    immediately, seeding the ledger with the correct opening values.
    The service layer silently writes ``submitted = Decimal("0")`` to the
    DB column — this field is not surfaced to callers.
    """
    profileName: Optional[str] = Field(default=None, min_length=1, max_length=100)

    # ── Optional initial snapshot fields ─────────────────────────────────────
    snapshot_date:       Optional[date]    = Field(default=None, description="Date for the initial snapshot. Defaults to today.")
    available_withdraw:  Optional[Decimal] = Field(default=None, ge=0)
    not_cleared:         Optional[Decimal] = Field(default=None, ge=0)
    active_orders:       Optional[int]     = Field(default=None, ge=0)
    active_order_amount: Optional[Decimal] = Field(default=None, ge=0)
    withdrawn:           Optional[Decimal] = Field(default=None, ge=0)
    seller_plus:         bool              = Field(default=False)
    promotion:           Optional[Decimal] = Field(default=None, ge=0)


class FiverrProfileUpdate(BaseModel):
    """
    ``PATCH /profiles/{id}`` — partial update for a Fiverr profile.

    All fields are optional — only supplied fields are written.
    Sending an empty body ``{}`` is idempotent.

    ### Profile metadata
    ``profileName``  Renames the profile (uniqueness enforced server-side).
    ``isActive``     ``false`` soft-deletes; ``true`` restores a deactivated profile.

    ### Snapshot upsert fields
    When any snapshot field is supplied the service performs an **upsert**
    on the ``FiverrEntry`` for ``snapshot_date`` (defaults to today).
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
    withdrawn:           Optional[Decimal] = Field(default=None, ge=0)
    seller_plus:         Optional[bool]    = Field(default=None)
    promotion:           Optional[Decimal] = Field(default=None, ge=0)


class FiverrProfileResponse(BaseModel):
    """Lightweight profile row."""
    id:          str
    profileName: str
    isActive:    bool
    createdAt:   Optional[datetime] = None   # raw column — None before bootstrap
    updatedAt:   Optional[datetime] = None   # raw column — None before bootstrap

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot
# ─────────────────────────────────────────────────────────────────────────────

class FiverrSnapshotCreate(BaseModel):
    """
    ``POST /snapshots`` — additive daily snapshot.

    ### Accumulation behaviour
    | Condition                                     | Action                               |
    |-----------------------------------------------|--------------------------------------|
    | First submission for ``(profile_name, date)`` | INSERT with incoming values          |
    | Subsequent submission for the same pair        | ADD incoming values to stored values |

    Numeric fields accumulate; ``seller_plus`` uses OR semantics.
    ``profile_name`` is matched case-insensitively.

    All numeric snapshot fields are **optional** — omitted fields default to
    zero and do not affect any previously stored value.
    """
    profile_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Fiverr profile name (case-insensitive match).",
    )
    date:                date
    available_withdraw:  Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    not_cleared:         Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    active_orders:       Optional[int]     = Field(default=0, ge=0)
    active_order_amount: Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    withdrawn:           Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    seller_plus:         Optional[bool]    = Field(default=False)
    promotion:           Optional[Decimal] = Field(default=Decimal("0"), ge=0)


class FiverrSnapshotUpdate(BaseModel):
    """
    ``PATCH /snapshots/{id}`` — partial update for an existing daily snapshot.

    All fields are optional — only supplied fields are written (SET semantics,
    not additive accumulation).  This allows HR to correct a previously
    submitted snapshot without re-entering unrelated values.

    ``profile_name`` and ``date`` are intentionally excluded — they form the
    natural key and are immutable after creation.
    """
    available_withdraw:  Optional[Decimal] = Field(default=None, ge=0)
    not_cleared:         Optional[Decimal] = Field(default=None, ge=0)
    active_orders:       Optional[int]     = Field(default=None, ge=0)
    active_order_amount: Optional[Decimal] = Field(default=None, ge=0)
    withdrawn:           Optional[Decimal] = Field(default=None, ge=0)
    seller_plus:         Optional[bool]    = Field(default=None)
    promotion:           Optional[Decimal] = Field(default=None, ge=0)


class FiverrSnapshotResponse(BaseModel):
    """
    Full snapshot row — includes ``profileName`` for client convenience.

    ``submitted`` is intentionally excluded from API responses.
    """
    id:                 str
    profileId:          str
    profileName:        str
    date:               date
    availableWithdraw:  Decimal
    notCleared:         Decimal
    activeOrders:       int
    activeOrderAmount:  Decimal
    withdrawn:          Decimal
    sellerPlus:         bool
    promotion:          Decimal
    createdAt:          datetime
    updatedAt:          Optional[datetime] = None   # raw column — None before bootstrap

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

class FiverrOrderCreate(BaseModel):
    """
    ``POST /orders`` — log a new Fiverr order.

    ``profile_name`` is matched case-insensitively.

    ### ``after_fiverr`` — always system-computed
    The service always computes: ``after_fiverr = amount × 0.80``

    ### Automatic snapshot sync
    After the order is persisted the service additively updates the
    ``FiverrEntry`` for the same ``(profile_name, date)``:
    ```
    activeOrders      += 1
    activeOrderAmount += order.amount
    ```
    """
    profile_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Fiverr profile name (case-insensitive match).",
    )
    date:       date
    buyer_name: Optional[str]     = Field(default=None, min_length=1)
    order_id:   Optional[str]     = Field(default=None, min_length=1)
    amount:     Optional[Decimal] = Field(default=None, gt=0)


class FiverrOrderUpdate(BaseModel):
    """
    ``PATCH /orders/{id}`` — partial update for a Fiverr order.

    All fields are optional — only supplied fields are written.
    ``after_fiverr`` is always recomputed when ``amount`` is updated.
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
    updatedAt:   Optional[datetime] = None   # raw column — None before bootstrap

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Trash  (soft-delete registry)
# ─────────────────────────────────────────────────────────────────────────────

class FiverrTrashItem(BaseModel):
    """
    One soft-deleted record as stored in the trash registry.

    ``type``      ``"profile"`` | ``"snapshot"`` | ``"order"``
    ``snapshot``  Full record dict captured at deletion time.
    """
    id:        str
    module:    str
    type:      str
    deletedAt: str
    snapshot:  Dict[str, Any]


class FiverrTrashResponse(BaseModel):
    """Envelope for ``GET /trash``."""
    total:  int
    items:  List[FiverrTrashItem]


class FiverrRestoreRequest(BaseModel):
    """
    ``POST /restore-trash`` — restore one or more soft-deleted records.

    ``ids``  List of original DB primary keys to restore.
             Each ID must exist in the trash registry.
    """
    ids: List[str] = Field(..., min_length=1, description="List of trash record IDs to restore.")


class FiverrRestoreResponse(BaseModel):
    """Result envelope for ``POST /restore-trash``."""
    restored: List[str]
    failed:   List[str]
    message:  str


# ─────────────────────────────────────────────────────────────────────────────
# Combined-totals envelope  GET /profiles
# ─────────────────────────────────────────────────────────────────────────────

class FiverrTotals(BaseModel):
    """
    Cross-profile aggregate for the selected period.

    ``submitted`` is excluded — see module-level docstring.
    """
    totalAvailableWithdraw:  float
    totalNotCleared:         float
    totalActiveOrders:       int
    totalActiveOrderAmount:  float
    totalWithdrawn:          float
    totalPromotion:          float
    totalRevenueInPeriod:    float   # Σ afterFiverr in period
    totalOrderAmount:        float   # Σ order.amount in period
    activeProfileCount:      int


class FiverrProfileSummary(BaseModel):
    """Per-profile row in the list response."""
    id:              str
    profileName:     str
    isActive:        bool
    createdAt:       Optional[datetime] = None   # raw column
    updatedAt:       Optional[datetime] = None   # raw column
    latestSnapshot:  Optional[FiverrSnapshotResponse]
    periodTotals:    Dict[str, Any]
    snapshotCount:   int
    orderCount:      int
    revenueInPeriod: float
    orders:          List[FiverrOrderResponse]


class FiverrListResponse(BaseModel):
    """Top-level envelope for ``GET /profiles``."""
    filter:   Dict[str, Any]
    totals:   FiverrTotals
    profiles: List[FiverrProfileSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Single-profile detail  GET /profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────

class FiverrProfileDetailResponse(BaseModel):
    """Paginated snapshot + order list with profile metadata."""
    filter:       Dict[str, Any]
    profile:      FiverrProfileResponse
    periodTotals: Dict[str, Any]
    pagination:   Dict[str, Any]
    snapshots:    List[FiverrSnapshotResponse]
    orders:       List[FiverrOrderResponse]