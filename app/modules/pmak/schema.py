"""
app/modules/pmak/schema.py
════════════════════════════════════════════════════════════════════════════════
v4.3 — Enterprise Edition

Request/response contracts for all PMAK endpoints.

Key design decisions
────────────────────
• ``account_name`` (not ``account_id``) — server resolves to internal ID.
  Staff never handle UUIDs in API payloads.
• ``PmakTransactionStatusUpdate`` is deliberately narrow (status only) —
  the BDev role may PATCH status but must never touch financial fields.
• ``PmakAllInhouseResponse`` — new envelope for GET /inhouse (cross-account).
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.shared.constants import InhouseOrderStatus, PmakStatus


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

    class Config:
        from_attributes = True


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
    date: date = Field(
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
        None,
        description="Source account or entity name.",
        examples=["Payoneer Main"],
    )
    accountTo: Optional[str] = Field(
        None,
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
    remaining_balance: Decimal = Field(
        ...,
        description="Running balance after this entry, in USD.",
        examples=[8750.00],
    )
    status: PmakStatus = Field(
        default=PmakStatus.PENDING,
        description="Initial transaction status. Defaults to PENDING.",
    )


class PmakTransactionStatusUpdate(BaseModel):
    """
    Restricted PATCH payload — BDev entry-point.
    Only `status` is exposed. Financial fields are intentionally absent.
    """

    status: Optional[PmakStatus] = Field(
        None,
        description="New status: PENDING | CLEARED | ON_HOLD | REJECTED.",
    )


class PmakTransactionResponse(BaseModel):
    id:               str
    accountId:        str
    accountName:      str
    date:             date
    details:          str
    accountFrom:      Optional[str]
    accountTo:        Optional[str]
    debit:            Decimal
    credit:           Decimal
    remainingBalance: Decimal
    status:           PmakStatus
    createdAt:        datetime

    class Config:
        from_attributes = True


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
    date: date = Field(
        ...,
        description="Deal date (YYYY-MM-DD).",
        examples=["2026-03-15"],
    )
    details: Optional[str] = Field(
        None,
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
    """Partial update payload for an inhouse deal — all PMAK roles."""

    order_status: Optional[InhouseOrderStatus] = Field(
        None,
        description="New status: PENDING | IN_PROGRESS | COMPLETED | CANCELLED.",
    )
    details: Optional[str] = Field(
        None,
        description="Updated notes or reference code.",
        examples=["SEO audit + 3-month plan – CLT-003"],
    )


class PmakInhouseResponse(BaseModel):
    id:          str
    accountId:   str
    accountName: str
    date:        date
    details:     Optional[str]
    buyerName:   str
    sellerName:  str
    orderAmount: Decimal
    orderStatus: InhouseOrderStatus
    createdAt:   datetime
    updatedAt:   datetime

    class Config:
        from_attributes = True


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
    byStatus: Dict[str, PmakInhouseStatusBreakdown]  # keys: PENDING | IN_PROGRESS | COMPLETED | CANCELLED


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
    totalBalance:       float
    totalCredit:        float
    totalDebit:         float
    totalTransactions:  int
    totalInhouse:       int
    totalInhouseAmount: float
    inhouseByStatus:    PmakInhouseByStatus
    activeAccountCount: int


class PmakAccountSummary(BaseModel):
    """Per-account row inside the GET /accounts response."""
    id:                  str
    accountName:         str
    isActive:            bool
    currentBalance:      float
    periodCredit:        float
    periodDebit:         float
    transactionCount:    int
    inhouseCount:        int
    inhouseByStatus:     PmakInhouseByStatus
    recentTransactions:  List[PmakTransactionResponse]
    recentInhouse:       List[PmakInhouseResponse]


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