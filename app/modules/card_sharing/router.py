"""
app/modules/card_sharing/router.py
════════════════════════════════════════════════════════════════════════════════
v5 — Transparent card data + structured DELETE responses

Changes vs v4.1:
  • cardNo and cardCvc are fully visible in all responses — no masking.
  • GET /{card_id}/secure still exists for backward compatibility but now
    returns the same unmasked data as GET /{card_id} (both use CEO_DIRECTOR).
  • DELETE /{card_id}              → structured JSON response body.
  • DELETE /{card_id}/screenshots  → structured JSON response body.
  • service.py is NOT affected — include_sensitive flag is kept as-is so
    the service signature remains stable.
════════════════════════════════════════════════════════════════════════════════
"""
from datetime import date                               
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR
from app.shared.filters import DateRangeFilter

from .schema import (
    CardSharingCreate,
    CardSharingResponse, CardSharingSensitiveResponse,
    CardSharingUpdate,
    ScreenshotRemoveBody, ScreenshotUploadResponse,
)
from .service import (
    add_screenshot, add_screenshots_bulk, create_card, delete_card,
    export_cards, get_card, list_cards, remove_screenshot, update_card,
)

router = APIRouter(prefix="/card-sharing", tags=["Card Sharing"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CardSharingResponse])
async def get_cards(
    serial_no:    Optional[str] = Query(
        default=None,
        description="Partial / case-insensitive match on serial number",
    ),
    account_name: Optional[str] = Query(
        default=None,
        description="Partial / case-insensitive match on Payoneer account name",
    ),
    filters: DateRangeFilter = Depends(),
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    List all card sharing records — all fields fully visible.

    Filters (all combinable):
    - `serial_no`    — case-insensitive substring search
    - `account_name` — case-insensitive substring search on the linked account name
    - Date filters   — period (daily/weekly/monthly/yearly) or explicit from/to
    """
    return await list_cards(
        db,
        include_sensitive=True,
        serial_no=serial_no,
        account_name=account_name,
        date_filter=filters.to_prisma_filter() or None,
    )


# ── Export ────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export card sharing records to Excel",
    response_description="Excel workbook download",
)
async def export_cards_endpoint(
    serial_no:    Optional[str] = Query(default=None, description="Partial match on serial number"),
    account_name: Optional[str] = Query(default=None, description="Partial match on account name"),
    filters:      DateRangeFilter = Depends(),
    db:           Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Export filtered card records to Excel.

    All card fields are included in the export.
    Screenshot URLs are replaced with a count for readability.
    """
    meta     = filters.meta()
    date_str = (meta["dateRange"]["from"] or "all").replace("-", "")
    label    = f"card_sharing_{date_str}"

    data, filename = await export_cards(
        db,
        date_filter=filters.to_prisma_filter() or None,
        serial_no=serial_no,
        account_name=account_name,
        label=label,
    )
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Create  (multipart/form-data — supports optional screenshot uploads) ──────

@router.post("", response_model=CardSharingResponse, status_code=201)
async def add_card(
    # ── Card fields ────────────────────────────────────────────────────────────
    serial_no:             str            = Form(..., description="Unique card serial number"),
    date:                  date           = Form(..., description="Card date (YYYY-MM-DD)"),
    account_name:          str            = Form(..., description="Payoneer accountName (not UUID)"),
    card_no:               str            = Form(..., description="Card number"),
    card_expire:           str            = Form(..., description="Expiry (MM/YY)"),
    card_cvc:              str            = Form(..., description="CVC"),
    card_vendor:           str            = Form(..., description="Card vendor / issuer"),
    card_limit:            float          = Form(..., description="Card spending limit"),
    card_payment_received: float          = Form(0.0, description="Amount already received"),
    card_receiver_bank:    str            = Form("",  description="Receiver bank / channel"),
    details:               Optional[str]  = Form(None, description="General notes"),
    mail_details:          Optional[str]  = Form(None, description="Mail / email notes"),
    # ── Optional screenshot uploads ────────────────────────────────────────────
    screenshots: List[UploadFile] = File(
        default=[],
        description="Optional screenshot images (JPG/PNG/WebP). "
                    "Uploaded to Cloudinary; URLs appended to cardDetails.",
    ),
    db:  Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Create a card record.

    • Provide **accountName** (human-readable) — the system looks up the
      matching PayoneerAccount automatically.
    • Optionally attach one or more screenshot files in the same request.
    • `date` must be a valid ISO-8601 date string: YYYY-MM-DD.
    • cardNo and cardCvc are stored and returned as plain text — no encryption.
    """
    payload = CardSharingCreate(
        serial_no=serial_no,
        date=date,
        details=details,
        account_name=account_name,
        card_no=card_no,
        card_expire=card_expire,
        card_cvc=card_cvc,
        card_details=[],
        card_vendor=card_vendor,
        card_limit=Decimal(str(card_limit)),
        card_payment_received=Decimal(str(card_payment_received)),
        card_receiver_bank=card_receiver_bank,
        mail_details=mail_details,
    )

    card_response = await create_card(db, payload)

    # Upload screenshots immediately after creation if any were attached
    if screenshots:
        valid_files = [f for f in screenshots if f.filename]
        if valid_files:
            await add_screenshots_bulk(db, card_response["id"], valid_files)
            # Refresh card to include uploaded screenshot URLs
            card_response = await get_card(db, card_response["id"], include_sensitive=True)

    return card_response


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{card_id}", response_model=CardSharingResponse)
async def get_card_masked(
    card_id: str,
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """Get a single card — all fields fully visible."""
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
    """Returns full card data. Kept for backward compatibility."""
    return await get_card(db, card_id, include_sensitive=True)


# ── Update  (multipart/form-data — supports optional screenshot uploads) ──────

@router.patch("/{card_id}", response_model=CardSharingResponse)
async def update_card_endpoint(
    card_id:               str,
    details:               Optional[str]   = Form(None),
    card_no:               Optional[str]   = Form(None, description="New card number"),
    card_expire:           Optional[str]   = Form(None),
    card_cvc:              Optional[str]   = Form(None, description="New CVC"),
    card_vendor:           Optional[str]   = Form(None),
    card_limit:            Optional[float] = Form(None),
    card_payment_received: Optional[float] = Form(None),
    card_receiver_bank:    Optional[str]   = Form(None),
    mail_details:          Optional[str]   = Form(None),
    # ── Optional screenshot uploads ────────────────────────────────────────────
    screenshots: List[UploadFile] = File(
        default=[],
        description="New screenshot images to append to this card's cardDetails.",
    ),
    db:  Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Partial update — only provided fields are changed.

    Attach screenshot files to append them to the card's Cloudinary gallery
    without a separate API call.
    """
    payload = CardSharingUpdate(
        details=details,
        card_no=card_no,
        card_expire=card_expire,
        card_cvc=card_cvc,
        card_vendor=card_vendor,
        card_limit=Decimal(str(card_limit)) if card_limit is not None else None,
        card_payment_received=Decimal(str(card_payment_received)) if card_payment_received is not None else None,
        card_receiver_bank=card_receiver_bank,
        mail_details=mail_details,
    )

    # Only call update_card if there are actual field changes
    raw = payload.model_dump(exclude_none=True)
    if raw:
        card_response = await update_card(db, card_id, payload)
    else:
        card_response = await get_card(db, card_id, include_sensitive=True)

    # Upload any attached screenshots
    if screenshots:
        valid_files = [f for f in screenshots if f.filename]
        if valid_files:
            await add_screenshots_bulk(db, card_id, valid_files)
            card_response = await get_card(db, card_id, include_sensitive=True)

    return card_response


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{card_id}", status_code=200)
async def delete_card_endpoint(
    card_id: str,
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Delete a card record and all associated data.
    Returns a structured success message.
    """
    await delete_card(db, card_id)
    return {
        "success": True,
        "message": "Card record deleted successfully.",
        "id": card_id,
    }


# ── Screenshot management  (dedicated endpoints still available) ───────────────

@router.post(
    "/{card_id}/screenshots",
    response_model=ScreenshotUploadResponse,
    status_code=201,
    summary="Upload a single card screenshot to Cloudinary",
)
async def upload_screenshot(
    card_id: str,
    file:    UploadFile = File(..., description="Image file (JPG, PNG, WebP)"),
    db:      Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    """
    Upload one screenshot file. The secure_url is appended to cardDetails.

    Tip: You can also upload screenshots directly in the POST / PATCH endpoints
    by attaching files to the `screenshots` field — avoids a second round-trip.
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
    Remove a Cloudinary URL from the card's cardDetails list.
    Returns a structured success message confirming the removed URL.
    """
    await remove_screenshot(db, card_id, body.url)
    return {
        "success": True,
        "message": "Screenshot removed successfully.",
        "card_id": card_id,
        "removed_url": body.url,
    }