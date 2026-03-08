"""
app/modules/dollar_exchange/schema.py

from datetime import date
from decimal import Decimal
"""
from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, model_validator

from app.shared.constants import PaymentStatusEnum


class DollarExchangeCreate(BaseModel):
    date: date
    details: str
    accountFrom: Optional[str] = None   
    accountTo: Optional[str] = None    
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    rate: Decimal
    payment_status: PaymentStatusEnum = PaymentStatusEnum.DUE

    @model_validator(mode="after")
    def compute_total_bdt(self):
        exchange_amount = self.credit if self.credit > 0 else self.debit
        self.total_bdt = exchange_amount * self.rate
        return self

    total_bdt: Decimal = Decimal("0")


class DollarExchangeUpdate(BaseModel):
    payment_status: Optional[PaymentStatusEnum] = None
    details: Optional[str] = None
    rate: Optional[Decimal] = None


class DollarExchangeResponse(BaseModel):
    id: str
    date: date
    details: str
    accountFrom: Optional[str]         
    accountTo: Optional[str]            
    debit: Decimal
    credit: Decimal
    rate: Decimal
    totalBdt: Decimal
    paymentStatus: str

    class Config:
        from_attributes = True