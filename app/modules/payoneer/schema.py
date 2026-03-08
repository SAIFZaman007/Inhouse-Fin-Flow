from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class PayoneerAccountCreate(BaseModel):
    accountName: str


class PayoneerAccountResponse(BaseModel):
    id: str
    accountName: str
    isActive: bool

    class Config:
        from_attributes = True


class PayoneerTransactionCreate(BaseModel):
    account_id: str
    date: date
    details: str
    accountFrom: Optional[str]   
    accountTo: Optional[str] 
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    remaining_balance: Decimal


class PayoneerTransactionResponse(BaseModel):
    id: str
    accountId: str
    date: date
    details: str
    accountFrom: Optional[str]   
    accountTo: Optional[str] 
    debit: Decimal
    credit: Decimal
    remainingBalance: Decimal

    class Config:
        from_attributes = True