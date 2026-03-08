"""
app/modules/fiverr/schema.py
"""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel


class FiverrProfileCreate(BaseModel):
    profileName: str                  


class FiverrProfileResponse(BaseModel):
    id: str
    profileName: str                  
    isActive: bool

    class Config:
        from_attributes = True


class FiverrSnapshotCreate(BaseModel):
    profile_id: str
    date: date
    available_withdraw: Decimal
    not_cleared: Decimal
    active_orders: int
    submitted: Decimal                   
    withdrawn: Decimal
    seller_plus: bool = False
    promotion: Decimal = Decimal("0")    


class FiverrSnapshotResponse(BaseModel):
    id: str
    profileId: str
    date: date
    availableWithdraw: Decimal
    notCleared: Decimal
    activeOrders: int
    submitted: Decimal                     
    withdrawn: Decimal
    sellerPlus: bool
    promotion: Decimal                     

    class Config:
        from_attributes = True


class FiverrOrderCreate(BaseModel):
    profile_id: str
    date: date
    buyer_name: str                      
    order_id: str
    amount: Decimal


class FiverrOrderResponse(BaseModel):
    id: str
    profileId: str
    date: date
    buyerName: str                        
    orderId: str
    amount: Decimal

    class Config:
        from_attributes = True