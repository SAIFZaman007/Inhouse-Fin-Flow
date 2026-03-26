"""
app/modules/role_matrix/router.py
===================================
Role Matrix — access control configuration for FinFlow modules.

All mutating endpoints (POST, PATCH, DELETE) are CEO-only.
Read endpoints (GET) are accessible to CEO and DIRECTOR.

Endpoints
─────────
GET    /api/v1/role-matrix/rules                → Full visibility matrix
POST   /api/v1/role-matrix/rules                → Create a permission rule   [CEO]
PATCH  /api/v1/role-matrix/rules/{rule_id}      → Update a permission rule   [CEO]
DELETE /api/v1/role-matrix/rules/{rule_id}      → Delete a custom rule       [CEO]
GET    /api/v1/role-matrix/action-permissions   → Caller's visible modules
GET    /api/v1/role-matrix/terms                → Get latest Terms & Conditions (PUBLIC)
POST   /api/v1/role-matrix/terms                → Create new Terms version   [CEO]
PATCH  /api/v1/role-matrix/terms/{terms_id}     → Update a Terms version     [CEO]
"""
from fastapi import APIRouter, Depends
from prisma import Prisma
from prisma.models import User

from app.core.database import get_db
from app.core.dependencies import CEO_ONLY, CEO_DIRECTOR, get_current_user

from .schema import (
    ActionPermissionsResponse,
    PermissionRuleCreate,
    PermissionRuleResponse,
    PermissionRuleUpdate,
    TermsConditionCreate,
    TermsConditionResponse,
    TermsConditionUpdate,
    VisibilityMatrixResponse,
)
from .service import (
    create_permission_rule,
    create_terms,
    delete_permission_rule,
    get_action_permissions,
    get_terms,
    get_visibility_matrix,
    update_permission_rule,
    update_terms,
)

router = APIRouter(prefix="/role-matrix", tags=["Role Matrix"])


# ══════════════════════════════════════════════════════════════════════════════
# PERMISSION RULES
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/rules",
    response_model=VisibilityMatrixResponse,
    summary="Get Visibility Matrix",
    description=(
        "Returns the full module × role visibility matrix ordered by `displayOrder`.\n\n"
        "- **CEO / DIRECTOR**: full read access\n"
        "- Use `GET /action-permissions` if you only need the caller's own view."
    ),
)
async def get_rules(
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_DIRECTOR),
):
    return await get_visibility_matrix(db)


@router.post(
    "/rules",
    response_model=PermissionRuleResponse,
    status_code=201,
    summary="Create Permission Rule",
    description=(
        "Add a permission rule for a module not yet tracked by the matrix.\n\n"
        "**CEO only.** Built-in modules are auto-seeded at startup — "
        "this endpoint is for any custom/future modules."
    ),
)
async def create_rule(
    body: PermissionRuleCreate,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    return await create_permission_rule(db, body)


@router.patch(
    "/rules/{rule_id}",
    response_model=PermissionRuleResponse,
    summary="Update Permission Rule",
    description=(
        "Partial update — send only the fields you want to change.\n\n"
        "**CEO only.** Example: set `hrAccess: 'VISIBLE'` to grant HR access "
        "to a previously hidden module."
    ),
)
async def update_rule(
    rule_id: str,
    body: PermissionRuleUpdate,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    return await update_permission_rule(db, rule_id, body)


@router.delete(
    "/rules/{rule_id}",
    status_code=204,
    summary="Delete Permission Rule",
    description=(
        "Hard-delete a **custom** permission rule.\n\n"
        "**CEO only.** Built-in module rules (dashboard, fiverr, upwork, …) "
        "cannot be deleted — use PATCH to hide them instead. "
        "Returns `400` if you attempt to delete a built-in rule."
    ),
)
async def delete_rule(
    rule_id: str,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    await delete_permission_rule(db, rule_id)


# ══════════════════════════════════════════════════════════════════════════════
# ACTION PERMISSIONS  (per-user derived view)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/action-permissions",
    response_model=ActionPermissionsResponse,
    summary="Get Action Permissions",
    description=(
        "Returns the **caller's** personalised module visibility map — "
        "derived from the PermissionRule matrix and the caller's role.\n\n"
        "Intended for the frontend shell on session start: one call resolves "
        "which nav items to show or hide without any client-side role logic.\n\n"
        "All authenticated roles may call this endpoint."
    ),
)
async def get_my_permissions(
    db:           Prisma = Depends(get_db),
    current_user: User   = Depends(get_current_user),
):
    return await get_action_permissions(db, current_user.role)


# ══════════════════════════════════════════════════════════════════════════════
# TERMS & CONDITIONS
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/terms",
    summary="Get Terms & Conditions",
    description=(
        "Returns the latest Terms & Conditions version.\n\n"
        "**Public endpoint** — no authentication required. "
        "Returns `null` if no terms have been created yet."
    ),
)
async def get_terms_endpoint(db: Prisma = Depends(get_db)):
    terms = await get_terms(db)
    if not terms:
        return {"terms": None}
    return {
        "id":        terms.id,
        "content":   terms.content,
        "version":   terms.version,
        "updatedAt": terms.updatedAt.isoformat(),
    }


@router.post(
    "/terms",
    status_code=201,
    summary="Create Terms & Conditions",
    description=(
        "Create a new Terms & Conditions version (auto-increments version number).\n\n"
        "**CEO only.** Previous versions are retained for audit purposes."
    ),
)
async def create_terms_endpoint(
    body: TermsConditionCreate,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    terms = await create_terms(db, body)
    return {
        "id":        terms.id,
        "content":   terms.content,
        "version":   terms.version,
        "updatedAt": terms.updatedAt.isoformat(),
    }


@router.patch(
    "/terms/{terms_id}",
    summary="Update Terms & Conditions",
    description=(
        "Update the content of an existing Terms version.\n\n"
        "**CEO only.** The version number is not changed — "
        "create a new record via POST if you want a version bump."
    ),
)
async def update_terms_endpoint(
    terms_id: str,
    body: TermsConditionUpdate,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    terms = await update_terms(db, terms_id, body)
    return {
        "id":        terms.id,
        "content":   terms.content,
        "version":   terms.version,
        "updatedAt": terms.updatedAt.isoformat(),
    }