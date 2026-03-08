from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, CEO_DIRECTOR
from app.shared.filters import DateRangeFilter

from .schema import (
    PmakAccountCreate, PmakAccountResponse,
    PmakTransactionCreate, PmakTransactionResponse,
)
from .service import (
    add_transaction, create_account, delete_transaction,
    get_account_transactions, list_accounts,
)

router = APIRouter(prefix="/pmak", tags=["PMAK"])


@router.get("/accounts", response_model=list[PmakAccountResponse])
async def get_accounts(db: Prisma = Depends(get_db), _=Depends(ALL_ROLES)):
    return await list_accounts(db)


@router.post("/accounts", response_model=PmakAccountResponse, status_code=201)
async def add_account(body: PmakAccountCreate, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    return await create_account(db, body)


@router.post("/transactions", response_model=PmakTransactionResponse, status_code=201)
async def add_transaction_entry(
    body: PmakTransactionCreate, db: Prisma = Depends(get_db), _=Depends(ALL_ROLES)
):
    return await add_transaction(db, body)


@router.get("/accounts/{account_id}/transactions", response_model=list[PmakTransactionResponse])
async def account_transactions(
    account_id: str,
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await get_account_transactions(db, account_id, filters.to_prisma_filter())


@router.delete("/transactions/{transaction_id}", status_code=204)
async def remove_transaction(
    transaction_id: str, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)
):
    await delete_transaction(db, transaction_id)