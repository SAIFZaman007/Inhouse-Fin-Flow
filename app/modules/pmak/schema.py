"""
app/modules/pmak/schema.py
════════════════════════════════════════════════════════════════════════════════
v7.0 — Enterprise Edition
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date as Date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ── Enum imports — always use the prisma-generated source directly ────────────
from prisma.enums import InhouseOrderStatus, PmakStatus


# ─────────────────────────────────────────────────────────────────────────────
# Accounts
# ─────────────────────────────────────────────────────────────────────────────

class PmakAccountCreate(BaseModel):
    accountName: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique display name for this PMAK ledger account.",
        examples=["PMAK Main", "PMAK Operations"],
    )


class PmakAccountResponse(BaseModel):
    id:          str
    accountName: str
    isActive:    bool
    createdAt:   Optional[datetime] = None
    updatedAt:   Optional[datetime] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Ledger Transactions
# ─────────────────────────────────────────────────────────────────────────────

class PmakTransactionCreate(BaseModel):
    """Full transaction creation payload — HR and above only."""

    account_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="PMAK account name (case-insensitive). Resolved to ID server-side.",
        examples=["PMAK Main"],
    )
    date: Date = Field(                          # ← `Date` alias; field name safe
        ...,
        description="Transaction date (YYYY-MM-DD).",
        examples=["2026-03-15"],
    )
    details: str = Field(
        ...,
        description="Free-text description of this ledger entry.",
        examples=["Payment received from client – INV-042"],
    )
    accountFrom: Optional[str] = Field(
        default=None,
        description="Source account or entity name.",
        examples=["Payoneer Main"],
    )
    accountTo: Optional[str] = Field(
        default=None,
        description="Destination account or entity name.",
        examples=["PMAK Operations"],
    )
    debit: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="Debit amount in USD. Defaults to 0.",
        examples=[500.00],
    )
    credit: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="Credit amount in USD. Defaults to 0.",
        examples=[1200.00],
    )
    remaining_balance: Optional[Decimal] = Field(
        default=None,
        description=(
            "Running balance after this entry, in USD. "
            "If omitted, the server auto-computes it as: "
            "previous_balance − debit + credit."
        ),
        examples=[8750.00],
    )
    status: PmakStatus = Field(
        default=PmakStatus.PENDING,
        description="Initial transaction status. Defaults to PENDING.",
    )


class PmakTransactionStatusUpdate(BaseModel):
    """
    Restricted PATCH payload — BDev entry-point.
    Only ``status`` is exposed. Financial fields are intentionally absent.
    """

    status: Optional[PmakStatus] = Field(
        default=None,
        description="New status: PENDING | CLEARED | ON_HOLD | REJECTED.",
    )


class PmakTransactionResponse(BaseModel):
    id:               str
    accountId:        str
    accountName:      str
    date:             Date                       # ← `Date` alias
    details:          str
    accountFrom:      Optional[str]
    accountTo:        Optional[str]
    debit:            Decimal
    credit:           Decimal
    remainingBalance: Decimal
    status:           PmakStatus
    createdAt:        datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Inhouse Deals
# ─────────────────────────────────────────────────────────────────────────────

class PmakInhouseCreate(BaseModel):
    """Inhouse deal creation payload — HR and above only."""

    account_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="PMAK account name (case-insensitive). Resolved to ID server-side.",
        examples=["PMAK Main"],
    )
    date: Date = Field(                          # ← `Date` alias
        ...,
        description="Deal date (YYYY-MM-DD).",
        examples=["2026-03-15"],
    )
    details: Optional[str] = Field(
        default=None,
        description="Optional notes or reference code for this deal.",
        examples=["UI/UX design package – CLT-001"],
    )
    buyer_name: str = Field(
        ...,
        description="Name of the buyer in this deal.",
        examples=["Rahim Textiles"],
    )
    seller_name: str = Field(
        ...,
        description="Name of the seller / service provider in this deal.",
        examples=["maktech_design"],
    )
    order_amount: Decimal = Field(
        ...,
        gt=0,
        description="Deal value in USD. Must be greater than 0.",
        examples=[18000.00],
    )
    order_status: InhouseOrderStatus = Field(
        default=InhouseOrderStatus.PENDING,
        description="Initial deal status. Defaults to PENDING.",
    )


class PmakInhouseStatusUpdate(BaseModel):
    """
    Legacy partial update payload — kept for backward compatibility.
    Use PmakInhouseFullUpdate for the full PATCH endpoint instead.
    """

    order_status: Optional[InhouseOrderStatus] = Field(
        default=None,
        description="New status: PENDING | IN_PROGRESS | COMPLETED | CANCELLED.",
    )
    details: Optional[str] = Field(
        default=None,
        description="Updated notes or reference code.",
        examples=["SEO audit + 3-month plan – CLT-003"],
    )


class PmakInhouseFullUpdate(BaseModel):
    """
    Full optional-field PATCH payload for PATCH /inhouse/{deal_id}.

    Every field is optional — only supplied fields are written.
    Sending an empty body {} returns the current deal state unchanged (idempotent).
    """

    account_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Reassign deal to a different active PMAK account (case-insensitive).",
        examples=["PMAK Operations"],
    )
    date: Optional[Date] = Field(               # ← `Date` alias
        default=None,
        description="Updated deal date (YYYY-MM-DD).",
        examples=["2026-04-01"],
    )
    details: Optional[str] = Field(
        default=None,
        description="Updated free-text notes or reference code.",
        examples=["SEO audit + 3-month plan – CLT-003"],
    )
    buyer_name: Optional[str] = Field(
        default=None,
        description="Updated buyer name.",
        examples=["Rahim Textiles"],
    )
    seller_name: Optional[str] = Field(
        default=None,
        description="Updated seller / service-provider name.",
        examples=["maktech_design"],
    )
    order_amount: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Updated deal value in USD. Must be greater than 0.",
        examples=[20000.00],
    )
    order_status: Optional[InhouseOrderStatus] = Field(
        default=None,
        description="New lifecycle status: PENDING | IN_PROGRESS | COMPLETED | CANCELLED.",
    )


class PmakInhouseResponse(BaseModel):
    id:          str
    accountId:   str
    accountName: str
    date:        Date                            # ← `Date` alias
    details:     Optional[str]
    buyerName:   str
    sellerName:  str
    orderAmount: Decimal
    orderStatus: InhouseOrderStatus
    createdAt:   datetime
    updatedAt:   datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Tools  (v7 — new entity stored in `pmak_tools` raw-SQL table)
# ─────────────────────────────────────────────────────────────────────────────

class PmakToolCreate(BaseModel):
    """
    POST /tools payload.

    Only ``account_name`` is required; every other field is optional so that
    callers can gradually fill in values without being forced to supply zeros or
    placeholder strings.

    The ``total`` field is auto-computed server-side using:
        total = latest_total_for_account − debit + credit
    and stored so that all future reads are O(1) without re-scanning history.
    You may still pass ``total`` explicitly to override this (useful for manual
    balance corrections — identical semantics to ``remaining_balance`` in the
    Transactions entity).
    """

    account_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description=(
            "PMAK account name (case-insensitive). "
            "Resolved to an account ID server-side."
        ),
        examples=["PMAK Main"],
    )
    date: Optional[Date] = Field(
        default=None,
        description="Entry date (YYYY-MM-DD). Defaults to today when omitted.",
        examples=["2026-04-15"],
    )
    details: Optional[str] = Field(
        default=None,
        description="Free-text description of this tools ledger entry.",
        examples=["Adobe CC subscription renewal – Q2 2026"],
    )
    debit: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Debit amount in USD. Defaults to 0 when omitted.",
        examples=[120.00],
    )
    credit: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Credit amount in USD. Defaults to 0 when omitted.",
        examples=[0.00],
    )
    total: Optional[Decimal] = Field(
        default=None,
        description=(
            "Running total after this entry, in USD. "
            "Auto-computed as: latest_total − debit + credit when omitted. "
            "Pass an explicit non-zero value to override (manual correction)."
        ),
        examples=[3800.00],
    )


class PmakToolUpdate(BaseModel):
    """
    PATCH /tools/{tool_id} payload — every field is optional.

    Sending an empty body {} is accepted and returns the current state
    unchanged (idempotent).  Financial field changes (debit / credit) trigger
    automatic ``total`` recomputation using the same reverse-formula as the
    Transactions PATCH unless an explicit ``total`` override is supplied.
    """

    account_name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Reassign entry to a different active PMAK account.",
        examples=["PMAK Operations"],
    )
    date: Optional[Date] = Field(
        default=None,
        description="Updated entry date (YYYY-MM-DD).",
        examples=["2026-05-01"],
    )
    details: Optional[str] = Field(
        default=None,
        description="Updated free-text description.",
        examples=["Figma Teams renewal — updated ref"],
    )
    debit: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Updated debit amount in USD.",
        examples=[150.00],
    )
    credit: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Updated credit amount in USD.",
        examples=[0.00],
    )
    total: Optional[Decimal] = Field(
        default=None,
        description=(
            "Manual total override in USD. "
            "Takes priority over the auto-recomputed value."
        ),
        examples=[3650.00],
    )


class PmakToolResponse(BaseModel):
    """Single tools-ledger row returned by all Tools endpoints."""
    id:          str
    accountId:   str
    accountName: str
    date:        Date
    details:     Optional[str]
    debit:       Decimal
    credit:      Decimal
    total:       Decimal
    createdAt:   datetime
    updatedAt:   datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# GET /inhouse — cross-account deal list
# ─────────────────────────────────────────────────────────────────────────────

class PmakInhouseStatusBreakdown(BaseModel):
    """Count and total amount for one order status."""
    count:       int
    totalAmount: float


class PmakInhouseTotals(BaseModel):
    """Aggregate totals across all matching inhouse deals."""
    totalDeals:  int
    totalAmount: float
    byStatus:    Dict[str, PmakInhouseStatusBreakdown]  # keys: PENDING | IN_PROGRESS | COMPLETED | CANCELLED


class PmakAllInhouseResponse(BaseModel):
    """Envelope returned by GET /pmak/inhouse."""
    filter:     Dict[str, Any]
    totals:     PmakInhouseTotals
    pagination: Dict[str, Any]
    deals:      List[PmakInhouseResponse]


# ─────────────────────────────────────────────────────────────────────────────
# GET /tools — cross-account tools list
# ─────────────────────────────────────────────────────────────────────────────

class PmakToolsTotals(BaseModel):
    """Aggregate totals across all matching tools entries."""
    totalEntries: int
    totalDebit:   float
    totalCredit:  float
    latestTotal:  float


class PmakAllToolsResponse(BaseModel):
    """Envelope returned by GET /pmak/tools."""
    filter:     Dict[str, Any]
    totals:     PmakToolsTotals
    pagination: Dict[str, Any]
    tools:      List[PmakToolResponse]


# ─────────────────────────────────────────────────────────────────────────────
# GET /accounts — combined account list
# ─────────────────────────────────────────────────────────────────────────────

class PmakInhouseByStatus(BaseModel):
    """Inhouse deal counts and amounts grouped by order status."""
    PENDING:     Dict[str, Any]
    IN_PROGRESS: Dict[str, Any]
    COMPLETED:   Dict[str, Any]
    CANCELLED:   Dict[str, Any]


class PmakTotals(BaseModel):
    """Cross-account aggregate for the selected period."""
    totalBalance:           float
    totalCredit:            float
    totalDebit:             float
    totalTransactions:      int
    totalInhouse:           int
    totalInhouseAmount:     float
    inhouseByStatus:        PmakInhouseByStatus
    activeAccountCount:     int


class PmakAccountSummary(BaseModel):
    """Per-account row inside the GET /accounts response."""
    id:                      str
    accountName:             str
    isActive:                bool
    createdAt:               Optional[datetime] = None   # v7
    updatedAt:               Optional[datetime] = None   # v7
    currentBalance:          float
    periodCredit:            float
    periodDebit:             float
    transactionCount:        int
    inhouseCount:            int
    totalInhouseOrderAmount: float
    inhouseByStatus:         PmakInhouseByStatus
    recentTransactions:      List[PmakTransactionResponse]
    recentInhouse:           List[PmakInhouseResponse]


class PmakListResponse(BaseModel):
    """Top-level envelope for GET /accounts."""
    filter:     Dict[str, Any]
    totals:     PmakTotals
    pagination: Dict[str, Any]
    accounts:   List[PmakAccountSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Single-account detail responses
# ─────────────────────────────────────────────────────────────────────────────

class PmakAccountTransactionResponse(BaseModel):
    """Envelope for GET /accounts/{id}/transactions."""
    account:        PmakAccountResponse
    currentBalance: float
    periodCredit:   float
    periodDebit:    float
    pagination:     Dict[str, Any]
    transactions:   List[PmakTransactionResponse]


class PmakAccountInhouseResponse(BaseModel):
    """Envelope for GET /accounts/{id}/inhouse."""
    account:         PmakAccountResponse
    inhouseByStatus: PmakInhouseByStatus
    totalAmount:     float
    pagination:      Dict[str, Any]
    deals:           List[PmakInhouseResponse]


class PmakAccountToolsResponse(BaseModel):
    """Envelope for GET /accounts/{id}/tools."""
    account:        PmakAccountResponse
    totalDebit:     float
    totalCredit:    float
    latestTotal:    float
    pagination:     Dict[str, Any]
    tools:          List[PmakToolResponse]