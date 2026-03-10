"""
app/modules/dollar_exchange/schema.py
=======================================
Pydantic schemas for Dollar Exchange module.

SCHEMA FACTS (schema.prisma — single source of truth):
  enum PaymentStatus  { RECEIVED  DUE }
  model DollarExchange { paymentStatus PaymentStatus @default(DUE) }

DESIGN:
  • PaymentStatusEnum is defined HERE (not imported from shared constants)
    so it is always in sync with schema.prisma regardless of what constants.py holds.
  • payment_status (snake_case Python attr) aliases paymentStatus (camelCase JSON).
  • total_bdt is ALWAYS server-computed — clients must never send it.
  • DollarExchangeResponse reads paymentStatus directly from the Prisma object
    via from_attributes=True — works because prisma-client-py exposes the field
    as a camelCase Python attribute matching the Pydantic field name.
"""
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ── Payment Status Enum ───────────────────────────────────────────────────────
# Values MUST match schema.prisma exactly: enum PaymentStatus { RECEIVED  DUE }

class PaymentStatusEnum(str, Enum):
    RECEIVED = "RECEIVED"
    DUE      = "DUE"


# ── Request schemas ───────────────────────────────────────────────────────────

class DollarExchangeCreate(BaseModel):
    date:        date
    details:     str
    accountFrom: Optional[str]     = None
    accountTo:   Optional[str]     = None
    debit:       Decimal           = Decimal("0")
    credit:      Decimal           = Decimal("0")
    rate:        Decimal

    # Accept both camelCase JSON body {"paymentStatus": "RECEIVED"}
    # and snake_case Python attribute .payment_status
    payment_status: PaymentStatusEnum = Field(
        PaymentStatusEnum.DUE,
        alias="paymentStatus",
    )

    model_config = {"populate_by_name": True}

    # Server-computed — clients must NOT send this field
    total_bdt: Decimal = Decimal("0")

    @model_validator(mode="after")
    def compute_total_bdt(self) -> "DollarExchangeCreate":
        exchange_amount = self.credit if self.credit > 0 else self.debit
        self.total_bdt  = exchange_amount * self.rate
        return self


class DollarExchangeUpdate(BaseModel):
    """
    Partial update. Changing `rate` triggers automatic totalBdt recompute
    in the service layer. `payment_status` flips between RECEIVED and DUE.
    """
    payment_status: Optional[PaymentStatusEnum] = Field(None, alias="paymentStatus")
    details:        Optional[str]               = None
    rate:           Optional[Decimal]           = None
    accountFrom:    Optional[str]               = None
    accountTo:      Optional[str]               = None

    model_config = {"populate_by_name": True}


# ── Response schema ───────────────────────────────────────────────────────────

class DollarExchangeResponse(BaseModel):
    id:            str
    date:          date
    details:       str
    accountFrom:   Optional[str]
    accountTo:     Optional[str]
    debit:         Decimal
    credit:        Decimal
    rate:          Decimal
    totalBdt:      Decimal
    paymentStatus: str              # "RECEIVED" | "DUE"

    model_config = {"from_attributes": True}