"""
app/modules/card_sharing/schema.py
================================================================================
v5 — Transparent card fields (no masking / no encryption):

  cardNo and cardCvc are now fully visible in ALL responses.
  CardSharingSensitiveResponse is kept as an alias of CardSharingResponse
  for backward-compatible route imports — both expose the same full data.

  account_id  → account_name / payoneer_account_name  (friendlier lookup by name)

  The service layer performs a case-insensitive find_first on
  PayoneerAccount.accountName so users never need to know internal UUIDs.

  cardDetails holds Cloudinary screenshot URLs — managed separately.
================================================================================
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Create ─────────────────────────────────────────────────────────────────────

class CardSharingCreate(BaseModel):
    """
    Create a new card record.

    account_name — provide the Payoneer accountName (e.g. "My Payoneer Account").
                   The service will look it up; a 404 is returned if not found.
                   This replaces the legacy account_id UUID field for better UX.
    """
    serial_no:             str
    date:                  date
    details:               Optional[str]   = None
    account_name:          str             = Field(..., description="Payoneer accountName (not UUID)")
    card_no:               str
    card_expire:           str
    card_cvc:              str
    card_details:          List[str]       = Field(default_factory=list)
    card_vendor:           str
    card_limit:            Decimal
    card_payment_received: Decimal         = Decimal("0")
    card_receiver_bank:    str             = ""
    mail_details:          Optional[str]   = None


# ── Update ─────────────────────────────────────────────────────────────────────

class CardSharingUpdate(BaseModel):
    """
    Partial update — only provided fields are patched.

    card_details: supply the FULL replacement list of Cloudinary screenshot URLs.
    Use POST /{id}/screenshots to append a new file upload instead.
    """
    details:               Optional[str]      = None
    card_no:               Optional[str]      = None
    card_expire:           Optional[str]      = None
    card_cvc:              Optional[str]      = None
    card_vendor:           Optional[str]      = None
    card_limit:            Optional[Decimal]  = None
    card_payment_received: Optional[Decimal]  = None
    card_receiver_bank:    Optional[str]      = None
    mail_details:          Optional[str]      = None
    card_details:          Optional[List[str]] = None   # full replacement list


# ── Responses ──────────────────────────────────────────────────────────────────

class CardSharingResponse(BaseModel):
    """
    Standard response — all card fields are fully visible (no masking).
    cardNo and cardCvc are returned as stored.
    """
    id:                  str
    serialNo:            str
    date:                date
    details:             Optional[str]
    payoneerAccountName: str
    cardNo:              str               # fully visible — no masking
    cardExpire:          str
    cardCvc:             str               # fully visible — no masking
    cardDetails:         List[str]
    cardVendor:          str
    cardLimit:           Decimal
    cardPaymentReceive:  Decimal           # DB field name kept as-is
    cardReceiveBank:     str
    mailDetails:         Optional[str]
    createdAt:           datetime
    updatedAt:           datetime

    class Config:
        from_attributes = True


# CardSharingSensitiveResponse is kept as a direct alias so that existing
# route imports (GET /{id}/secure) continue to resolve without any changes.
CardSharingSensitiveResponse = CardSharingResponse


# ── Screenshot upload ──────────────────────────────────────────────────────────

class ScreenshotUploadResponse(BaseModel):
    url:              str
    publicId:         str
    totalScreenshots: int


# ── Screenshot remove ─────────────────────────────────────────────────────────

class ScreenshotRemoveBody(BaseModel):
    url: str