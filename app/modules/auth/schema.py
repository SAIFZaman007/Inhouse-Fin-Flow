"""
app/modules/auth/schema.py
===========================
Pydantic schemas for authentication endpoints.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password:     str = Field(..., min_length=8, description="Minimum 8 characters")

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("New password must contain at least one digit.")
        if not any(c.isalpha() for c in v):
            raise ValueError("New password must contain at least one letter.")
        return v


class MeResponse(BaseModel):
    id:       str
    name:     str
    email:    str
    role:     str
    isActive: bool

    class Config:
        from_attributes = True