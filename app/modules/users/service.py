"""
app/modules/users/service.py
==============================
User CRUD — kept for backward compatibility alongside invitation flow.
The preferred way to add new users is via the invitation system.
"""
import logging
import secrets
import string

from fastapi import HTTPException, status
from prisma import Prisma

from app.core.email import send_password_reset_email
from app.core.security import hash_password

from .schema import UserUpdate

logger = logging.getLogger(__name__)


def _generate_temp_password(length: int = 14) -> str:
    """Generate a secure temp password: letters + digits + symbols."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    # Ensure at least one digit and one symbol
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    pwd += [secrets.choice(alphabet) for _ in range(length - 3)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


async def list_users(db: Prisma) -> list:
    return await db.user.find_many(order={"createdAt": "desc"})


async def get_user(db: Prisma, user_id: str):
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def update_user(db: Prisma, user_id: str, data: UserUpdate):
    await get_user(db, user_id)
    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    return await db.user.update(where={"id": user_id}, data=update_data)


async def reset_user_password(db: Prisma, user_id: str) -> dict:
    """
    Generate a new temp password, persist it, and email it to the user.
    Returns both a success message AND indicates whether email was delivered.
    """
    user = await get_user(db, user_id)
    temp_password = _generate_temp_password()

    await db.user.update(
        where={"id": user_id},
        data={"passwordHash": hash_password(temp_password)},
    )

    email_sent = await send_password_reset_email(
        to=user.email,
        name=user.name,
        new_password=temp_password,
    )

    if email_sent:
        logger.info("Password reset + email delivered → %s", user.email)
        return {
            "success": True,
            "message": f"Password reset. New credentials emailed to {user.email}.",
        }
    else:
        # Password IS reset — SMTP just failed. Surface the temp password in response
        # so CEO can relay it manually. Never log the raw password.
        logger.warning(
            "Password reset for %s succeeded but email delivery failed — "
            "check SMTP settings.",
            user.email,
        )
        return {
            "success":      True,
            "message":      (
                f"Password reset for {user.email}. "
                f"Email delivery failed (check SMTP settings). "
                f"Share the new password manually."
            ),
            "temp_password": temp_password,   # Only present when email fails
        }


async def delete_user(db: Prisma, user_id: str, requester_id: str) -> None:
    if user_id == requester_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await get_user(db, user_id)
    await db.user.delete(where={"id": user_id})