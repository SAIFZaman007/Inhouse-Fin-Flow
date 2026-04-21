"""
app/modules/pmak/router.py
════════════════════════════════════════════════════════════════════════════════
v7.0 — Enterprise Edition
════════════════════════════════════════════════════════════════════════════════
Changelog v7.0
  • POST   /pmak/tools                        — Add a Tools entry
  • GET    /pmak/tools                        — List all Tools entries (period-aware)
  • PATCH  /pmak/tools/{tool_id}              — Partial update (all fields)
  • DELETE /pmak/tools/{tool_id}              — Hard delete
  • GET    /pmak/accounts/{id}/tools          — Tools for one account (period-aware)
  • ?search= query param added to:
      GET /pmak/accounts/{id}/transactions    — keyword search on details
      GET /pmak/tools                         — keyword search on details
      GET /pmak/accounts/{id}/tools           — keyword search on details
  • GET /pmak/export/{account_id}            — now exports 3-sheet workbook
    (Ledger + Inhouse Deals + Tools)
  All pre-existing routes, names, and access rules are unchanged.
════════════════════════════════════════════════════════════════════════════════
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from prisma import Prisma

from app.core.database import get_db
from app.core.dependencies import ALL_ROLES, BDEV_AND_ABOVE, CEO_DIRECTOR, HR_AND_ABOVE
from app.shared.filters import DateRangeFilter
from app.shared.pagination import PageParams
from app.modules.export.schema import ExportQueryParams
from app.modules.export.service import export_pmak

from .schema import (
    PmakAccountCreate,
    PmakInhouseCreate,
    PmakInhouseFullUpdate,
    PmakToolCreate,
    PmakToolUpdate,
    PmakTransactionCreate,
    PmakTransactionStatusUpdate,
)
from .service import (
    # Accounts
    create_account,
    deactivate_account,
    update_account,
    list_accounts,
    # Transactions
    list_transactions,
    add_transaction,
    update_transaction,
    update_transaction_status,
    delete_transaction,
    get_account_transactions,
    # Inhouse
    add_inhouse,
    update_inhouse,
    delete_inhouse,
    get_all_inhouse,
    get_account_inhouse,
    # Tools (v7)
    add_tool,
    list_all_tools,
    get_account_tools,
    update_tool,
    delete_tool,
    # Export
    export_account_excel,
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
    description="""
Returns a **single response** containing:

- **Combined totals** across all active accounts for the selected period —
  `totalBalance`, `totalCredit`, `totalDebit`, `totalTransactions`,
  `totalInhouse`, `totalInhouseAmount`, `inhouseByStatus`, `activeAccountCount`.
- **Paginated per-account breakdown** (50 accounts per page by default),
  each including `currentBalance` *(dynamically computed as:
  latest_balance − period_debit + period_credit)*, `periodCredit`, `periodDebit`,
  transaction count, `totalInhouseOrderAmount` (all-time inhouse deal volume),
  inhouse deal summary, and the 5 most recent transactions/deals.
  Each account row now also includes `createdAt` and `updatedAt`.

Use `?name=` for a case-insensitive partial search on account name.

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** HR and above.
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
    _=Depends(HR_AND_ABOVE),
):
    return await list_accounts(db, filters, name=name, pagination=pagination)


