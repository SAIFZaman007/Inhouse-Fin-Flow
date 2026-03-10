from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class DailyRateCreate(BaseModel):
    date:  date
    rate:  Decimal = Field(..., gt=0, description="BDT per 1 USD (e.g. 110.50)")
    setBy: Optional[str] = None
    note:  Optional[str] = None


class DailyRateUpdate(BaseModel):
    rate:  Optional[Decimal] = Field(None, gt=0)
    note:  Optional[str]     = None


class DailyRateResponse(BaseModel):
    id:        str
    date:      date
    rate:      Decimal
    setBy:     Optional[str]
    note:      Optional[str]
    createdAt: str   # ISO string

    model_config = {"from_attributes": True}