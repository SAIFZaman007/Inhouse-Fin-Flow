"""
app/modules/card_sharing/service.py
================================================================================
v4 — Changes from v3.1:

Encryption contract (unchanged):
  encrypt_value() / decrypt_value() from app.core.security (Fernet AES)
  Encrypt BEFORE write, decrypt AFTER read (sensitive endpoint only)
================================================================================
"""
import io
from datetime import date as dt_date, datetime, time
from decimal import Decimal
from typing import List, Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from fastapi import HTTPException, UploadFile
from prisma import Json, Prisma

from app.core.cloudinary_service import upload_card_screenshot
from app.core.security import decrypt_value, encrypt_value

from .schema import CardSharingCreate, CardSharingUpdate


# ── Date helper (fix #3) ──────────────────────────────────────────────────────

def _to_datetime(d: dt_date) -> datetime:
    """
    Convert a date to a datetime at midnight.
    Prisma's @db.Date DateTime fields reject bare datetime.date objects —
    only datetime.datetime is accepted by the JSON serialiser.
    """
    if isinstance(d, datetime):
        return d
    return datetime.combine(d, time.min)


# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialize_card(card, include_sensitive: bool = False) -> dict:
    """
    Map Prisma CardSharing model → safe response dict.
    The account relation MUST be included in the originating query.
    """
    card_details = card.cardDetails
    if not isinstance(card_details, list):
        card_details = []

    base = {
        "id":                  card.id,
        "serialNo":            card.serialNo,
        "date":                card.date,
        "details":             card.details,
        "payoneerAccountName": card.account.accountName if card.account else "",
        "cardNo":              "****",
        "cardExpire":          card.cardExpire,
        "cardCvc":             "***",
        "cardDetails":         card_details,
        "cardVendor":          card.cardVendor,
        "cardLimit":           card.cardLimit,
        "cardPaymentReceive":  card.cardPaymentReceive,
        "cardReceiveBank":     card.cardReceiveBank,
        "mailDetails":         card.mailDetails,
        "createdAt":           card.createdAt,
        "updatedAt":           card.updatedAt,
    }
    if include_sensitive:
        base["cardNo"]  = decrypt_value(card.cardNo)
        base["cardCvc"] = decrypt_value(card.cardCvc)
    return base


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create_card(db: Prisma, data: CardSharingCreate):
    """
    Create a card record.

    Lookup by accountName (case-insensitive exact match) replaces the old
    account_id UUID approach — much friendlier for API consumers.
    """
    account = await db.payoneeraccount.find_first(
        where={"accountName": {"equals": data.account_name, "mode": "insensitive"}}
    )
    if not account:
        raise HTTPException(
            status_code=404,
            detail=f"Payoneer account '{data.account_name}' not found",
        )

    existing = await db.cardsharing.find_unique(where={"serialNo": data.serial_no})
    if existing:
        raise HTTPException(status_code=409, detail="Serial number already exists")

    card = await db.cardsharing.create(
        data={
            "serialNo":            data.serial_no,
            "date":                _to_datetime(data.date),
            "details":             data.details,
            # Root Cause 1 FIX — relation requires connect syntax, not bare FK scalar
            "account":             {"connect": {"id": account.id}},
            "cardNo":              encrypt_value(data.card_no),
            "cardExpire":          data.card_expire,
            "cardCvc":             encrypt_value(data.card_cvc),
            # Root Cause 2 FIX — cardDetails is Json in schema, must wrap with Json()
            "cardDetails":         Json(data.card_details),
            "cardVendor":          data.card_vendor,
            "cardLimit":           data.card_limit,
            "cardPaymentReceive":  data.card_payment_received,
            "cardReceiveBank":     data.card_receiver_bank,
            "mailDetails":         data.mail_details,
        },
        include={"account": True},
    )
    return _serialize_card(card, include_sensitive=False)


