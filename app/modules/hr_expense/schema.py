"""
app/modules/hr_expense/schema.py
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

class HrExpenseCreate(BaseModel):
    """
    All fields are optional so partial / incremental entries are supported.
    Business logic defaults applied in the service layer:
      • debit / credit        → 0   (when omitted)
      • remaining_balance     → auto-computed as:
                                prev_record.remainingBalance − debit + credit
                                (caller may override by supplying a non-zero value)
      • date                  → today (when omitted)
      • details               → ""   (when omitted)

    IMPORTANT: remaining_balance must default to None here so the service
    can distinguish "caller did not provide a value" from "caller explicitly
    sent 0".  A Decimal("0") default would always satisfy the
    `is not None` guard and suppress the auto-compute path.
    """
    date:              date
    details:           Optional[str]     = None
    accountFrom:       Optional[str]     = None
    accountTo:         Optional[str]     = None
    debit:             Optional[Decimal] = Decimal("0")
    credit:            Optional[Decimal] = Decimal("0")
    remaining_balance: Optional[Decimal] = None          # ← FIX 1: was Decimal("0")
    remarks:           Optional[str]     = None


class HrExpenseUpdate(BaseModel):
    """
    Full partial update — every field is optional; only supplied fields are written.
    Supports: date, details, accountFrom, accountTo, debit, credit,
              remaining_balance, remarks.
    """
    date:              date
    details:           Optional[str]     = None
    accountFrom:       Optional[str]     = None
    accountTo:         Optional[str]     = None
    debit:             Optional[Decimal] = None
    credit:            Optional[Decimal] = None
    remaining_balance: Optional[Decimal] = None
    remarks:           Optional[str]     = None


class HrExpenseResponse(BaseModel):
    id:               str
    date:             date
    details:          str
    accountFrom:      Optional[str]
    accountTo:        Optional[str]
    debit:            Decimal
    credit:           Decimal
    remainingBalance: Decimal
    remarks:          Optional[str]
    createdAt:        datetime
    updatedAt:        datetime

    class Config:
        from_attributes = True


class HrExpenseTotals(BaseModel):
    """Computed aggregate figures returned alongside the record list."""
    totalRecords:          int
    totalDebits:           Decimal
    totalCredits:          Decimal
    totalRemainingBalance: Decimal   # = sum(remainingBalance) + totalCredits - totalDebits


class HrExpenseListResponse(BaseModel):
    """Envelope returned by GET /hr-expense — records + totals in one payload."""
    totals:  HrExpenseTotals
    records: List[HrExpenseResponse]