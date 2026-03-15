"""
app/modules/pmak/router.py
════════════════════════════════════════════════════════════════════════════════
v4.3 — Enterprise Edition

Endpoint matrix
───────────────────────────────────────────────────────────────────────────────
GET    /accounts                        PMAK_EDITORS  Combined totals + all accounts
POST   /accounts                        CEO_DIRECTOR  Create account
DELETE /accounts/{id}                   CEO_DIRECTOR  Soft-delete (isActive → false)

POST   /transactions                    HR_AND_ABOVE  Add ledger transaction
GET    /accounts/{id}/transactions      PMAK_EDITORS  Paginated transactions per account
PATCH  /transactions/{id}/status        PMAK_EDITORS  Status-only update
DELETE /transactions/{id}               CEO_DIRECTOR  Hard delete

POST   /inhouse                         HR_AND_ABOVE  Add inhouse deal
GET    /inhouse                         PMAK_EDITORS  All deals, cross-account + totals
GET    /accounts/{id}/inhouse           PMAK_EDITORS  Paginated deals per account
PATCH  /inhouse/{id}                    PMAK_EDITORS  Update status / details
DELETE /inhouse/{id}                    CEO_DIRECTOR  Hard delete

GET    /export                          PMAK_EDITORS  All-accounts Excel (multi-sheet)
GET    /export/{account_id}             CEO_DIRECTOR  Single-account Excel
════════════════════════════════════════════════════════════════════════════════
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR, HR_AND_ABOVE, PMAK_EDITORS
from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_pmak

from .schema import (
    PmakAccountCreate,
    PmakInhouseCreate,
    PmakInhouseStatusUpdate,
    PmakTransactionCreate,
    PmakTransactionStatusUpdate,
)
from .service import (
    add_transaction,
    create_account,
    create_inhouse_deal,
    deactivate_account,
    delete_inhouse_deal,
    delete_transaction,
    export_account_excel,
    get_account_inhouse_deals,
    get_account_transactions,
    list_accounts,
    list_all_inhouse_deals,
    update_inhouse_deal,
    update_transaction_status,
)

router = APIRouter(prefix="/pmak", tags=["PMAK"])

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _xlsx(data: bytes, filename: str) -> Response:
    return Response(
        content=data,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Accounts
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/accounts",
    summary="All PMAK accounts — combined totals + per-account breakdown",
    description=(
        "Returns combined totals across all active accounts "
        "(`totalBalance`, `totalCredit`, `totalDebit`, `totalTransactions`, "
        "`totalInhouse`, `totalInhouseAmount`, `inhouseByStatus`, `activeAccountCount`) "
        "together with a paginated per-account breakdown. "
        "Each account includes its current balance, period credit/debit, "
        "transaction and inhouse counts, status breakdown, and the 5 most recent items. "
        "Use `?name=` for a case-insensitive partial search on account name. "
        "Supported periods: `daily` | `weekly` | `monthly` | `yearly` | `all`."
    ),
)
async def get_accounts(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial match on account name."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await list_accounts(db, filters, name=name, pagination=pagination)


@router.post(
    "/accounts",
    status_code=201,
    summary="Create a PMAK account",
    description=(
        "Creates a new PMAK ledger account. "
        "The response includes a zero-balance breakdown "
        "(`currentBalance`, `totalTransactions`, `totalInhouse`, `inhouseByStatus`) "
        "ready for data entry. "
        "**Required:** `accountName` — **Access:** CEO and Director only."
    ),
)
async def add_account(
    body: PmakAccountCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await create_account(db, body)


@router.delete(
    "/accounts/{account_id}",
    status_code=204,
    summary="Soft-delete a PMAK account",
    description=(
        "Sets `isActive = false` on the account. "
        "All transactions and inhouse deals are preserved. "
        "The account is excluded from all future list and totals queries. "
        "**Access:** CEO and Director only."
    ),
)
async def remove_account(
    account_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await deactivate_account(db, account_id)


# ─────────────────────────────────────────────────────────────────────────────
# Ledger Transactions
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/transactions",
    status_code=201,
    summary="Add a PMAK ledger transaction",
    description=(
        "Adds a double-entry ledger row to the specified PMAK account. "
        "`account_name` is resolved case-insensitively — staff never handle internal UUIDs. "
        "**Access:** HR and above. BDev may not create transactions."
    ),
)
async def add_transaction_entry(
    body: PmakTransactionCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await add_transaction(db, body)


@router.get(
    "/accounts/{account_id}/transactions",
    summary="Transactions for one PMAK account",
    description=(
        "Returns paginated ledger transactions for a single account, newest first. "
        "Each row includes `accountName` for client convenience. "
        "Response envelope also contains `currentBalance`, `periodCredit`, and `periodDebit`. "
        "Default page size: 50. Supports all standard period filters."
    ),
)
async def account_transactions(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await get_account_transactions(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.patch(
    "/transactions/{transaction_id}/status",
    summary="Update transaction status",
    description=(
        "Restricted PATCH — only the `status` field may be changed. "
        "This is the BDev entry-point; no financial fields are exposed. "
        "Valid values: `PENDING` | `CLEARED` | `ON_HOLD` | `REJECTED`. "
        "**Access:** All PMAK roles (BDev, HR, CEO, Director)."
    ),
)
async def patch_transaction_status(
    transaction_id: str,
    body: PmakTransactionStatusUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await update_transaction_status(db, transaction_id, body)


@router.delete(
    "/transactions/{transaction_id}",
    status_code=204,
    summary="Delete a PMAK transaction (hard delete)",
    description=(
        "Permanently removes the transaction. This action is irreversible. "
        "**Access:** CEO and Director only."
    ),
)
async def remove_transaction(
    transaction_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_transaction(db, transaction_id)


# ─────────────────────────────────────────────────────────────────────────────
# Inhouse Deals
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/inhouse",
    status_code=201,
    summary="Add a PMAK inhouse deal",
    description=(
        "Creates a new buyer/seller inhouse deal for the specified PMAK account. "
        "`account_name` is resolved case-insensitively — staff never need internal UUIDs. "
        "**Access:** HR and above. BDev may not create inhouse deals."
    ),
)
async def add_inhouse_deal(
    body: PmakInhouseCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_inhouse_deal(db, body)


@router.get(
    "/inhouse",
    summary="All PMAK inhouse deals — combined totals + cross-account deal list",
    description=(
        "Returns all inhouse deals across every active PMAK account "
        "in a single paginated response. "
        "The `totals` block covers `totalDeals`, `totalAmount`, and a `byStatus` "
        "breakdown (`PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` — "
        "each with `count` and `totalAmount`). "
        "Totals are always computed across **all** matching deals, not just the current page. "
        "Each deal row includes `accountName`, `date`, `details`, "
        "`buyerName`, `sellerName`, `orderAmount`, and `orderStatus`. "
        "**Filters:** `period`, `from`, `to`, `year`, `month`, "
        "`account_name`, `buyer_name`, `seller_name`, `order_status` — all combinable. "
        "**Access:** All PMAK roles (BDev, HR, CEO, Director)."
    ),
)
async def get_all_inhouse_deals(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    account_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive substring match on PMAK account name."),
    ] = None,
    buyer_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive substring match on buyer name."),
    ] = None,
    seller_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive substring match on seller name."),
    ] = None,
    order_status: Annotated[
        Optional[str],
        Query(
            description="Exact status filter: PENDING | IN_PROGRESS | COMPLETED | CANCELLED",
            pattern="^(PENDING|IN_PROGRESS|COMPLETED|CANCELLED)$",
        ),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await list_all_inhouse_deals(
        db,
        filters=filters,
        pagination=pagination,
        account_name=account_name,
        buyer_name=buyer_name,
        seller_name=seller_name,
        order_status=order_status,
    )


@router.get(
    "/accounts/{account_id}/inhouse",
    summary="Inhouse deals for one PMAK account",
    description=(
        "Returns paginated inhouse deals for a single account, newest first. "
        "Each row includes `accountName`. "
        "Response envelope includes a full `inhouseByStatus` breakdown "
        "and `totalAmount` for the selected period. "
        "Default page size: 50. Supports all standard period filters."
    ),
)
async def account_inhouse_deals(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await get_account_inhouse_deals(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.patch(
    "/inhouse/{deal_id}",
    summary="Update inhouse deal status or details",
    description=(
        "Partial update — only `order_status` and/or `details` may be changed. "
        "Valid statuses: `PENDING` | `IN_PROGRESS` | `COMPLETED` | `CANCELLED`. "
        "**Access:** All PMAK roles (BDev, HR, CEO, Director)."
    ),
)
async def patch_inhouse_deal(
    deal_id: str,
    body:    PmakInhouseStatusUpdate,
    db:      Prisma = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    return await update_inhouse_deal(db, deal_id, body)


@router.delete(
    "/inhouse/{deal_id}",
    status_code=204,
    summary="Delete a PMAK inhouse deal (hard delete)",
    description=(
        "Permanently removes the inhouse deal. This action is irreversible. "
        "**Access:** CEO and Director only."
    ),
)
async def remove_inhouse_deal(
    deal_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_inhouse_deal(db, deal_id)


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export all PMAK accounts to Excel",
    description=(
        "Downloads a multi-sheet Excel workbook covering all active PMAK accounts "
        "for the selected period. One sheet per account — each containing "
        "its ledger transactions and inhouse deals. "
        "Supports `period`, `from`, `to`, `year`, `month`, and `export_date` params. "
        "**Access:** All PMAK roles (BDev, HR, CEO, Director)."
    ),
)
async def export_all_accounts(
    params: ExportQueryParams = Depends(),
    db:     Prisma            = Depends(get_db),
    _=Depends(PMAK_EDITORS),
):
    data, filename = await export_pmak(db, params)
    return _xlsx(data, filename)


@router.get(
    "/export/{account_id}",
    summary="Export a single PMAK account to Excel",
    description=(
        "Downloads a two-sheet Excel workbook for one account: "
        "**Sheet 1** — Ledger Transactions (date, details, account from/to, debit, credit, balance, status). "
        "**Sheet 2** — Inhouse Deals (date, buyer, seller, amount, status, details). "
        "Supports all standard period filters. "
        "**Access:** CEO and Director only."
    ),
)
async def export_single_account(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    db:         Prisma          = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_account_excel(db, account_id, filters)
    return _xlsx(data, filename)