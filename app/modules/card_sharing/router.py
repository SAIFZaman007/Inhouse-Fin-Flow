"""
app/modules/card_sharing/router.py
================================================================================
v8 — Multi-column OR keyword search on GET /card-sharing
================================================================================
"""
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR
from app.shared.filters import DateRangeFilter

from .schema import (
    CardSharingCreate,
    CardSharingResponse,
    CardSharingSensitiveResponse,
    CardSharingUpdate,
    ScreenshotRemoveBody,
    ScreenshotUploadResponse,
)
from .service import (
    add_screenshot,
    add_screenshots_bulk,
    create_card,
    delete_card,
    export_cards,
    get_card,
    list_cards,
    remove_screenshot,
    update_card,
)

router = APIRouter(prefix="/card-sharing", tags=["Card Sharing"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CardSharingResponse])
async def get_cards(
    serial_no: Optional[str] = Query(
        default=None,
        description="Partial / case-insensitive match on serial number.",
    ),
    card_name: Optional[str] = Query(
        default=None,
        description="Partial / case-insensitive match on the card's own label (``cardName``).",
    ),
    search: Annotated[
        Optional[str],
        Query(
            description=(
                "Case-insensitive keyword search across FIVE columns simultaneously "
                "(OR logic — a single keyword matches any of these fields): "
                "details | cardName | cardReceiveBank | mailDetails | cardVendor. "
                "e.g. ?search=bKash returns every card where any of those fields "
                "mentions 'bKash'."
            )
        ),
    ] = None,
    filters: DateRangeFilter = Depends(),
    db:      Prisma          = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    List all card sharing records — all fields fully visible.

    ``cardNo`` and ``cardCvc`` are returned **decrypted** in every row.

    ### Filters (all combinable)
    | Parameter   | Behaviour                                                        |
    |-------------|------------------------------------------------------------------|
    | `serial_no` | Case-insensitive substring match on serial number                |
    | `card_name` | Case-insensitive substring match on card label (cardName)        |
    | `search`    | OR keyword search across **details**, **cardName**, **cardReceiveBank**, **mailDetails**, **cardVendor** |
    | Date filters| Period (daily/weekly/monthly/yearly) or explicit from/to range   |
    """
    return await list_cards(
        db,
        include_sensitive=True,
        serial_no=serial_no,
        account_name=card_name,        # service param name kept for compatibility
        date_filter=filters.to_prisma_filter() or None,
        search=search,
    )


# ── Export ────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export card sharing records to Excel",
    response_description="Excel workbook (.xlsx) download",
)
async def export_cards_endpoint(
    serial_no: Optional[str] = Query(
        default=None,
        description="Partial match on serial number.",
    ),
    card_name: Optional[str] = Query(
        default=None,
        description="Partial match on card name / label.",
    ),
    search: Annotated[
        Optional[str],
        Query(
            description=(
                "Case-insensitive keyword search across details, cardName, "
                "cardReceiveBank, mailDetails, and cardVendor (OR logic)."
            )
        ),
    ] = None,
    filters: DateRangeFilter = Depends(),
    db:      Prisma          = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Export filtered card records to an Excel workbook.

    Supports the same ``search`` OR filter as ``GET /card-sharing``.

    ### Included columns
    Date · Serial No · Card Name · Card Vendor · Card Expire ·
    Card Limit · Payment Received · Receiver Bank · Screenshots · Details · Mail Details

    ### Security
    ``cardNo`` and ``cardCvc`` are **intentionally excluded** from the
    export — sensitive PAN / CVC data must not appear in downloadable files.
    Screenshot URLs are replaced with a count for readability.
    """
    meta     = filters.meta()
    date_str = (meta["dateRange"]["from"] or "all").replace("-", "")
    label    = f"card_sharing_{date_str}"

    data, filename = await export_cards(
        db,
        date_filter=filters.to_prisma_filter() or None,
        serial_no=serial_no,
        account_name=card_name,        # service param name kept for compatibility
        search=search,
        label=label,
    )
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("", response_model=CardSharingResponse, status_code=201)
async def add_card(
    # ── Only required field ───────────────────────────────────────────────────
    card_name: str = Form(
        ...,
        description=(
            "Human-readable card label — the only required field.  "
            "e.g. 'Marketing VISA', 'Team Payoneer #3'.  "
            "Standalone — no relation to Payoneer or any other module."
        ),
    ),
    # ── All remaining fields are optional ─────────────────────────────────────
    serial_no: Optional[str] = Form(
        default=None,
        description="Unique card serial number. Auto-generated (UUID) if not supplied.",
    ),
    card_no: Optional[str] = Form(
        default=None,
        description="Card number — transmitted plain-text, stored encrypted, returned decrypted.",
    ),
    card_expire: Optional[str] = Form(
        default=None,
        description="Expiry date (MM/YY).",
    ),
    card_cvc: Optional[str] = Form(
        default=None,
        description="CVC — transmitted plain-text, stored encrypted, returned decrypted.",
    ),
    card_vendor: Optional[str] = Form(
        default=None,
        description="Card vendor / issuer.",
    ),
    card_limit: Optional[float] = Form(
        default=None,
        description="Card spending limit in USD.",
    ),
    card_payment_received: Optional[float] = Form(
        default=None,
        description="Amount already received from the vendor.",
    ),
    card_receiver_bank: Optional[str] = Form(
        default=None,
        description="Receiver bank / channel (e.g. 'bKash', 'Payoneer Sub').",
    ),
    details: Optional[str] = Form(
        default=None,
        description="General notes.",
    ),
    mail_details: Optional[str] = Form(
        default=None,
        description="Mail / email notes.",
    ),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Create a new card record.

    ### Only ``card_name`` is required
    Every other field is optional — the server applies safe defaults for
    anything not supplied.

    ### Date
    Automatically set to the current server timestamp — callers do not
    supply this field.

    ### Screenshots
    Screenshots are managed separately via the dedicated
    ``POST /{id}/screenshots`` endpoint — they are not part of this request.

    ### Sensitive fields
    ``card_no`` and ``card_cvc`` are encrypted at rest.  The response always
    returns the **decrypted** values — no client-side work required.
    """
    payload = CardSharingCreate(
        card_name=card_name,
        serial_no=serial_no,
        card_no=card_no,
        card_expire=card_expire,
        card_cvc=card_cvc,
        card_vendor=card_vendor,
        card_limit=Decimal(str(card_limit)) if card_limit is not None else None,
        card_payment_received=Decimal(str(card_payment_received)) if card_payment_received is not None else None,
        card_receiver_bank=card_receiver_bank,
        details=details,
        mail_details=mail_details,
    )
    return await create_card(db, payload)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{card_id}", response_model=CardSharingResponse)
async def get_card_detail(
    card_id: str,
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Get a single card record — all fields fully visible.

    ``cardNo`` and ``cardCvc`` are returned **decrypted**.
    """
    return await get_card(db, card_id, include_sensitive=True)


@router.get(
    "/{card_id}/secure",
    response_model=CardSharingSensitiveResponse,
    summary="Get full card details — CEO/Director only",
)
async def get_card_secure(
    card_id: str,
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Returns full card data including decrypted sensitive fields.

    Kept for backward compatibility — identical response to ``GET /{card_id}``.
    """
    return await get_card(db, card_id, include_sensitive=True)


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{card_id}", response_model=CardSharingResponse)
async def update_card_endpoint(
    card_id: str,
    card_name: Optional[str] = Form(
        default=None,
        description="Updated card label — standalone, no relational lookup.",
    ),
    serial_no: Optional[str] = Form(
        default=None,
        description="Updated serial number.",
    ),
    card_no: Optional[str] = Form(
        default=None,
        description="Updated card number — stored encrypted, returned decrypted.",
    ),
    card_expire: Optional[str] = Form(
        default=None,
        description="Updated expiry date (MM/YY).",
    ),
    card_cvc: Optional[str] = Form(
        default=None,
        description="Updated CVC — stored encrypted, returned decrypted.",
    ),
    card_vendor: Optional[str] = Form(
        default=None,
        description="Updated card vendor / issuer.",
    ),
    card_limit: Optional[float] = Form(default=None),
    card_payment_received: Optional[float] = Form(default=None),
    card_receiver_bank: Optional[str] = Form(default=None),
    details: Optional[str] = Form(default=None),
    mail_details: Optional[str] = Form(default=None),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Partial update — only provided fields are changed.

    Sending an empty body ``{}`` is idempotent.

    ### Screenshots
    Use the dedicated ``POST / DELETE /{id}/screenshots`` endpoints to
    manage the card's Cloudinary screenshot gallery — screenshots are not
    part of this request.

    ``cardNo`` and ``cardCvc``, when supplied, are re-encrypted before
    being stored.
    """
    payload = CardSharingUpdate(
        card_name=card_name,
        serial_no=serial_no,
        card_no=card_no,
        card_expire=card_expire,
        card_cvc=card_cvc,
        card_vendor=card_vendor,
        card_limit=Decimal(str(card_limit)) if card_limit is not None else None,
        card_payment_received=Decimal(str(card_payment_received)) if card_payment_received is not None else None,
        card_receiver_bank=card_receiver_bank,
        details=details,
        mail_details=mail_details,
    )

    raw = payload.model_dump(exclude_none=True)
    if raw:
        return await update_card(db, card_id, payload)
    return await get_card(db, card_id, include_sensitive=True)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{card_id}", status_code=200)
async def delete_card_endpoint(
    card_id: str,
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Hard-delete a card record and all associated data.

    Returns a structured success envelope.
    """
    await delete_card(db, card_id)
    return {
        "success": True,
        "message": "Card record deleted successfully.",
        "id":      card_id,
    }


# ── Screenshot management  (dedicated endpoints — unchanged) ──────────────────

@router.post(
    "/{card_id}/screenshots",
    response_model=ScreenshotUploadResponse,
    status_code=201,
    summary="Upload a single card screenshot to Cloudinary",
)
async def upload_screenshot(
    card_id: str,
    file:    UploadFile = File(..., description="Image file (JPG, PNG, WebP)."),
    db:      Prisma     = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Upload one screenshot file.

    The Cloudinary ``secure_url`` is appended to ``cardDetails``.
    Use this endpoint to attach screenshots after a card has been created.
    """
    return await add_screenshot(db, card_id, file)


@router.delete(
    "/{card_id}/screenshots",
    status_code=200,
    summary="Remove a screenshot URL from card details",
)
async def delete_screenshot(
    card_id: str,
    body:    ScreenshotRemoveBody,
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Remove a Cloudinary URL from the card's ``cardDetails`` list.

    Returns a structured success envelope confirming the removed URL.
    """
    await remove_screenshot(db, card_id, body.url)
    return {
        "success":     True,
        "message":     "Screenshot removed successfully.",
        "card_id":     card_id,
        "removed_url": body.url,
    }