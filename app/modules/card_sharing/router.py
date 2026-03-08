from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR

from .schema import CardSharingCreate, CardSharingResponse, CardSharingSensitiveResponse, CardSharingUpdate
from .service import create_card, delete_card, get_card, list_cards, update_card

router = APIRouter(prefix="/card-sharing", tags=["Card Sharing"])


@router.get("", response_model=list[CardSharingResponse])
async def get_cards(db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    """List all cards WITHOUT sensitive data (card number, CVC hidden)."""
    return await list_cards(db, include_sensitive=False)


@router.post("", response_model=CardSharingResponse, status_code=201)
async def add_card(body: CardSharingCreate, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    return await create_card(db, body)


@router.get("/{card_id}/secure", response_model=CardSharingSensitiveResponse)
async def get_card_secure(card_id: str, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    """Get card WITH decrypted card number & CVC — CEO/Director only."""
    return await get_card(db, card_id, include_sensitive=True)


@router.patch("/{card_id}", response_model=CardSharingResponse)
async def update_card_endpoint(
    card_id: str, body: CardSharingUpdate, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)
):
    return await update_card(db, card_id, body)


@router.delete("/{card_id}", status_code=204)
async def delete_card_endpoint(card_id: str, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    await delete_card(db, card_id)