"""
app/modules/users/router.py
=============================
User management — CEO-only CRUD + invitation-based onboarding sub-router.

Standard CRUD (direct creation via temp password — kept for backward compat):
  GET    /api/v1/users              → List all users
  GET    /api/v1/users/{id}         → Get single user
  PATCH  /api/v1/users/{id}         → Update user name/role/status
  POST   /api/v1/users/{id}/reset-password → Reset password + send email
  DELETE /api/v1/users/{id}         → Delete user

Invitation sub-router (preferred onboarding path):
  POST   /api/v1/users/invitations              → Invite member via email
  GET    /api/v1/users/invitations              → List invitations
  POST   /api/v1/users/invitations/{id}/resend → Resend invitation email
  DELETE /api/v1/users/invitations/{id}         → Cancel invitation
  GET    /api/v1/users/invitations/accept-form  → HTML page (PUBLIC)
  POST   /api/v1/users/invitations/accept       → Create account (PUBLIC)
"""
from fastapi import APIRouter, Depends
from prisma import Prisma
from prisma.models import User

from app.core.database import get_db
from app.core.dependencies import CEO_ONLY

from app.modules.invitations.router import router as invitation_router
from .schema import UserResponse, UserUpdate
from .service import delete_user, get_user, list_users, reset_user_password, update_user

router = APIRouter(prefix="/users", tags=["Users"])

# ── Mount invitations as a nested sub-router ──────────────────────────────────
router.include_router(invitation_router)


# ── User CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[UserResponse], summary="List all users (CEO only)")
async def list_users_endpoint(
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    return await list_users(db)


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID (CEO only)")
async def get_user_endpoint(
    user_id: str,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    return await get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserResponse, summary="Update user (CEO only)")
async def update_user_endpoint(
    user_id: str,
    body: UserUpdate,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    return await update_user(db, user_id, body)


@router.post(
    "/{user_id}/reset-password",
    summary="Reset user password and email it (CEO only)",
)
async def reset_password_endpoint(
    user_id: str,
    db: Prisma = Depends(get_db),
    _: User    = Depends(CEO_ONLY),
):
    return await reset_user_password(db, user_id)


@router.delete("/{user_id}", status_code=204, summary="Delete user (CEO only)")
async def delete_user_endpoint(
    user_id:      str,
    db:           Prisma = Depends(get_db),
    current_user: User   = Depends(CEO_ONLY),
):
    await delete_user(db, user_id, current_user.id)