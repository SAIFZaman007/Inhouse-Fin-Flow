"""
app/modules/payoneer/schema.py
════════════════════════════════════════════════════════════════════════════════
v2 — Enterprise Edition

Changes vs v1
─────────────
PayoneerAccountCreate
  • ``initial_balance`` optional — seeds an opening transaction on creation.
  • ``description`` optional — free-text account note.

PayoneerTransactionCreate
  • ``account_id`` → ``account_name``  (case-insensitive server-side lookup).
    Finance staff know account names, not internal UUIDs.

PayoneerTransactionResponse
  • ``accountName`` field added — every transaction row carries the
    human-readable account label; clients never need a second lookup.

PayoneerAccountSummary / PayoneerListResponse  (NEW)
  • Top-level combined-totals envelope for GET /accounts.

PayoneerAccountDetailResponse  (NEW)
  • Full drill-down for GET /accounts/{id} or embedded in list.
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Account
# ─────────────────────────────────────────────────────────────────────────────

class PayoneerAccountCreate(BaseModel):
    """
    Create a new Payoneer account.

    If ``initial_balance`` is provided, an opening transaction is recorded
    immediately with ``details`` = "Opening balance" (or the supplied
    ``opening_note``), so the ledger starts with the correct balance.
    """
    accountName:     str            = Field(..., min_length=1, max_length=100)
    description:     Optional[str]  = Field(default=None, description="Optional free-text account note.")
    initial_balance: Optional[Decimal] = Field(
        default=None, ge=0,
        description="Opening balance — seeds an initial credit transaction.",
    )
    opening_note: str = Field(
        default="Opening balance",
        description="Details string for the opening transaction.",
    )


class PayoneerAccountResponse(BaseModel):
    """Lightweight account row."""
    id:          str
    accountName: str
    isActive:    bool

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Transaction
# ─────────────────────────────────────────────────────────────────────────────

class PayoneerTransactionCreate(BaseModel):
    """
    Add a ledger transaction.

    ``account_name`` replaced ``account_id`` in v2.
    Finance staff know account names — the service resolves the name to an
    internal record automatically.
    """
    account_name:      str            = Field(
        ..., min_length=1, max_length=100,
        description="Exact Payoneer account name (case-insensitive match).",
    )
    date:              date
    details:           str            = Field(..., min_length=1)
    accountFrom:       Optional[str]  = None
    accountTo:         Optional[str]  = None
    debit:             Decimal        = Field(default=Decimal("0"), ge=0)
    credit:            Decimal        = Field(default=Decimal("0"), ge=0)
    remaining_balance: Decimal        = Field(..., description="Balance after this transaction.")


class PayoneerTransactionResponse(BaseModel):
    """Full transaction row — includes ``accountName`` for client convenience."""
    id:               str
    accountId:        str
    accountName:      str           # ← v2: human-readable label
    date:             date
    details:          str
    accountFrom:      Optional[str]
    accountTo:        Optional[str]
    debit:            Decimal
    credit:           Decimal
    remainingBalance: Decimal

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Combined-totals envelope  GET /accounts
# ─────────────────────────────────────────────────────────────────────────────

class PayoneerTotals(BaseModel):
    """Cross-account aggregate for the selected period."""
    totalBalance:       float   # sum of latest remainingBalance per account
    totalCredit:        float   # Σ credit in period
    totalDebit:         float   # Σ debit in period
    totalTransactions:  int     # transaction count in period
    activeAccountCount: int


class PayoneerAccountSummary(BaseModel):
    """Per-account row in the list response."""
    id:                  str
    accountName:         str
    isActive:            bool
    currentBalance:      float   # latest remainingBalance
    periodCredit:        float
    periodDebit:         float
    transactionCount:    int
    recentTransactions:  List[PayoneerTransactionResponse]


class PayoneerListResponse(BaseModel):
    """Top-level envelope for GET /accounts."""
    filter:   Dict[str, Any]
    totals:   PayoneerTotals
    accounts: List[PayoneerAccountSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Single-account detail  GET /accounts/{id}/transactions
# ─────────────────────────────────────────────────────────────────────────────

class PayoneerAccountDetailResponse(BaseModel):
    """Paginated transaction list with account metadata."""
    account:          PayoneerAccountResponse
    currentBalance:   float
    periodCredit:     float
    periodDebit:      float
    pagination:       Dict[str, Any]
    transactions:     List[PayoneerTransactionResponse]