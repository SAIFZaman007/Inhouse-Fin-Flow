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
    Business logic defaults: debit & credit fall back to 0; remaining_balance
    defaults to 0 when omitted.
    """
    date:              date
    details:           Optional[str]     = None
    accountFrom:       Optional[str]     = None
    accountTo:         Optional[str]     = None
    debit:             Optional[Decimal] = Decimal("0")
    credit:            Optional[Decimal] = Decimal("0")
    remaining_balance: Optional[Decimal] = Decimal("0")
    remarks:           Optional[str]     = None          


class HrExpenseUpdate(BaseModel):
    """
    Full partial update — every field is optional; only supplied fields are written.
    Supports: accountFrom, accountTo, debit, credit, remaining_balance, remarks.
    date and details are also patchable for correction workflows.
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