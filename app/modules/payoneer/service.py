"""
app/modules/payoneer/service.py
"""
from fastapi import HTTPException
from prisma import Prisma

from .schema import PayoneerAccountCreate, PayoneerTransactionCreate


async def create_account(db: Prisma, data: PayoneerAccountCreate):
    existing = await db.payoneeraccount.find_unique(where={"accountName": data.accountName})
    if existing:
        raise HTTPException(status_code=409, detail="Account name already exists")
    return await db.payoneeraccount.create(data={"accountName": data.accountName})


async def list_accounts(db: Prisma):
    accounts = await db.payoneeraccount.find_many(
        where={"isActive": True},
        include={"transactions": {"take": 5}},
        order={"accountName": "asc"},
    )
    # Sort each account's transactions descending by date so the latest comes first
    for acc in accounts:
        if acc.transactions:
            acc.transactions.sort(key=lambda t: t.date, reverse=True)
    return accounts


async def add_transaction(db: Prisma, data: PayoneerTransactionCreate):
    account = await db.payoneeraccount.find_unique(where={"id": data.account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Payoneer account not found")

    return await db.payoneertransaction.create(
        data={
            "accountId":        data.account_id,
            "date":             data.date,
            "details":          data.details,
            "accountFrom":      data.accountFrom,  
            "accountTo":        data.accountTo,   
            "debit":            data.debit,
            "credit":           data.credit,
            "remainingBalance": data.remaining_balance,
        }
    )


async def get_account_transactions(db: Prisma, account_id: str, date_filter: dict):
    account = await db.payoneeraccount.find_unique(where={"id": account_id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    where: dict = {"accountId": account_id}
    if date_filter:
        where["date"] = date_filter
    return await db.payoneertransaction.find_many(where=where, order={"date": "asc"})


async def delete_transaction(db: Prisma, transaction_id: str):
    tx = await db.payoneertransaction.find_unique(where={"id": transaction_id})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await db.payoneertransaction.delete(where={"id": transaction_id})