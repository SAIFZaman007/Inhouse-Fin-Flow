"""
app/modules/payoneer/router.py
════════════════════════════════════════════════════════════════════════════════
v5 — Enterprise Edition

Endpoint matrix
───────────────────────────────────────────────────────────────────────────────
GET    /accounts                        CEO_DIRECTOR  Combined totals + all accounts
                                                      Period + ?name= filter. Paginated.
POST   /accounts                        CEO_DIRECTOR  Create + optional opening balance
GET    /accounts/{account_id}           CEO_DIRECTOR  Single-account detail — full filter
                                                      system (period-aware, paginated)
PATCH  /accounts/{account_id}           CEO_DIRECTOR  Partial update (rename / isActive /
                                                      balance-adjustment — all optional)
DELETE /accounts/{account_id}           CEO_DIRECTOR  Soft-delete — returns JSON message

POST   /transactions                    CEO_DIRECTOR  Add transaction (by accountName)
PATCH  /transactions/{id}               CEO_DIRECTOR  Partial update (any field)
DELETE /transactions/{id}               CEO_DIRECTOR  Hard delete — returns JSON message
GET    /accounts/{id}/transactions      CEO_DIRECTOR  Paginated transactions + accountName

GET    /export                          CEO_DIRECTOR  All-accounts Excel (period-aware)
GET    /export/{account_id}             CEO_DIRECTOR  Single-account Excel (period-aware)
════════════════════════════════════════════════════════════════════════════════
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import CEO_DIRECTOR
from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_payoneer

from .schema import (
    PayoneerAccountCreate,
    PayoneerAccountUpdate,
    PayoneerTransactionCreate,
    PayoneerTransactionUpdate,
)
from .service import (
    add_transaction,
    create_account,
    deactivate_account,
    delete_transaction,
    export_account_excel,
    get_account_detail,
    get_account_transactions,
    list_accounts,
    update_account,
    update_transaction,
)

router = APIRouter(prefix="/payoneer", tags=["Payoneer"])

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
    summary="All Payoneer accounts — combined totals + per-account breakdown",
    description="""
Returns a **single response** containing:

- **Combined totals** across all active accounts:
  `totalBalance` (Σ latest balance per account), `totalCredit`, `totalDebit`,
  `totalTransactions`, `activeAccountCount`.
- **Paginated per-account breakdown** (50 accounts per page by default),
  each including `currentBalance`, period `credit`/`debit`, transaction count,
  and the 5 most recent transactions in the selected window.

Use `?name=` for a case-insensitive partial search on account name.

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** CEO and Director only.
    """,
)
async def get_accounts(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on account name."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await list_accounts(db, filters, name=name, pagination=pagination)


@router.post(
    "/accounts",
    status_code=201,
    summary="Create a Payoneer account (optionally seed with an opening balance)",
    description="""
Creates a new Payoneer account.

If `initial_balance` is provided, an opening **credit** transaction is recorded
immediately — no separate POST /transactions call is needed.

**Required:** `accountName`
**Optional:** `description`, `initial_balance`, `opening_note`

**Access:** CEO and Director only.
    """,
)
async def add_account(
    body: PayoneerAccountCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await create_account(db, body)


@router.get(
    "/accounts/{account_id}",
    summary="Single Payoneer account — full detail with period-aware filter",
    description="""
Returns a complete breakdown for **one Payoneer account**:

- Account metadata (`id`, `accountName`, `isActive`)
- `currentBalance` — the latest `remainingBalance` across all time
- Period-scoped `periodCredit` and `periodDebit` for the selected window
- **Paginated transactions** in the selected period (newest first, 50 per page)

Each transaction row includes `accountName` for full client context.

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** CEO and Director only.
    """,
)
async def get_account(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await get_account_detail(db, account_id, filters, pagination=pagination)


@router.patch(
    "/accounts/{account_id}",
    summary="Partially update a Payoneer account (metadata + optional balance adjustment)",
    description="""
Performs a **partial update** on an existing Payoneer account.

All fields are optional — only supplied fields are changed.

### Account metadata

| Field | Effect |
|---|---|
| `accountName` | Renames the account; uniqueness enforced (409 on conflict). |
| `isActive` | `false` soft-deletes the account; `true` restores a deactivated one. |

### Balance-adjustment fields *(v4 addition)*

When `initial_balance` is supplied the service **appends a credit transaction**
to the account's ledger immediately, so the balance can be corrected or topped-up
without a separate POST /transactions call.

