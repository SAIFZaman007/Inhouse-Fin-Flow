"""
app/modules/hr_expense/schema.py
════════════════════════════════════════════════════════════════════════════════
v3 changes:
  HrExpenseCreate   → remarks field added (CEO comments/judgements)
  HrExpenseResponse → remarks field added
  HrExpenseUpdate   → remarks field added (CEO can add/edit remarks)
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class HrExpenseCreate(BaseModel):
    date: date
    details: str
    accountFrom: Optional[str] = None
    accountTo: Optional[str] = None
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    remaining_balance: Decimal
    remarks: Optional[str] = None        # CEO comments / judgement


class HrExpenseUpdate(BaseModel):
    """Partial update — only remarks can be patched by CEO after the fact."""
    remarks: Optional[str] = None


class HrExpenseResponse(BaseModel):
    id: str
    date: date
    details: str
    accountFrom: Optional[str]
    accountTo: Optional[str]
    debit: Decimal
    credit: Decimal
    remainingBalance: Decimal
    remarks: Optional[str]               
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True