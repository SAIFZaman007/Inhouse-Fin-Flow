"""
app/modules/invitations/schema.py
===================================
Pydantic schemas for the invitation flow:
  - Invite   (CEO sends email → pending invitation)
  - Resend   (CEO re-sends same token)
  - Accept   (invitee sets name + password → account created)
  - Cancel   (CEO cancels pending)
  - List     (paginated invitation history)
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.shared.constants import RoleEnum


class InviteCreate(BaseModel):
    """Body for POST /api/v1/users/invitations — send invite email."""
    email: EmailStr
    role: RoleEnum = Field(..., description="Role to assign: CEO, DIRECTOR, or HR")


class AcceptInvitation(BaseModel):
    """Body for POST /api/v1/users/invitations/accept — public endpoint."""
    invite_token: str = Field(..., min_length=10)
    name:         str = Field(..., min_length=2, max_length=100)
    password:     str = Field(..., min_length=8, description="Password (min 8 chars)")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class InvitationResponse(BaseModel):
    """Returned for all invitation CRUD operations."""
    id:            str
    email:         str
    role:          str
    status:        str
    invite_token:  str  = Field(alias="inviteToken")
    invited_by:    str  = Field(alias="invitedBy")
    expires_at:    datetime = Field(alias="expiresAt")
    accepted_at:   Optional[datetime] = Field(None, alias="acceptedAt")
    created_at:    datetime = Field(alias="createdAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class InvitationListResponse(BaseModel):
    """Paginated list of invitations."""
    items:       list[InvitationResponse]
    total:       int
    page:        int
    page_size:   int
    total_pages: int