@router.post(
    "/accounts",
    status_code=201,
    summary="Create a PMAK account",
    description="""
Creates a new PMAK ledger account.

**Required:** `accountName` (unique, 1–100 characters)

Response now includes `createdAt` and `updatedAt`.

**Access:** CEO, Director, and HR.
    """,
)
async def add_account(
    body: PmakAccountCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await create_account(db, body)


@router.patch(
    "/accounts/{account_id}",
    summary="Partially update a PMAK account",
    description="""
Performs a **partial update** on an existing PMAK account.

| Field | Effect |
|---|---|
| `accountName` | Renames the account; uniqueness enforced (409 on conflict). |
| `isActive` | `false` soft-deletes; `true` restores a deactivated account. |

Sending an empty body `{}` is accepted and returns the current state unchanged
(idempotent).

Response now includes `createdAt` and `updatedAt`.

**Access:** CEO, Director, HR, and BDev.
    """,
)
async def patch_account(
    account_id: str,
    body: PmakAccountCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await update_account(db, account_id, body)


@router.delete(
    "/accounts/{account_id}",
    status_code=200,
    summary="Soft-delete a PMAK account (sets isActive = false)",
    description="""
Soft-deletes a PMAK account by setting `isActive` to `false`.

The account and all its historical transactions/deals remain intact in the
database and can be restored via `PATCH /accounts/{id}`.

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
        "message": "PMAK account has been deactivated successfully.",
        "accountId": account_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Transactions
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/transactions",
    summary="All PMAK transactions (cross-account, period-aware, paginated)",
    description="""
Returns paginated ledger transactions across **all active accounts** for the
selected period.

Response includes aggregate totals:
- `totalTransactions` — total number of matching rows
- `totalDebit`        — sum of debit values in the matching set
- `totalCredit`       — sum of credit values in the matching set

Each row includes `accountName` for full client context.

**Search & Filter:**
- `?account_name=<n>` — case-insensitive substring match on account name
- `?search=<keyword>` — case-insensitive keyword search on the `details` field
- `?status=<s>`       — exact match: `PENDING` | `CLEARED` | `ON_HOLD` | `REJECTED`

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** HR and above.
    """,
)
async def get_all_transactions(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    account_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on account name."),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(description="Case-insensitive keyword search on the details field."),
    ] = None,
    status: Annotated[
        Optional[str],
        Query(description="Filter by status: PENDING | CLEARED | ON_HOLD | REJECTED."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await list_transactions(
        db, filters, pagination,
        account_name=account_name,
        search=search,
        status=status,
    )


@router.post(
    "/transactions",
    status_code=201,
    summary="Add a PMAK ledger transaction",
    description="""
Adds a ledger transaction for the specified PMAK account.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it to an internal record automatically.

`remainingBalance` is **auto-computed** server-side using the formula:
> `latest_balance − debit + credit`

You may still pass `remaining_balance` in the body to override this
(useful for manual balance corrections). `status` defaults to `PENDING`.

**Access:** All roles (CEO, Director, HR, and BDev).
    """,
)
async def add_transaction_entry(
    body: PmakTransactionCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await add_transaction(db, body)


@router.patch(
    "/transactions/{transaction_id}",
    summary="Partially update a PMAK transaction (all fields)",
    description="""
Performs a **partial update** on an existing PMAK transaction.

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
| `status` | Updates lifecycle status: `PENDING` \\| `CLEARED` \\| `ON_HOLD` \\| `REJECTED`. |

Sending an empty body `{}` returns the current transaction state unchanged
(idempotent).

**Access:** HR and above.
    """,
)
async def patch_transaction(
    transaction_id: str,
    body: PmakTransactionCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_transaction(db, transaction_id, body)


@router.patch(
    "/transactions/{transaction_id}/status",
    summary="Update PMAK transaction status only (BDev entry-point)",
    description="""
Restricted status-only update for a PMAK transaction.

| Status | Meaning |
|---|---|
| `PENDING` | Awaiting clearance (default). |
| `CLEARED` | Funds confirmed / settled. |
| `ON_HOLD` | Temporarily suspended. |
| `REJECTED` | Transaction rejected / reversed. |

Sending an empty body `{}` is accepted and returns the current status unchanged
(idempotent).

**Access:** BDev and above (all roles).
    """,
)
async def patch_transaction_status(
    transaction_id: str,
    body: PmakTransactionStatusUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(BDEV_AND_ABOVE),
):
    return await update_transaction_status(db, transaction_id, body)


@router.get(
    "/accounts/{account_id}/transactions",
    summary="Transactions for one PMAK account (period-aware, paginated)",
    description="""
Returns paginated transactions for a single PMAK account.

Each transaction row includes **`accountName`** so clients always have full
context without a secondary account lookup.

Response also contains `currentBalance` *(dynamically computed as:
latest_balance − period_debit + period_credit)*, `periodCredit`, and
`periodDebit` for the selected window.

Default: 50 transactions per page, newest first.

**Search:** Use `?search=<keyword>` to filter by a case-insensitive substring
of the `details` column (e.g. `?search=Adobe` returns all rows whose details
mention "Adobe").

**Access:** HR and above.
    """,
)
async def account_transactions(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    search: Annotated[
        Optional[str],
        Query(description="Case-insensitive keyword search on the details field."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_account_transactions(
        db, account_id, filters.to_prisma_filter(), pagination=pagination, search=search,
    )


@router.delete(
    "/transactions/{transaction_id}",
    status_code=200,
    summary="Delete a PMAK transaction (hard delete)",
    description="""
Permanently removes a PMAK transaction from the ledger.

> ⚠️ **This is a hard delete** — the record cannot be recovered.
> Update subsequent `remainingBalance` values manually if needed to maintain
> ledger integrity.

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
        "message": "PMAK transaction has been permanently deleted.",
        "transactionId": transaction_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Inhouse Deals
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/inhouse",
    status_code=201,
    summary="Add a PMAK inhouse deal",
    description="""
Logs a new inhouse deal against the specified PMAK account.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it to an internal record automatically.

`order_status` defaults to `PENDING`.

**Access:** All roles (CEO, Director, HR, and BDev).
    """,
)
async def add_inhouse_entry(
    body: PmakInhouseCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await add_inhouse(db, body)


@router.patch(
    "/inhouse/{deal_id}",
    summary="Partially update a PMAK inhouse deal (all fields)",
    description="""
Performs a **partial update** on an existing inhouse deal.

All fields are optional — only supplied fields are changed:

| Field | Effect |
|---|---|
| `account_name` | Reassigns the deal to a different active PMAK account. |
| `date` | Updates the deal date (YYYY-MM-DD). |
| `details` | Updates the free-text notes / reference code. |
| `buyer_name` | Updates the buyer name. |
| `seller_name` | Updates the seller / service-provider name. |
| `order_amount` | Updates the deal value in USD (must be > 0). |
| `order_status` | Updates lifecycle status: `PENDING` \\| `IN_PROGRESS` \\| `COMPLETED` \\| `CANCELLED`. |

Sending an empty body `{}` returns the current deal state unchanged (idempotent).

**Access:** All roles (CEO, Director, HR, and BDev).
    """,
)
async def patch_inhouse(
    deal_id: str,
    body: PmakInhouseFullUpdate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await update_inhouse(db, deal_id, body)


@router.get(
    "/inhouse",
    summary="All PMAK inhouse deals (period-aware, paginated)",
    description="""
Returns paginated inhouse deals across **all accounts** for the selected period.

Response includes aggregate totals (`totalDeals`, `totalAmount`, `byStatus`)
as well as the paginated deal list.

Each deal row includes `accountName` for full client context.

**Search & Filter:**
- `?account_name=<n>` — case-insensitive substring match on account name
- `?buyer_name=<n>`   — case-insensitive substring match on buyer name
- `?seller_name=<n>`  — case-insensitive substring match on seller name
- `?order_status=<s>` — exact match: `PENDING` | `IN_PROGRESS` | `COMPLETED` | `CANCELLED`
- `?search=<keyword>` — case-insensitive keyword search on the `details` field

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** HR and above.
    """,
)
async def get_inhouse(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    account_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on account name."),
    ] = None,
    buyer_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on buyer name."),
    ] = None,
    seller_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on seller name."),
    ] = None,
    order_status: Annotated[
        Optional[str],
        Query(description="Filter by deal status: PENDING | IN_PROGRESS | COMPLETED | CANCELLED."),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(description="Case-insensitive keyword search on the details field."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_all_inhouse(
        db, filters, pagination=pagination,
        account_name=account_name,
        buyer_name=buyer_name,
        seller_name=seller_name,
        order_status=order_status,
        search=search,
    )


@router.get(
    "/accounts/{account_id}/inhouse",
    summary="Inhouse deals for one PMAK account (period-aware, paginated)",
    description="""
Returns paginated inhouse deals for a single PMAK account.

Response includes deal counts grouped by `orderStatus`
(`PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`) and a `totalAmount`
for the selected window.

Default: 50 deals per page, newest first.

**Access:** HR and above.
    """,
)
async def account_inhouse(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_account_inhouse(
        db, account_id, filters.to_prisma_filter(), pagination=pagination
    )


@router.delete(
    "/inhouse/{deal_id}",
    status_code=200,
    summary="Delete a PMAK inhouse deal (hard delete)",
    description="""
Permanently removes a PMAK inhouse deal from the ledger.

> ⚠️ **This is a hard delete** — the record cannot be recovered.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_inhouse(
    deal_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_inhouse(db, deal_id)
    return {
        "success": True,
        "message": "PMAK inhouse deal has been permanently deleted.",
        "dealId": deal_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tools  (v7 — new entity)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/tools",
    status_code=201,
    summary="Add a PMAK Tools entry",
    description="""
Adds a Tools ledger entry for the specified PMAK account.

**`account_name`** — the human-readable account name (case-insensitive).
The system resolves it to an internal record automatically.

The **`total`** field is **auto-computed** server-side using:
> `latest_total − debit + credit`

You may still pass `total` explicitly (non-zero) to override the auto-compute
(useful for manual balance corrections).

All other fields (`date`, `details`, `debit`, `credit`) are **optional** —
`date` defaults to today when omitted; `debit` and `credit` default to 0.

**Access:** All roles (CEO, Director, HR, and BDev).
    """,
)
async def add_tool_entry(
    body: PmakToolCreate,
    db:   Prisma = Depends(get_db),
    _=Depends(ALL_ROLES),
):
    return await add_tool(db, body)


@router.get(
    "/tools",
    summary="All PMAK Tools entries (period-aware, paginated)",
    description="""
Returns paginated Tools entries across **all accounts** for the selected period.

Response includes aggregate totals:
- `totalEntries` — total number of matching rows
- `totalDebit`   — sum of all debit values in the result set
- `totalCredit`  — sum of all credit values in the result set
- `latestTotal`  — highest `total` (running balance) in the result set

Each row includes `accountName` for full client context.

**Search:**
- `?account_name=<name>` — case-insensitive substring match on account name
- `?search=<keyword>` — case-insensitive keyword search on the `details` field
  (e.g. `?search=Adobe` returns all entries whose details mention "Adobe")

Period params: `daily` | `weekly` | `monthly` | `yearly` | `all` (default).

**Access:** HR and above.
    """,
)
async def get_tools(
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    account_name: Annotated[
        Optional[str],
        Query(description="Case-insensitive partial search on account name."),
    ] = None,
    search: Annotated[
        Optional[str],
        Query(description="Case-insensitive keyword search on the details field."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await list_all_tools(
        db, filters, pagination, account_name=account_name, search=search
    )


@router.patch(
    "/tools/{tool_id}",
    summary="Partially update a PMAK tool entry (all fields)",
    description="""
Performs a **partial update** on an existing Tools entry.

All fields are optional — only supplied fields are changed:

| Field | Effect |
|---|---|
| `account_name` | Reassigns the entry to a different active PMAK account. |
| `date` | Updates the entry date (YYYY-MM-DD). |
| `details` | Updates the free-text description. |
| `debit` | Updates the debit amount (triggers `total` auto-recompute). |
| `credit` | Updates the credit amount (triggers `total` auto-recompute). |
| `total` | Manual override of the running total (non-zero value only). |

When `debit` or `credit` changes and no explicit `total` override is supplied,
the server **auto-recomputes** `total` by reversing the stored formula:
> `total = (old_total + old_debit − old_credit) − new_debit + new_credit`

Sending an empty body `{}` returns the current entry unchanged (idempotent).

**Access:** HR and above.
    """,
)
async def patch_tool(
    tool_id: str,
    body:    PmakToolUpdate,
    db:      Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await update_tool(db, tool_id, body)


@router.delete(
    "/tools/{tool_id}",
    status_code=200,
    summary="Delete a PMAK tool entry (hard delete)",
    description="""
Permanently removes a PMAK Tools entry.

> ⚠️ **This is a hard delete** — the record cannot be recovered.
> Update subsequent `total` values manually if needed to maintain ledger integrity.

Returns a JSON confirmation message on success.

**Access:** CEO and Director only.
    """,
)
async def remove_tool(
    tool_id: str,
    db: Prisma = Depends(get_db),
    _=Depends(CEO_DIRECTOR),
):
    await delete_tool(db, tool_id)
    return {
        "success": True,
        "message": "PMAK tool entry has been permanently deleted.",
        "toolId": tool_id,
    }


@router.get(
    "/accounts/{account_id}/tools",
    summary="Tools entries for one PMAK account (period-aware, paginated)",
    description="""
Returns paginated Tools entries for a single PMAK account.

Response includes:
- `totalDebit`  — sum of debit values for the selected window
- `totalCredit` — sum of credit values for the selected window
- `latestTotal` — most recent running total for this account

**Search:** Use `?search=<keyword>` to filter by a case-insensitive substring
of the `details` column.

Default: 50 entries per page, newest first.

**Access:** HR and above.
    """,
)
async def account_tools(
    account_id: str,
    filters:    DateRangeFilter = Depends(),
    pagination: PageParams      = Depends(),
    search: Annotated[
        Optional[str],
        Query(description="Case-insensitive keyword search on the details field."),
    ] = None,
    db: Prisma = Depends(get_db),
    _=Depends(HR_AND_ABOVE),
):
    return await get_account_tools(
        db, account_id, filters.to_prisma_filter(), pagination=pagination, search=search,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export all PMAK accounts to Excel (period-aware, multi-sheet)",
    description="""
Downloads a multi-sheet Excel workbook covering **all active PMAK accounts**
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
    data, filename = await export_pmak(db, params)
    return _xlsx(data, filename)


@router.get(
    "/export/{account_id}",
    summary="Export a single PMAK account to Excel (period-aware)",
    description="""
Downloads a **three-sheet** Excel workbook for **one account**:
- **Sheet 1** — Ledger Transactions (date, details, from, to, debit, credit, balance, status)
- **Sheet 2** — Inhouse Deals (date, buyer, seller, amount, status, details)
- **Sheet 3** — Tools (date, details, debit, credit, total)

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