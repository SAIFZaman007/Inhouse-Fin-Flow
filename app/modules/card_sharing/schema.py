"""
app/modules/card_sharing/schema.py
Pydantic models for Card Sharing module.
Defines request and response schemas, including separate response models for sensitive data.
"""
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class CardSharingCreate(BaseModel):
    details: Optional[str] = None      
    payoneer_account: str
    card_no: str                         
    card_expire: str
    card_cvc: str                       
    card_vendor: str
    card_limit: Decimal
    card_payment_rcv: Decimal = Decimal("0")
    card_rcv_bank: Optional[str] = None
    mail_details: Optional[str] = None
    screenshot_path: Optional[str] = None  
    serial_no: str                      


class CardSharingUpdate(BaseModel):
    details: Optional[str] = None
    card_vendor: Optional[str] = None
    card_limit: Optional[Decimal] = None
    card_payment_rcv: Optional[Decimal] = None
    card_rcv_bank: Optional[str] = None
    mail_details: Optional[str] = None
    screenshot_path: Optional[str] = None 


class CardSharingResponse(BaseModel):
    id: str
    serialNo: str                     
    details: Optional[str]
    payoneerAccount: str
    cardExpire: str
    cardVendor: str
    cardLimit: Decimal
    cardPaymentRcv: Decimal
    cardRcvBank: Optional[str]
    mailDetails: Optional[str]
    screenshotPath: Optional[str]       

    class Config:
        from_attributes = True


class CardSharingSensitiveResponse(CardSharingResponse):
    """Full response including decrypted cardNo and cardCvc — CEO/Director only."""
    cardNo: str
    cardCvc: str