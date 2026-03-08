"""
app/modules/card_sharing/service.py
CRUD operations for Card Sharing module.
"""
from fastapi import HTTPException
from prisma import Prisma

from app.core.security import decrypt_value, encrypt_value

from .schema import CardSharingCreate, CardSharingUpdate


async def create_card(db: Prisma, data: CardSharingCreate):
    return await db.cardsharing.create(
        data={
            "serialNo":       data.serial_no,
            "details":        data.details,
            "payoneerAccount": data.payoneer_account,
            "cardNo":         encrypt_value(data.card_no),     
            "cardExpire":     data.card_expire,
            "cardCvc":        encrypt_value(data.card_cvc),    
            "cardVendor":     data.card_vendor,
            "cardLimit":      data.card_limit,
            "cardPaymentRcv": data.card_payment_rcv,
            "cardRcvBank":    data.card_rcv_bank,
            "mailDetails":    data.mail_details,
            "screenshotPath": data.screenshot_path,            
        }
    )


def _serialize_card(card, include_sensitive: bool) -> dict:
    """Convert Prisma CardSharing model to response dict, decrypting sensitive fields if requested."""
    result = {
        "id":               card.id,
        "serialNo":         card.serialNo,
        "details":          card.details,
        "payoneerAccount":  card.payoneerAccount,
        "cardExpire":       card.cardExpire,
        "cardVendor":       card.cardVendor,
        "cardLimit":        card.cardLimit,
        "cardPaymentRcv":   card.cardPaymentRcv,
        "cardRcvBank":      card.cardRcvBank,
        "mailDetails":      card.mailDetails,
        "screenshotPath":   card.screenshotPath,  
    }
    if include_sensitive:
        result["cardNo"]  = decrypt_value(card.cardNo)  
        result["cardCvc"] = decrypt_value(card.cardCvc)  
    return result


async def list_cards(db: Prisma, include_sensitive: bool = False):
    cards = await db.cardsharing.find_many(order={"serialNo": "asc"})
    return [_serialize_card(c, include_sensitive) for c in cards]


async def get_card(db: Prisma, card_id: str, include_sensitive: bool = False):
    card = await db.cardsharing.find_unique(where={"id": card_id})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return _serialize_card(card, include_sensitive)


async def update_card(db: Prisma, card_id: str, data: CardSharingUpdate):
    existing = await db.cardsharing.find_unique(where={"id": card_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Card not found")

    update_data = data.model_dump(exclude_none=True)
    field_map = {
        "card_vendor":      "cardVendor",
        "card_limit":       "cardLimit",
        "card_payment_rcv": "cardPaymentRcv",
        "card_rcv_bank":    "cardRcvBank",
        "mail_details":     "mailDetails",
        "screenshot_path":  "screenshotPath",  
    }
    mapped = {field_map.get(k, k): v for k, v in update_data.items()}
    updated = await db.cardsharing.update(where={"id": card_id}, data=mapped)
    return _serialize_card(updated, include_sensitive=False)


async def delete_card(db: Prisma, card_id: str):
    existing = await db.cardsharing.find_unique(where={"id": card_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Card not found")
    await db.cardsharing.delete(where={"id": card_id})