| Field | Description |
|---|---|
| `description` | Free-text note; used as the transaction `details` text when `initial_balance` is set. |
| `initial_balance` | Amount of the credit adjustment (must be > 0). The new `remainingBalance` is computed as *current latest balance + initial_balance*. |
| `opening_note` | Fallback details text if `description` is not provided. Defaults to `"Balance adjustment"`. |

> **Ledger integrity:** `remainingBalance` is auto-computed from the latest
> transaction — you do not need to supply it manually.

Sending an empty body `{}` is accepted and returns the current account state
unchanged (idempotent).

**Access:** CEO and Director only.
    """,
)
async def patch_account(
    account_id: str,
    body: PayoneerAccountUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await update_account(db, account_id, body)


@router.delete(
    "/accounts/{account_id}",
    status_code=200,
    summary="Soft-delete a Payoneer account (sets isActive = false)",
    description="""
Soft-deletes a Payoneer account by setting `isActive` to `false`.

The account and all its historical transactions remain intact in the database
and can be restored via `PATCH /accounts/{id}` with `isActive: true`.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_account(
    account_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await deactivate_account(db, account_id)
    return {
        "success": True,
        "message": "Payoneer account has been deactivated successfully.",
        "accountId": account_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Transactions
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/transactions",
    status_code=201,
    summary="Add a Payoneer transaction",
    description="""
Adds a ledger transaction for the specified account.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it to an internal record automatically.
Finance staff never need to handle internal account UUIDs.

`remainingBalance` must be supplied by the caller (it reflects the account
balance *after* this transaction, as entered in the Payoneer interface).

**Access:** CEO and Director only.
    """,
)
async def add_transaction_entry(
    body: PayoneerTransactionCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await add_transaction(db, body)


@router.patch(
    "/transactions/{transaction_id}",
    summary="Partially update a Payoneer transaction",
    description="""
Performs a **partial update** on an existing Payoneer transaction.

All fields are optional — only supplied fields are changed:

| Field | Effect |
|---|---|
| `date` | Changes the transaction date. |
| `details` | Updates the description / reference text. |
| `accountFrom` | Updates the source label (send `null` to clear). |
| `accountTo` | Updates the destination label (send `null` to clear). |
| `debit` | Updates the debit amount. |
| `credit` | Updates the credit amount. |
| `remaining_balance` | Corrects the post-transaction balance (not auto-recomputed). |

`remainingBalance` is **never auto-recomputed** — if you update `debit` or
`credit`, supply the corrected `remaining_balance` in the same request to keep
the ledger consistent.

Sending an empty body `{}` returns the current transaction state unchanged
(idempotent).

**Access:** CEO and Director only.
    """,
)
async def patch_transaction(
    transaction_id: str,
    body: PayoneerTransactionUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await update_transaction(db, transaction_id, body)


@router.get(
    "/accounts/{account_id}/transactions",
    summary="Transactions for one Payoneer account (period-aware, paginated)",
    description="""
Returns paginated transactions for a single account.

Each transaction row includes **`accountName`** so clients always have full
context without a secondary account lookup.

Response also contains `currentBalance` (latest balance across all time),
`periodCredit`, and `periodDebit` for the selected window.

Default: 50 transactions per page, newest first.

**Access:** CEO and Director only.
    """,
)
async def account_transactions(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    return await get_account_transactions(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.delete(
    "/transactions/{transaction_id}",
    status_code=200,
    summary="Delete a Payoneer transaction (hard delete)",
    description="""
Permanently removes a Payoneer transaction from the ledger.

> ⚠️ **This is a hard delete** — the record cannot be recovered.
> If `remainingBalance` values in subsequent transactions depend on this
> entry, update them manually after deletion to maintain ledger integrity.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_transaction(
    transaction_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_transaction(db, transaction_id)
    return {
        "success": True,
        "message": "Payoneer transaction has been permanently deleted.",
        "transactionId": transaction_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export all Payoneer accounts to Excel (period-aware, multi-sheet)",
    description="""
Downloads a multi-sheet Excel workbook covering **all active Payoneer accounts**
for the selected period.

Supports `period` / `from` / `to` / `year` / `month` / `export_date` params.

**Access:** CEO and Director only.
    """,
)
async def export_all_accounts(
    params: ExportQueryParams = Depends(),
    db:     Prisma            = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_payoneer(db, params)
    return _xlsx(data, filename)


@router.get(
    "/export/{account_id}",
    summary="Export a single Payoneer account to Excel (period-aware)",
    description="""
Downloads a single-sheet Excel workbook for **one account** containing all
transactions for the selected period.

**Access:** CEO and Director only.
    """,
)
async def export_single_account(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    db:         Prisma          = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    data, filename = await export_account_excel(db, account_id, filters)
    return _xlsx(data, filename)