"""
app/modules/pmak/schema.py

New fields on PmakTransaction (migration required):
  - status  String?   — transaction lifecycle status (PENDING/CLEARED/REJECTED/ON_HOLD)
  - notes   String?   — internal remarks; editable by HR and BDev

BDev role can ONLY patch `status` and `notes` on existing transactions.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from app.shared.constants import PmakTransactionStatus


class PmakAccountCreate(BaseModel):
    accountName: str


class PmakAccountResponse(BaseModel):
    id: str
    accountName: str
    isActive: bool

    class Config:
        from_attributes = True


# ── Transaction schemas ───────────────────────────────────────────────────────

class PmakTransactionCreate(BaseModel):
    """Full transaction creation — CEO / DIRECTOR / HR only."""
    account_id: str
    date: date
    details: str
    accountFrom: Optional[str] = None
    accountTo: Optional[str] = None
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    remaining_balance: Decimal
    status: Optional[PmakTransactionStatus] = PmakTransactionStatus.PENDING
    notes: Optional[str] = None


class PmakTransactionStatusUpdate(BaseModel):
    """
    Restricted update — the ONLY payload BDev (and HR) may PATCH.
    Deliberately narrow: BDev cannot touch financial figures.
    """
    status: Optional[PmakTransactionStatus] = None
    notes: Optional[str] = None


class PmakTransactionResponse(BaseModel):
    id: str
    accountId: str
    date: date
    details: str
    accountFrom: Optional[str]
    accountTo: Optional[str]
    debit: Decimal
    credit: Decimal
    remainingBalance: Decimal
    status: Optional[str]
    notes: Optional[str]
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True