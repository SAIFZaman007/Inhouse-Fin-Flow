"""
app/modules/invitations/service.py
====================================
Enterprise invitation system — token-based user onboarding.

Flow:
  1. CEO → POST /invite      → creates Invitation record + sends email
  2. Invitee clicks link     → loads accept-form (GET, HTML page)
  3. Invitee submits form    → POST /accept → creates User, marks invitation ACCEPTED
  4. CEO → POST /{id}/resend → re-sends email with same token (no new record)
  5. CEO → DELETE /{id}      → marks invitation CANCELLED (no hard delete)

Security:
  - Tokens: 32-byte URL-safe random (256-bit entropy)
  - Expiry: 7 days (configurable via INVITE_EXPIRE_DAYS in .env)
  - Single-use: token rejected after first acceptance
  - No temp password ever touches email — user sets their own
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from math import ceil

from fastapi import HTTPException, status
from prisma import Prisma

from app.core.config import get_settings
from app.core.email import send_invitation_email
from app.core.security import hash_password

from .schema import AcceptInvitation, InviteCreate

logger = logging.getLogger(__name__)
settings = get_settings()

INVITE_EXPIRE_DAYS = 7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _role_label(role: str) -> str:
    return {"CEO": "CEO", "DIRECTOR": "Director", "HR": "HR Manager"}.get(role, role.title())


# ── Invite ────────────────────────────────────────────────────────────────────

async def create_invitation(
    db: Prisma,
    data: InviteCreate,
    invited_by_id: str,
    base_url: str,
) -> dict:
    """
    Create a secure invitation and dispatch the email.
    Raises 409 if the email already has an active user or pending invitation.
    """
    # 1. Check existing user
    existing_user = await db.user.find_unique(where={"email": data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{data.email}' already exists.",
        )

    # 2. Check duplicate pending invitation
    duplicate = await db.invitation.find_first(
        where={"email": data.email, "status": "PENDING"}
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A pending invitation already exists for '{data.email}'. "
                f"Resend it or cancel it first."
            ),
        )

    # 3. Generate token and create record
    token = secrets.token_urlsafe(32)
    inviter = await db.user.find_unique(where={"id": invited_by_id})
    inviter_name = inviter.name if inviter else "Administrator"

    invitation = await db.invitation.create(
        data={
            "email":       data.email,
            "role":        data.role,
            "inviteToken": token,
            "invitedBy":   invited_by_id,
            "status":      "PENDING",
            "expiresAt":   _utc_now() + timedelta(days=INVITE_EXPIRE_DAYS),
        }
    )

    # 4. Send email — non-blocking failure (invitation still created)
    sent = await send_invitation_email(
        to=data.email,
        inviter_name=inviter_name,
        role_label=_role_label(data.role),
        invite_token=token,
        base_url=base_url,
        app_name=settings.APP_NAME,
        expire_days=INVITE_EXPIRE_DAYS,
    )
    if not sent:
        logger.warning(
            "Invitation created for %s but email delivery failed — "
            "check SMTP settings. Token can be resent.",
            data.email,
        )

    return _serialize(invitation)


# ── Resend ────────────────────────────────────────────────────────────────────

async def resend_invitation(
    db: Prisma,
    invitation_id: str,
    resent_by_id: str,
    base_url: str,
) -> dict:
    """Re-send the invitation email. Only PENDING invitations can be resent."""
    invitation = await db.invitation.find_unique(where={"id": invitation_id})
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Only PENDING invitations can be resent (current: {invitation.status})",
        )
    if invitation.expiresAt < _utc_now():
        raise HTTPException(
            status_code=400,
            detail="Invitation has expired. Cancel it and send a new one.",
        )

    resender = await db.user.find_unique(where={"id": resent_by_id})
    resender_name = resender.name if resender else "Administrator"

    sent = await send_invitation_email(
        to=invitation.email,
        inviter_name=resender_name,
        role_label=_role_label(invitation.role),
        invite_token=invitation.inviteToken,
        base_url=base_url,
        app_name=settings.APP_NAME,
        expire_days=INVITE_EXPIRE_DAYS,
    )
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery failed. Check SMTP configuration.",
        )

    logger.info("Invitation resent to %s by user %s", invitation.email, resent_by_id)
    return _serialize(invitation)


# ── Accept ────────────────────────────────────────────────────────────────────

async def accept_invitation(db: Prisma, data: AcceptInvitation) -> dict:
    """
    PUBLIC endpoint — no auth required.
    Validates token, creates User, marks invitation ACCEPTED.
    """
    invitation = await db.invitation.find_unique(
        where={"inviteToken": data.invite_token}
    )

    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid or unknown invitation token")

    if invitation.status == "ACCEPTED":
        raise HTTPException(status_code=400, detail="This invitation has already been accepted")

    if invitation.status == "CANCELLED":
        raise HTTPException(status_code=400, detail="This invitation has been cancelled")

    if invitation.status == "EXPIRED" or invitation.expiresAt < _utc_now():
        # Auto-expire if not already marked
        if invitation.status == "PENDING":
            await db.invitation.update(
                where={"id": invitation.id},
                data={"status": "EXPIRED"},
            )
        raise HTTPException(status_code=400, detail="Invitation has expired. Request a new one.")

    # Edge-case: user registered externally between invite and accept
    existing = await db.user.find_unique(where={"email": invitation.email})
    if existing:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists. Please log in instead.",
        )

    # Create the user — they choose their own password (no temp password)
    user = await db.user.create(
        data={
            "name":         data.name,
            "email":        invitation.email,
            "passwordHash": hash_password(data.password),
            "role":         invitation.role,
            "isActive":     True,
        }
    )

    # Mark invitation used
    await db.invitation.update(
        where={"id": invitation.id},
        data={"status": "ACCEPTED", "acceptedAt": _utc_now()},
    )

    logger.info("Invitation accepted: %s → role=%s", user.email, user.role)

    return {
        "message": "Invitation accepted. Your account is ready — you can now log in.",
        "email":   user.email,
        "role":    user.role,
        "name":    user.name,
    }


# ── Cancel ────────────────────────────────────────────────────────────────────

async def cancel_invitation(
    db: Prisma,
    invitation_id: str,
) -> dict:
    """Soft-cancel: marks CANCELLED, keeps record for audit trail."""
    invitation = await db.invitation.find_unique(where={"id": invitation_id})
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Only PENDING invitations can be cancelled (current: {invitation.status})",
        )
    await db.invitation.update(
        where={"id": invitation_id},
        data={"status": "CANCELLED"},
    )
    return {"message": f"Invitation for '{invitation.email}' has been cancelled."}


# ── List ──────────────────────────────────────────────────────────────────────

async def list_invitations(
    db: Prisma,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
) -> dict:
    """Paginated invitation list with optional status filter."""
    where: dict = {}
    if status_filter:
        status_filter = status_filter.upper()
        valid = {"PENDING", "ACCEPTED", "EXPIRED", "CANCELLED"}
        if status_filter not in valid:
            raise HTTPException(status_code=400, detail=f"status must be one of {valid}")
        where["status"] = status_filter

    total = await db.invitation.count(where=where)
    skip  = (page - 1) * page_size

    rows = await db.invitation.find_many(
        where=where,
        order={"createdAt": "desc"},
        skip=skip,
        take=page_size,
    )

    return {
        "items":       [_serialize(r) for r in rows],
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": max(1, ceil(total / page_size)),
    }


# ── Serializer ────────────────────────────────────────────────────────────────

def _serialize(inv) -> dict:
    return {
        "id":          inv.id,
        "email":       inv.email,
        "role":        inv.role,
        "status":      inv.status,
        "inviteToken": inv.inviteToken,
        "invitedBy":   inv.invitedBy,
        "expiresAt":   inv.expiresAt,
        "acceptedAt":  inv.acceptedAt,
        "createdAt":   inv.createdAt,
    }