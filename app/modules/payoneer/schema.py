"""
app/modules/payoneer/schema.py
════════════════════════════════════════════════════════════════════════════════
v4 — Enterprise Edition

Changes vs v3
─────────────
PayoneerAccountUpdate   EXTENDED — PATCH /accounts/{id}
                          Now accepts ``description``, ``initial_balance``,
                          and ``opening_note`` so a single PATCH call can
                          rename/toggle the account AND add a balance-adjustment
                          credit transaction without a separate POST /transactions
                          round-trip.
                          New optional fields (all default None → left unchanged):
                            description, initial_balance, opening_note

PayoneerTransactionUpdate  FIXED — ``date`` is now Optional (was incorrectly
                             required in v3; an empty PATCH body must be
                             idempotent).

Everything else is unchanged from v3.
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

    If ``initial_balance`` is provided, an opening credit transaction is recorded
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


class PayoneerAccountUpdate(BaseModel):
    """
    PATCH /accounts/{id} — partial update for a Payoneer account.

    All fields are optional — only supplied fields are written.

    Account identity fields
    ───────────────────────
    ``accountName``   Renames the account (uniqueness enforced server-side).
    ``isActive``      ``false`` soft-deletes; ``true`` restores a deactivated account.

    Balance-adjustment fields  (v4 addition)
    ─────────────────────────────────────────
    When ``initial_balance`` is supplied the service appends a **credit**
    transaction to the account's ledger, so the balance can be corrected or
    topped-up without a separate POST /transactions call.

    ``description``    Updates the free-text account note (stored in the opening
                       transaction's ``details`` field if used at creation; here
                       it appears in the new adjustment transaction's details).
    ``initial_balance`` Amount of the credit adjustment (must be > 0 when supplied).
    ``opening_note``   Custom details text for the adjustment transaction.
                       Defaults to "Balance adjustment" when not supplied.

    Sending an empty body ``{}`` is accepted and returns the current account state
    unchanged (idempotent).
    """
    # ── Account metadata ──────────────────────────────────────────────────────
    accountName: Optional[str]  = Field(default=None, min_length=1, max_length=100)
    isActive:    Optional[bool] = Field(
        default=None,
        description="Set false to soft-delete; true to restore a deactivated account.",
    )

    # ── Balance-adjustment fields (v4) ────────────────────────────────────────
    description:     Optional[str]     = Field(
        default=None,
        description="Free-text account note (also used as transaction details when initial_balance is set).",
    )
    initial_balance: Optional[Decimal] = Field(
        default=None, gt=0,
        description="Posts a credit transaction of this amount to adjust the account balance.",
    )
    opening_note:    Optional[str]     = Field(
        default=None,
        description="Details text for the balance-adjustment transaction. Defaults to 'Balance adjustment'.",
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


class PayoneerTransactionUpdate(BaseModel):
    """
    PATCH /transactions/{id} — partial update for a Payoneer transaction.

    All fields are optional — only supplied fields are written.
    ``remainingBalance`` must be supplied by the caller if it needs correction —
    the system does not auto-recompute it (mirrors the POST contract).

    Sending an empty body ``{}`` is accepted and returns the current row unchanged
    (idempotent).
    """
    date:              date
    details:           Optional[str]     = Field(default=None, min_length=1)
    accountFrom:       Optional[str]     = None
    accountTo:         Optional[str]     = None
    debit:             Optional[Decimal] = Field(default=None, ge=0)
    credit:            Optional[Decimal] = Field(default=None, ge=0)
    remaining_balance: Optional[Decimal] = Field(
        default=None,
        description="Corrected balance after this transaction.",
    )


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