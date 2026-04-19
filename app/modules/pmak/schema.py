"""
app/modules/pmak/schema.py
════════════════════════════════════════════════════════════════════════════════
v5.0 — Enterprise Edition
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
    currentBalance:          float
    periodCredit:            float
    periodDebit:             float
    transactionCount:        int
    inhouseCount:            int
    totalInhouseOrderAmount: float          # ← NEW: sum of orderAmount for this account
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