from fastapi import APIRouter, Depends
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, CEO_DIRECTOR
from app.shared.filters import DateRangeFilter

from .schema import (
    PayoneerAccountCreate, PayoneerAccountResponse,
    PayoneerTransactionCreate, PayoneerTransactionResponse,
)
from .service import (
    add_transaction, create_account, delete_transaction,
    get_account_transactions, list_accounts,
)

router = APIRouter(prefix="/payoneer", tags=["Payoneer"])


@router.get("/accounts", response_model=list[PayoneerAccountResponse])
async def get_accounts(db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    return await list_accounts(db)


@router.post("/accounts", response_model=PayoneerAccountResponse, status_code=201)
async def add_account(body: PayoneerAccountCreate, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)):
    return await create_account(db, body)


@router.post("/transactions", response_model=PayoneerTransactionResponse, status_code=201)
async def add_transaction_entry(
    body: PayoneerTransactionCreate, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)
):
    return await add_transaction(db, body)


@router.get("/accounts/{account_id}/transactions", response_model=list[PayoneerTransactionResponse])
async def account_transactions(
    account_id: str,
    filters: DateRangeFilter = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await get_account_transactions(db, account_id, filters.to_prisma_filter())


@router.delete("/transactions/{transaction_id}", status_code=204)
async def remove_transaction(
    transaction_id: str, db: Prisma = Depends(get_db), _=Depends(CEO_DIRECTOR)
):
    await delete_transaction(db, transaction_id)