"""
app/modules/role_matrix/schema.py
===================================
Pydantic schemas for the Role Matrix API.
"""
from typing import Optional
from pydantic import BaseModel, field_validator

from .constants import MODULE_LABELS, MODULE_SET


# ─── Shared sub-schema ────────────────────────────────────────────────────────

class RoleAccessBlock(BaseModel):
    """Per-role visibility flags returned in every rule response."""
    ceo:      str  # "VISIBLE" | "HIDDEN"
    director: str
    hr:       str
    bdev:     str


# ─── Permission Rule ──────────────────────────────────────────────────────────

class PermissionRuleResponse(BaseModel):
    id:           str
    moduleName:   str
    label:        str           # Human-readable display name
    access:       RoleAccessBlock
    displayOrder: int

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_rule(cls, rule) -> "PermissionRuleResponse":
        return cls(
            id           = rule.id,
            moduleName   = rule.moduleName,
            label        = MODULE_LABELS.get(rule.moduleName, rule.moduleName),
            access       = RoleAccessBlock(
                ceo      = rule.ceoAccess,
                director = rule.directorAccess,
                hr       = rule.hrAccess,
                bdev     = rule.bdevAccess,
            ),
            displayOrder = rule.displayOrder,
        )


class PermissionRuleCreate(BaseModel):
    moduleName:     str
    ceoAccess:      Optional[str] = "VISIBLE"
    directorAccess: Optional[str] = "VISIBLE"
    hrAccess:       Optional[str] = "HIDDEN"
    bdevAccess:     Optional[str] = "HIDDEN"
    displayOrder:   Optional[int] = 0

    @field_validator("moduleName")
    @classmethod
    def validate_module(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in MODULE_SET:
            raise ValueError(
                f"Unknown module '{v}'. "
                f"Valid modules: {sorted(MODULE_SET)}"
            )
        return v

    @field_validator("ceoAccess", "directorAccess", "hrAccess", "bdevAccess")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        if v not in {"VISIBLE", "HIDDEN"}:
            raise ValueError("Visibility must be 'VISIBLE' or 'HIDDEN'.")
        return v


class PermissionRuleUpdate(BaseModel):
    ceoAccess:      Optional[str] = None
    directorAccess: Optional[str] = None
    hrAccess:       Optional[str] = None
    bdevAccess:     Optional[str] = None
    displayOrder:   Optional[int] = None

    @field_validator("ceoAccess", "directorAccess", "hrAccess", "bdevAccess", mode="before")
    @classmethod
    def validate_visibility(cls, v) -> Optional[str]:
        if v is None:
            return v
        if v not in {"VISIBLE", "HIDDEN"}:
            raise ValueError("Visibility must be 'VISIBLE' or 'HIDDEN'.")
        return v


# ─── Visibility Matrix (GET /role-matrix/rules) ───────────────────────────────

class VisibilityMatrixResponse(BaseModel):
    """
    Full matrix: all modules × all roles.
    Returned as a flat ordered list — frontend can build any table/grid from it.
    """
    rules:       list[PermissionRuleResponse]
    totalModules: int


# ─── Action Permissions (GET /role-matrix/action-permissions) ─────────────────

class ActionPermissionsResponse(BaseModel):
    """
    Derived from PermissionRules — tells the frontend which modules the
    currently authenticated user may access.
    Used by the frontend shell to show/hide nav items without additional calls.
    """
    role:              str
    visibleModules:    list[str]   # moduleName strings
    hiddenModules:     list[str]
    moduleLabels:      dict[str, str]   # moduleName → human label


# ─── Terms & Conditions ───────────────────────────────────────────────────────

class TermsConditionResponse(BaseModel):
    id:        str
    content:   str
    version:   int
    updatedAt: str

    class Config:
        from_attributes = True


class TermsConditionCreate(BaseModel):
    content: str


class TermsConditionUpdate(BaseModel):
    content: str