"""
app/modules/hr_expense/schema.py

Built directly from schema.prisma (source of truth):

  model HrExpense {
    id               String   @id @default(cuid())
    date             DateTime @db.Date
    details          String
    accountFrom      String?
    accountTo        String?
    debit            Decimal  @db.Decimal(12, 2) @default(0)
    credit           Decimal  @db.Decimal(12, 2) @default(0)
    remainingBalance Decimal  @db.Decimal(12, 2)
    createdAt        DateTime @default(now())
    @@map("hr_expenses")
  }
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


class HrExpenseUpdate(BaseModel):
    details: Optional[str] = None
    accountFrom: Optional[str] = None
    accountTo: Optional[str] = None
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    remaining_balance: Optional[Decimal] = None


class HrExpenseResponse(BaseModel):
    id: str
    date: date
    details: str
    accountFrom: Optional[str]            
    accountTo: Optional[str]               
    debit: Decimal
    credit: Decimal
    remainingBalance: Decimal
    createdAt: datetime

    class Config:
        from_attributes = True