async def list_cards(
    db:               Prisma,
    include_sensitive: bool = False,
    serial_no:         Optional[str] = None,
    account_name:      Optional[str] = None,
    date_filter:       Optional[dict] = None,
):
    """
    List cards with optional filters.

    Filters (all combinable):
      serial_no    — case-insensitive substring search on serialNo
      account_name — case-insensitive substring search on the related accountName
      date_filter  — Prisma-compatible dict from DateRangeFilter.to_prisma_filter()
    """
    where: dict = {}

    if date_filter:
        where["date"] = date_filter

    if serial_no:
        where["serialNo"] = {"contains": serial_no, "mode": "insensitive"}

    if account_name:
        # Filter via the relation: cards whose linked account name matches
        where["account"] = {
            "is": {
                "accountName": {"contains": account_name, "mode": "insensitive"}
            }
        }

    cards = await db.cardsharing.find_many(
        where=where,
        order={"date": "desc"},
        include={"account": True},
    )
    return [_serialize_card(c, include_sensitive) for c in cards]


async def get_card(db: Prisma, card_id: str, include_sensitive: bool = False):
    card = await db.cardsharing.find_unique(
        where={"id": card_id},
        include={"account": True},
    )
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return _serialize_card(card, include_sensitive)


async def update_card(db: Prisma, card_id: str, data: CardSharingUpdate):
    existing = await db.cardsharing.find_unique(where={"id": card_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Card not found")

    raw = data.model_dump(exclude_none=True)
    if not raw:
        raise HTTPException(status_code=400, detail="No fields to update")

    _FIELD_MAP = {
        "card_no":               "cardNo",
        "card_expire":           "cardExpire",
        "card_cvc":              "cardCvc",
        "card_vendor":           "cardVendor",
        "card_limit":            "cardLimit",
        "card_payment_received": "cardPaymentReceive",
        "card_receiver_bank":    "cardReceiveBank",
        "mail_details":          "mailDetails",
        "card_details":          "cardDetails",
    }

    mapped: dict = {}
    for k, v in raw.items():
        prisma_key = _FIELD_MAP.get(k, k)

        if prisma_key in {"cardNo", "cardCvc"}:
            v = encrypt_value(v)

        # cardDetails is Json — wrap with Json(), never use {"set": ...}
        if prisma_key == "cardDetails":
            mapped[prisma_key] = Json(v) if isinstance(v, list) else Json([])
        else:
            mapped[prisma_key] = v

    updated = await db.cardsharing.update(
        where={"id": card_id},
        data=mapped,
        include={"account": True},
    )
    return _serialize_card(updated, include_sensitive=False)


async def delete_card(db: Prisma, card_id: str):
    existing = await db.cardsharing.find_unique(where={"id": card_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Card not found")
    await db.cardsharing.delete(where={"id": card_id})


# ── Screenshot management ─────────────────────────────────────────────────────

async def add_screenshot(db: Prisma, card_id: str, file: UploadFile) -> dict:
    """
    Upload a single screenshot file to Cloudinary and append its URL
    to the card's cardDetails list.

    BUG FIX: uses {"set": new_list} for the Prisma scalar-list update (fix #2).
    BUG FIX: relies on the async-safe cloudinary_service wrapper (fix #1).
    """
    card = await db.cardsharing.find_unique(where={"id": card_id})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    result     = await upload_card_screenshot(file, card.serialNo)
    secure_url = result["secure_url"]
    public_id  = result["public_id"]

    existing: list = card.cardDetails if isinstance(card.cardDetails, list) else []
    new_list = existing + [secure_url]

    await db.cardsharing.update(
        where={"id": card_id},
        data={"cardDetails": Json(new_list)},
    )
    return {
        "url":              secure_url,
        "publicId":         public_id,
        "totalScreenshots": len(new_list),
    }


async def add_screenshots_bulk(
    db: Prisma, card_id: str, files: List[UploadFile]
) -> dict:
    """
    Upload multiple screenshot files at once (used by create / update endpoints
    when screenshots are attached directly to the form).

    Returns updated total screenshot count.
    """
    card = await db.cardsharing.find_unique(where={"id": card_id})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    existing: list = card.cardDetails if isinstance(card.cardDetails, list) else []
    uploaded_urls: list[str] = []

    for file in files:
        result = await upload_card_screenshot(file, card.serialNo)
        uploaded_urls.append(result["secure_url"])

    new_list = existing + uploaded_urls

    await db.cardsharing.update(
        where={"id": card_id},
        data={"cardDetails": Json(new_list)},
    )
    return {
        "uploadedCount":    len(uploaded_urls),
        "totalScreenshots": len(new_list),
        "urls":             uploaded_urls,
    }


async def remove_screenshot(db: Prisma, card_id: str, screenshot_url: str) -> dict:
    card = await db.cardsharing.find_unique(where={"id": card_id})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    existing: list = card.cardDetails if isinstance(card.cardDetails, list) else []
    if screenshot_url not in existing:
        raise HTTPException(status_code=404, detail="Screenshot URL not found")

    new_list = [u for u in existing if u != screenshot_url]

    await db.cardsharing.update(
        where={"id": card_id},
        data={"cardDetails": Json(new_list)},
    )
    return {"totalScreenshots": len(new_list)}


# ── Excel export ──────────────────────────────────────────────────────────────

_HEADERS = [
    "Date", "Serial No", "Account Name", "Card Vendor",
    "Card Expire", "Card Limit", "Payment Received", "Receiver Bank",
    "Screenshots", "Details", "Mail Details",
]

_HEADER_FILL  = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT  = Font(bold=True, color="FFFFFF", size=11)
_ALT_ROW_FILL = PatternFill("solid", fgColor="D6E4F0")
_CENTER       = Alignment(horizontal="center", vertical="center")
_LEFT         = Alignment(horizontal="left",   vertical="center", wrap_text=True)

_COL_WIDTHS = [12, 18, 26, 16, 14, 16, 18, 22, 12, 36, 36]


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, dt_date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


async def export_cards(
    db:           Prisma,
    date_filter:  Optional[dict] = None,
    serial_no:    Optional[str]  = None,
    account_name: Optional[str]  = None,
    label:        str = "card_sharing",
) -> tuple[bytes, str]:
    """
    Build and return (xlsx_bytes, filename).

    SECURITY: cardNo and cardCvc are NEVER included in exports.
    Column count and screenshot URLs are shown; actual card numbers are omitted.
    """
    cards_raw = await db.cardsharing.find_many(
        where=_build_where(date_filter, serial_no, account_name),
        order={"date": "desc"},
        include={"account": True},
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Card Sharing"

    # ── Header ────────────────────────────────────────────────────────────────
    ws.row_dimensions[1].height = 22
    for col_idx, (header, width) in enumerate(zip(_HEADERS, _COL_WIDTHS), start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font      = _HEADER_FONT
        cell.fill      = _HEADER_FILL
        cell.alignment = _CENTER
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # ── Data rows ─────────────────────────────────────────────────────────────
    for row_idx, card in enumerate(cards_raw, start=2):
        fill = _ALT_ROW_FILL if row_idx % 2 == 0 else None
        details_list = card.cardDetails if isinstance(card.cardDetails, list) else []

        values = [
            _fmt(card.date),
            _fmt(card.serialNo),
            card.account.accountName if card.account else "",
            _fmt(card.cardVendor),
            _fmt(card.cardExpire),
            float(card.cardLimit),
            float(card.cardPaymentReceive),
            _fmt(card.cardReceiveBank),
            len(details_list),            # screenshot count — not the URLs
            _fmt(card.details),
            _fmt(card.mailDetails),
        ]
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = _CENTER if col_idx in (1, 8, 9) else _LEFT
            if fill:
                cell.fill = fill

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{label}.xlsx"
    return buffer.read(), filename


def _build_where(
    date_filter:  Optional[dict],
    serial_no:    Optional[str],
    account_name: Optional[str],
) -> dict:
    where: dict = {}
    if date_filter:
        where["date"] = date_filter
    if serial_no:
        where["serialNo"] = {"contains": serial_no, "mode": "insensitive"}
    if account_name:
        where["account"] = {
            "is": {
                "accountName": {"contains": account_name, "mode": "insensitive"}
            }
        }
    return where