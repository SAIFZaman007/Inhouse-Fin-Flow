"""
app/modules/card_sharing/schema.py
================================================================================
v7 — Simplified input surface
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

    ### Required
    ``card_name`` is the only mandatory field — it uniquely identifies the
    card's label and is the sole required input.

    ### Optional fields
    All other fields are optional and receive safe server-side defaults when
    omitted:
    - ``serial_no``             → auto-generated UUID if not provided
    - ``card_no`` / ``card_cvc``→ empty string (encrypted at rest)
    - ``card_expire``           → empty string
    - ``card_vendor``           → empty string
    - ``card_limit``            → Decimal("0")
    - ``card_payment_received`` → Decimal("0")
    - ``card_receiver_bank``    → empty string
    - ``details``               → None
    - ``mail_details``          → None

    ### Removed fields
    ``date`` — the service records the current server timestamp automatically.
    ``card_details`` — screenshots are managed via the dedicated
    ``POST /{id}/screenshots`` endpoint.

    ### Sensitive fields
    ``card_no`` and ``card_cvc`` are transmitted in plain-text from the
    caller; the service encrypts them before writing to the database.
    Responses always return the decrypted values.
    """
    card_name:             str            = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Standalone card label — no relational lookup.  "
            "e.g. 'Marketing VISA', 'Team Payoneer #3'.  "
            "This is the only required field."
        ),
    )
    serial_no:             Optional[str]     = Field(
        default=None,
        description="Unique card serial number. Auto-generated if not supplied.",
    )
    card_no:               Optional[str]     = Field(
        default=None,
        description="Card number — transmitted plain-text, stored encrypted, returned decrypted.",
    )
    card_expire:           Optional[str]     = Field(
        default=None,
        description="Expiry date (MM/YY).",
    )
    card_cvc:              Optional[str]     = Field(
        default=None,
        description="CVC — transmitted plain-text, stored encrypted, returned decrypted.",
    )
    card_vendor:           Optional[str]     = Field(
        default=None,
        description="Card vendor / issuer.",
    )
    card_limit:            Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Card spending limit in USD.",
    )
    card_payment_received: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Amount already received from the vendor.",
    )
    card_receiver_bank:    Optional[str]     = Field(
        default=None,
        description="Receiver bank / channel (e.g. 'bKash', 'Payoneer Sub').",
    )
    details:               Optional[str]     = Field(
        default=None,
        description="General notes.",
    )
    mail_details:          Optional[str]     = Field(
        default=None,
        description="Mail / email notes.",
    )


# ── Update ─────────────────────────────────────────────────────────────────────

class CardSharingUpdate(BaseModel):
    """
    Partial update — only provided fields are patched.

    Sending an empty body ``{}`` is idempotent.

    ### Removed fields
    ``card_details`` — use the dedicated ``POST / DELETE /{id}/screenshots``
    endpoints to manage the Cloudinary screenshot gallery.

    ### Sensitive fields
    ``card_no`` and ``card_cvc``, when supplied, are encrypted before being
    written to the DB.  Responses always return decrypted values.
    """
    card_name:             Optional[str]     = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Updated standalone card label — no relational lookup.",
    )
    serial_no:             Optional[str]     = Field(
        default=None,
        description="Updated serial number.",
    )
    card_no:               Optional[str]     = Field(
        default=None,
        description="Updated card number — stored encrypted, returned decrypted.",
    )
    card_expire:           Optional[str]     = Field(
        default=None,
        description="Updated expiry date (MM/YY).",
    )
    card_cvc:              Optional[str]     = Field(
        default=None,
        description="Updated CVC — stored encrypted, returned decrypted.",
    )
    card_vendor:           Optional[str]     = Field(
        default=None,
        description="Updated card vendor / issuer.",
    )
    card_limit:            Optional[Decimal] = Field(default=None, ge=0)
    card_payment_received: Optional[Decimal] = Field(default=None, ge=0)
    card_receiver_bank:    Optional[str]     = Field(default=None)
    details:               Optional[str]     = Field(default=None)
    mail_details:          Optional[str]     = Field(default=None)


# ── Responses ──────────────────────────────────────────────────────────────────

class CardSharingResponse(BaseModel):
    """
    Standard card response — all fields returned, sensitive values decrypted.

    ``cardNo`` and ``cardCvc``
        Always returned DECRYPTED (plain-text) — the front-end renders them
        directly with no additional work.  Encryption / decryption is
        transparent and handled entirely in the service layer.

    ``cardName``
        Standalone, free-form label for this card.  No FK or cross-module
        dependency is surfaced to the caller.

    ``cardDetails``
        List of Cloudinary screenshot URLs managed via the dedicated
        screenshot endpoints.

    ``date``
        Server-recorded timestamp of when the card was created (auto-set).
    """
    id:                 str
    serialNo:           str
    date:               date
    details:            Optional[str]
    cardName:           str               # standalone label
    cardNo:             str               # always returned decrypted by the service
    cardExpire:         str
    cardCvc:            str               # always returned decrypted by the service
    cardDetails:        List[str]         # Cloudinary screenshot URLs
    cardVendor:         str
    cardLimit:          Decimal
    cardPaymentReceive: Decimal
    cardReceiveBank:    str
    mailDetails:        Optional[str]
    createdAt:          datetime
    updatedAt:          datetime

    class Config:
        from_attributes = True


# CardSharingSensitiveResponse is a direct alias so that existing route imports
# (GET /{id}/secure) continue to resolve without any changes.
CardSharingSensitiveResponse = CardSharingResponse


# ── Screenshot upload ──────────────────────────────────────────────────────────

class ScreenshotUploadResponse(BaseModel):
    """Response returned after a successful screenshot upload to Cloudinary."""
    url:              str
    publicId:         str
    totalScreenshots: int


# ── Screenshot remove ─────────────────────────────────────────────────────────

class ScreenshotRemoveBody(BaseModel):
    """Request body for removing a screenshot URL from a card's cardDetails."""
    url: str