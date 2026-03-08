from typing import Optional
from pydantic import BaseModel, EmailStr
from app.shared.constants import RoleEnum


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: RoleEnum


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[RoleEnum] = None
    isActive: Optional[bool] = None


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    isActive: bool

    class Config:
        from_attributes = True