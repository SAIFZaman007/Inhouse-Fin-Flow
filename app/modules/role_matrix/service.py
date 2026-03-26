"""
app/modules/role_matrix/service.py
=====================================
Role Matrix business logic — pure functions, no FastAPI imports.

All DB writes use upsert/update — never blind inserts — to stay idempotent.
"""
import logging

from fastapi import HTTPException, status
from prisma import Prisma

from .constants import MODULE_LABELS, MODULE_SET, MODULES
from .schema import (
    ActionPermissionsResponse,
    PermissionRuleCreate,
    PermissionRuleResponse,
    PermissionRuleUpdate,
    TermsConditionCreate,
    TermsConditionUpdate,
    VisibilityMatrixResponse,
)

logger = logging.getLogger(__name__)

# Role → DB field name mapping (used for action-permissions lookup)
_ROLE_ACCESS_FIELD: dict[str, str] = {
    "CEO":      "ceoAccess",
    "DIRECTOR": "directorAccess",
    "HR":       "hrAccess",
    "BDEV":     "bdevAccess",
}


# ─── Seed ────────────────────────────────────────────────────────────────────

async def seed_permission_rules(db: Prisma) -> int:
    """
    Idempotent seed: ensures every canonical module has a PermissionRule row.
    Skips rows that already exist. Called from lifespan startup.
    Returns the number of rows created.
    """
    created = 0
    for idx, module_name in enumerate(MODULES):
        existing = await db.permissionrule.find_unique(where={"moduleName": module_name})
        if not existing:
            await db.permissionrule.create(
                data={
                    "moduleName":     module_name,
                    "displayOrder":   idx,
                    # Defaults are set at DB level by Prisma, but be explicit:
                    "ceoAccess":      "VISIBLE",
                    "directorAccess": "VISIBLE",
                    "hrAccess":       "HIDDEN",
                    "bdevAccess":     "HIDDEN",
                }
            )
            created += 1
            logger.info("Seeded PermissionRule for module: %s", module_name)

    if created:
        logger.info("Role matrix seed complete — %d new rule(s) created.", created)
    return created


# ─── Read ─────────────────────────────────────────────────────────────────────

async def get_visibility_matrix(db: Prisma) -> VisibilityMatrixResponse:
    """Return all permission rules ordered by displayOrder."""
    rules = await db.permissionrule.find_many(order={"displayOrder": "asc"})
    return VisibilityMatrixResponse(
        rules        = [PermissionRuleResponse.from_orm_rule(r) for r in rules],
        totalModules = len(rules),
    )


async def get_rule_by_id(db: Prisma, rule_id: str):
    rule = await db.permissionrule.find_unique(where={"id": rule_id})
    if not rule:
        raise HTTPException(status_code=404, detail="Permission rule not found.")
    return rule


async def get_action_permissions(db: Prisma, role: str) -> ActionPermissionsResponse:
    """
    Return the caller's personal module visibility map.
    Used by frontend nav shell — one call per session to determine what to render.
    """
    if role not in _ROLE_ACCESS_FIELD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role '{role}'.",
        )

    rules = await db.permissionrule.find_many(order={"displayOrder": "asc"})
    field = _ROLE_ACCESS_FIELD[role]

    visible, hidden = [], []
    for rule in rules:
        access_value = getattr(rule, field)
        if access_value == "VISIBLE":
            visible.append(rule.moduleName)
        else:
            hidden.append(rule.moduleName)

    return ActionPermissionsResponse(
        role           = role,
        visibleModules = visible,
        hiddenModules  = hidden,
        moduleLabels   = {m: MODULE_LABELS.get(m, m) for m in (visible + hidden)},
    )


# ─── Write ────────────────────────────────────────────────────────────────────

async def create_permission_rule(db: Prisma, data: PermissionRuleCreate) -> PermissionRuleResponse:
    """
    Create a new rule. Rejects duplicate moduleName (Prisma unique constraint
    also guards this, but we raise a clear 409 before hitting the DB).
    """
    existing = await db.permissionrule.find_unique(where={"moduleName": data.moduleName})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A permission rule for module '{data.moduleName}' already exists.",
        )

    rule = await db.permissionrule.create(
        data={
            "moduleName":     data.moduleName,
            "ceoAccess":      data.ceoAccess,
            "directorAccess": data.directorAccess,
            "hrAccess":       data.hrAccess,
            "bdevAccess":     data.bdevAccess,
            "displayOrder":   data.displayOrder,
        }
    )
    logger.info("PermissionRule created: %s", rule.moduleName)
    return PermissionRuleResponse.from_orm_rule(rule)


async def update_permission_rule(
    db: Prisma,
    rule_id: str,
    data: PermissionRuleUpdate,
) -> PermissionRuleResponse:
    """Partial update — only provided fields are written."""
    await get_rule_by_id(db, rule_id)   # raises 404 if missing

    patch = data.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    rule = await db.permissionrule.update(
        where={"id": rule_id},
        data=patch,
    )
    logger.info("PermissionRule updated: %s | patch=%s", rule.moduleName, patch)
    return PermissionRuleResponse.from_orm_rule(rule)


async def delete_permission_rule(db: Prisma, rule_id: str) -> None:
    """
    Hard delete. Raises 400 if the module is one of the canonical built-ins —
    those rows are managed by seed and should not be deleted via API.
    """
    rule = await get_rule_by_id(db, rule_id)
    if rule.moduleName in MODULE_SET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot delete a built-in module rule ('{rule.moduleName}'). "
                "Use PATCH to change visibility instead."
            ),
        )
    await db.permissionrule.delete(where={"id": rule_id})
    logger.info("PermissionRule deleted: %s", rule.moduleName)


# ─── Terms & Conditions ───────────────────────────────────────────────────────

async def get_terms(db: Prisma):
    """Return the single active Terms record (latest by version)."""
    return await db.termscondition.find_first(order={"version": "desc"})


async def create_terms(db: Prisma, data: TermsConditionCreate):
    """
    Create a new Terms version — auto-increments version number.
    Keeps old versions in DB for audit trail.
    """
    latest = await db.termscondition.find_first(order={"version": "desc"})
    next_version = (latest.version + 1) if latest else 1
    return await db.termscondition.create(
        data={"content": data.content, "version": next_version}
    )


async def update_terms(db: Prisma, terms_id: str, data: TermsConditionUpdate):
    terms = await db.termscondition.find_unique(where={"id": terms_id})
    if not terms:
        raise HTTPException(status_code=404, detail="Terms record not found.")
    return await db.termscondition.update(
        where={"id": terms_id},
        data={"content": data.content},
    )