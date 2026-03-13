"""
app/modules/pmak/schema.py
════════════════════════════════════════════════════════════════════════════════
v4 — Enterprise Edition

Changes vs v3
─────────────
PmakTransactionCreate
  • ``account_id`` → ``account_name``  (case-insensitive server-side lookup).

PmakInhouseCreate
  • ``account_id`` → ``account_name``  (same rationale).

PmakTransactionResponse
  • ``accountName`` field added.

PmakInhouseResponse
  • ``accountName`` field added.

PmakAccountTotals / PmakListResponse  (NEW)
  • Top-level combined-totals envelope for GET /accounts.
  • Includes ledger balance, inhouse deal counts + amounts by status.

Security design (unchanged)
────────────────────────────
• PmakTransactionStatusUpdate — the ONLY payload BDev may PATCH.
  Deliberately narrow: no financial fields exposed to BDev role.
• status uses typed PmakStatus enum; orderStatus uses InhouseOrderStatus.
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.shared.constants import InhouseOrderStatus, PmakStatus


# ─────────────────────────────────────────────────────────────────────────────
# Account
# ─────────────────────────────────────────────────────────────────────────────

class PmakAccountCreate(BaseModel):
    accountName: str = Field(..., min_length=1, max_length=100)


class PmakAccountResponse(BaseModel):
    id:          str
    accountName: str
    isActive:    bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Ledger Transaction
# ─────────────────────────────────────────────────────────────────────────────

class PmakTransactionCreate(BaseModel):
    """
    Full transaction creation — HR_AND_ABOVE.

    ``account_name`` replaced ``account_id`` in v4 for user-friendliness.
    """
    account_name:      str            = Field(
        ..., min_length=1, max_length=100,
        description="Exact PMAK account name (case-insensitive match).",
    )
    date:              date
    details:           str
    accountFrom:       Optional[str]  = None
    accountTo:         Optional[str]  = None
    debit:             Decimal        = Field(default=Decimal("0"), ge=0)
    credit:            Decimal        = Field(default=Decimal("0"), ge=0)
    remaining_balance: Decimal
    status:            PmakStatus     = PmakStatus.PENDING


class PmakTransactionStatusUpdate(BaseModel):
    """
    Restricted PATCH — the ONLY payload BDev may PATCH.
    Deliberately narrow: BDev cannot touch financial figures.
    """
    status: Optional[PmakStatus] = None


class PmakTransactionResponse(BaseModel):
    """Full transaction row — includes ``accountName`` for client convenience."""
    id:               str
    accountId:        str
    accountName:      str           # ← v4
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
# Inhouse Deal
# ─────────────────────────────────────────────────────────────────────────────

class PmakInhouseCreate(BaseModel):
    """
    Inhouse deal creation — HR_AND_ABOVE.

    ``account_name`` replaced ``account_id`` in v4.
    """
    account_name: str            = Field(
        ..., min_length=1, max_length=100,
        description="Exact PMAK account name (case-insensitive match).",
    )
    date:         date
    details:      Optional[str]  = None
    buyer_name:   str
    seller_name:  str
    order_amount: Decimal        = Field(..., gt=0)
    order_status: InhouseOrderStatus = InhouseOrderStatus.PENDING


class PmakInhouseStatusUpdate(BaseModel):
    """Update deal status / details — PMAK_EDITORS (BDev + HR + CEO + DIRECTOR)."""
    order_status: Optional[InhouseOrderStatus] = None
    details:      Optional[str]                = None


class PmakInhouseResponse(BaseModel):
    """Full inhouse deal row — includes ``accountName``."""
    id:          str
    accountId:   str
    accountName: str           # ← v4
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
# Combined-totals envelope  GET /accounts
# ─────────────────────────────────────────────────────────────────────────────

class PmakInhouseByStatus(BaseModel):
    """Inhouse deal counts + amounts grouped by order status."""
    PENDING:     Dict[str, Any]   # {count, totalAmount}
    IN_PROGRESS: Dict[str, Any]
    COMPLETED:   Dict[str, Any]
    CANCELLED:   Dict[str, Any]


class PmakTotals(BaseModel):
    """Cross-account aggregate for the selected period."""
    totalBalance:       float   # Σ latest remainingBalance per account
    totalCredit:        float   # Σ credit transactions in period
    totalDebit:         float   # Σ debit transactions in period
    totalTransactions:  int
    totalInhouse:       int     # total inhouse deals in period
    totalInhouseAmount: float   # Σ orderAmount in period
    inhouseByStatus:    PmakInhouseByStatus
    activeAccountCount: int


class PmakAccountSummary(BaseModel):
    """Per-account row in the list response."""
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
    """Paginated transactions for one account with metadata."""
    account:        PmakAccountResponse
    currentBalance: float
    periodCredit:   float
    periodDebit:    float
    pagination:     Dict[str, Any]
    transactions:   List[PmakTransactionResponse]


class PmakAccountInhouseResponse(BaseModel):
    """Paginated inhouse deals for one account with status summary."""
    account:          PmakAccountResponse
    inhouseByStatus:  PmakInhouseByStatus
    totalAmount:      float
    pagination:       Dict[str, Any]
    deals:            List[PmakInhouseResponse]