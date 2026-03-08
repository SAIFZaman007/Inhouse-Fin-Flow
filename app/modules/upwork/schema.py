"""
app/modules/upwork/schema.py
"""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel


class UpworkProfileCreate(BaseModel):
    profileName: str            


class UpworkProfileResponse(BaseModel):
    id: str
    profileName: str            
    isActive: bool

    class Config:
        from_attributes = True


class UpworkSnapshotCreate(BaseModel):
    profile_id: str
    date: date
    available_withdraw: Decimal
    pending: Decimal
    in_review: Decimal
    work_in_progress: Decimal
    withdrawn: Decimal
    connects: int = 0               
    upwork_plus: bool = False


class UpworkSnapshotResponse(BaseModel):
    id: str
    profileId: str
    date: date
    availableWithdraw: Decimal
    pending: Decimal
    inReview: Decimal
    workInProgress: Decimal
    withdrawn: Decimal
    connects: int               
    upworkPlus: bool

    class Config:
        from_attributes = True


class UpworkOrderCreate(BaseModel):
    profile_id: str
    date: date
    client_name: str
    order_id: str
    amount: Decimal


class UpworkOrderResponse(BaseModel):
    id: str
    profileId: str
    date: date
    clientName: str
    orderId: str
    amount: Decimal

    class Config:
        from_attributes = True