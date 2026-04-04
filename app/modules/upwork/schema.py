"""
app/modules/upwork/schema.py
════════════════════════════════════════════════════════════════════════════════
v10 — Enterprise Edition
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# ── Fee constant (mirrors service.py — keep in sync) ─────────────────────────
_UPWORK_FEE = Decimal("0.10")


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

class UpworkProfileCreate(BaseModel):
    """
    Create a new Upwork profile.

    If ``available_withdraw`` is supplied, an initial snapshot is recorded
    for ``snapshot_date`` (defaults to today).
    """
    profileName: Optional[str] = Field(default=None, min_length=1, max_length=100)

    # Optional initial-snapshot fields ───────────────────────────────────────
    snapshot_date:      Optional[date]    = Field(default=None, description="Defaults to today.")
    available_withdraw: Optional[Decimal] = Field(default=None, ge=0, description="Seeds an initial snapshot.")
    pending:            Decimal           = Field(default=Decimal("0"), ge=0)
    in_review:          Decimal           = Field(default=Decimal("0"), ge=0)
    work_in_progress:   Decimal           = Field(default=Decimal("0"), ge=0)
    withdrawn:          Decimal           = Field(default=Decimal("0"), ge=0)
    connects:           int               = Field(default=0, ge=0)
    upwork_plus:        bool              = False


class UpworkProfileUpdate(BaseModel):
    """
    PATCH /profiles/{id} — partial update for an Upwork profile.

    All fields are optional — only supplied fields are written.

    Profile identity fields
    ───────────────────────
    ``profileName``  Renames the profile (uniqueness enforced server-side).
    ``isActive``     ``false`` soft-deletes; ``true`` restores a deactivated profile.

    Snapshot fields  (v7 addition)
    ──────────────────────────────
    When any snapshot field is supplied the service performs an **upsert** on
    today's snapshot (or ``snapshot_date`` if provided).
    """
    # ── Profile metadata ─────────────────────────────────────────────────────
    profileName: Optional[str]  = Field(default=None, min_length=1, max_length=100)
    isActive:    Optional[bool] = Field(
        default=None,
        description="Set false to soft-delete; true to restore a deactivated profile.",
    )

    # ── Snapshot fields (v7) ─────────────────────────────────────────────────
    snapshot_date:      Optional[date]    = Field(
        default=None,
        description="Date for the snapshot upsert. Defaults to today when any snapshot field is supplied.",
    )
    available_withdraw: Optional[Decimal] = Field(default=None, ge=0)
    pending:            Optional[Decimal] = Field(default=None, ge=0)
    in_review:          Optional[Decimal] = Field(default=None, ge=0)
    work_in_progress:   Optional[Decimal] = Field(default=None, ge=0)
    withdrawn:          Optional[Decimal] = Field(default=None, ge=0)
    connects:           Optional[int]     = Field(default=None, ge=0)
    upwork_plus:        Optional[bool]    = None


class UpworkProfileResponse(BaseModel):
    """Lightweight profile row (list / create responses)."""
    id:          str
    profileName: str
    isActive:    bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Snapshot
# ─────────────────────────────────────────────────────────────────────────────

class UpworkSnapshotCreate(BaseModel):
    """
    Daily financial snapshot — additive accumulation on (profileName, date).

    Submission behaviour
    ────────────────────
    • First submission for (profileName, date)
        → INSERT the row with the incoming values as-is.
    • Subsequent submission for the same (profileName, date)
        → ADD (accumulate) the incoming numeric values to the existing stored
          values rather than replacing them.
        → ``upwork_plus`` uses OR semantics: once True for the day it stays True.

    ``active_amount`` / ``work_in_progress`` duality
    ─────────────────────────────────────────────────
    ``active_amount`` is an **optional alias** for ``work_in_progress``.
    Both fields map to the same ``workInProgress`` DB column.
    • Only ``work_in_progress`` supplied  → stored as-is.
    • Only ``active_amount``   supplied   → treated identically.
    • Both supplied                       → their values are **summed** before storage.
    """
    profile_name:       Optional[str]     = Field(
        default=None, min_length=1, max_length=100,
        description="Exact Upwork profile name (case-insensitive match).",
    )
    date:               date
    available_withdraw: Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    pending:            Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    in_review:          Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    work_in_progress:   Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    # Optional alias ──────────────────────────────────────────────────────────
    active_amount:      Optional[Decimal] = Field(
        default=None, ge=0,
        description=(
            "Optional alias for work_in_progress. "
            "When supplied its value is added to work_in_progress before storage."
        ),
    )
    withdrawn:          Optional[Decimal] = Field(default=Decimal("0"), ge=0)
    connects:           Optional[int]     = Field(default=0, ge=0)
    upwork_plus:        Optional[bool]    = Field(default=False)

    @model_validator(mode="after")
    def _merge_active_amount(self) -> "UpworkSnapshotCreate":
        """Collapse ``active_amount`` into ``work_in_progress``."""
        wip = self.work_in_progress or Decimal("0")
        if self.active_amount is not None:
            wip = wip + self.active_amount
        self.work_in_progress = wip
        self.active_amount    = wip
        return self


class UpworkSnapshotUpdate(BaseModel):
    """
    ``PATCH /snapshots/{id}`` — partial update (SET semantics, not additive).

    All fields are optional — only supplied fields are overwritten.
    This allows HR to correct a previously submitted snapshot without
    re-entering unrelated values.

    ``profile_name`` and ``date`` are immutable after creation and are
    not accepted by this endpoint.
    """
    available_withdraw: Optional[Decimal] = Field(default=None, ge=0)
    pending:            Optional[Decimal] = Field(default=None, ge=0)
    in_review:          Optional[Decimal] = Field(default=None, ge=0)
    work_in_progress:   Optional[Decimal] = Field(default=None, ge=0)
    withdrawn:          Optional[Decimal] = Field(default=None, ge=0)
    connects:           Optional[int]     = Field(default=None, ge=0)
    upwork_plus:        Optional[bool]    = Field(default=None)


class UpworkSnapshotResponse(BaseModel):
    """Full snapshot row returned by POST /snapshots and GET .../snapshots."""
    id:                        str
    profileId:                 str
    profileName:               str
    date:                      date
    availableWithdraw:         Decimal
    availableWithdrawAfterFee: Decimal  # computed: × 0.90
    pending:                   Decimal
    inReview:                  Decimal
    workInProgress:            Decimal
    activeAmount:              Decimal  # alias — always equals workInProgress
    withdrawn:                 Decimal
    connects:                  int
    upworkPlus:                bool
    createdAt:                 datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Order
# ─────────────────────────────────────────────────────────────────────────────

class UpworkOrderCreate(BaseModel):
    """
    Log a new Upwork order.

    ``afterUpwork`` (amount × 0.90) is always computed server-side.

    ### Automatic snapshot sync
    After persisting the order row the service additively updates the snapshot
    for ``(profileName, date)``:
    • ``workInProgress`` and ``activeAmount`` each incremented by ``amount``.
    • If no snapshot exists yet for that date one is upserted automatically.
    """
    profile_name: Optional[str]     = Field(
        default=None, min_length=1, max_length=100,
        description="Exact Upwork profile name (case-insensitive match).",
    )
    date:         date
    client_name:  Optional[str]     = Field(default=None, min_length=1)
    order_id:     Optional[str]     = Field(default=None, min_length=1)
    amount:       Optional[Decimal] = Field(default=None, gt=0)


class UpworkOrderUpdate(BaseModel):
    """
    PATCH /orders/{id} — partial update for a logged Upwork order.

    All fields are optional — only supplied fields are written.
    If ``amount`` is updated, ``afterUpwork`` is automatically re-computed
    server-side (amount × 0.90).
    """
    date:        date
    client_name: Optional[str]     = Field(default=None, min_length=1)
    order_id:    Optional[str]     = Field(default=None, min_length=1)
    amount:      Optional[Decimal] = Field(default=None, gt=0)


class UpworkOrderResponse(BaseModel):
    """Full order row."""
    id:          str
    profileId:   str
    date:        date
    clientName:  str
    orderId:     str
    amount:      Decimal
    afterUpwork: Decimal
    createdAt:   datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Trash  (soft-delete registry)
# ─────────────────────────────────────────────────────────────────────────────

class UpworkTrashItem(BaseModel):
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


class UpworkTrashResponse(BaseModel):
    """Envelope for ``GET /trash``."""
    total: int
    items: List[UpworkTrashItem]


class UpworkRestoreRequest(BaseModel):
    """
    ``POST /restore-trash`` — restore one or more soft-deleted records.

    ``ids``  List of original DB primary keys to restore.
    """
    ids: List[str] = Field(..., min_length=1, description="List of trash record IDs to restore.")


class UpworkRestoreResponse(BaseModel):
    """Result envelope for ``POST /restore-trash``."""
    restored: List[str]
    failed:   List[str]
    message:  str


# ─────────────────────────────────────────────────────────────────────────────
# Embedded sub-types (profile list / detail responses)
# ─────────────────────────────────────────────────────────────────────────────

class UpworkSnapshotInProfile(BaseModel):
    """Snapshot row embedded within profile list / detail responses."""
    id:                        str
    profileName:               str
    date:                      date
    availableWithdraw:         float
    availableWithdrawAfterFee: float
    pending:                   float
    inReview:                  float
    workInProgress:            float
    activeAmount:              float   # alias — always equals workInProgress
    withdrawn:                 float
    connects:                  int
    upworkPlus:                bool
    createdAt:                 datetime


class UpworkOrderInProfile(BaseModel):
    """Order row embedded within profile list / detail responses."""
    id:          str
    date:        date
    clientName:  str
    orderId:     str
    amount:      float
    afterUpwork: float
    createdAt:   datetime


# ─────────────────────────────────────────────────────────────────────────────
# List envelope  GET /profiles
# ─────────────────────────────────────────────────────────────────────────────

class UpworkTotals(BaseModel):
    """Cross-profile aggregate for the selected period."""
    totalAvailableWithdraw:         float
    totalAvailableWithdrawAfterFee: float   # × 0.90
    totalPending:                   float
    totalInReview:                  float
    totalWorkInProgress:            float
    totalWithdrawn:                 float
    totalConnects:                  int
    totalRevenueInPeriod:           float
    totalActiveAmount:              float
    totalOrderCount:                int     # dynamic — live orders across ALL active profiles
    activeProfileCount:             int


class UpworkProfileSummary(BaseModel):
    """Per-profile row within the paginated list response."""
    id:              str
    profileName:     str
    isActive:        bool
    latestSnapshot:  Optional[UpworkSnapshotInProfile]
    periodTotals:    Dict[str, Any]
    snapshotCount:   int
    orderCount:      int
    revenueInPeriod: float
    orders:          List[UpworkOrderInProfile]


class UpworkListResponse(BaseModel):
    """Top-level envelope for GET /profiles."""
    filter:     Dict[str, Any]
    totals:     UpworkTotals
    pagination: Dict[str, Any]
    profiles:   List[UpworkProfileSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Single-profile detail  GET /profiles/{id}
# ─────────────────────────────────────────────────────────────────────────────

class UpworkProfileDetailTotals(BaseModel):
    availableWithdraw:         float
    availableWithdrawAfterFee: float
    pending:                   float
    inReview:                  float
    workInProgress:            float
    activeAmount:              float
    withdrawn:                 float
    connects:                  int
    revenueInPeriod:           float
    snapshotCount:             int
    orderCount:                int


class UpworkProfileDetailResponse(BaseModel):
    """Full drill-down for GET /profiles/{id}."""
    filter:       Dict[str, Any]
    profile:      UpworkProfileResponse
    periodTotals: UpworkProfileDetailTotals
    pagination:   Dict[str, Any]
    snapshots:    List[UpworkSnapshotInProfile]
    orders:       List[UpworkOrderInProfile]