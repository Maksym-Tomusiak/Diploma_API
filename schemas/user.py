from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import SettingsConfigDict
from datetime import datetime
from typing import Optional
from uuid import UUID

from models.user import User, UserRole  # Import actual SQLAlchemy enum


class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="User email address")


class BanUserRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for banning the user")


class UserDto(BaseModel):
    id: UUID
    email: EmailStr
    role: UserRole  # Use actual SQLAlchemy enum (not string enum)
    is_banned: bool = False
    created_at: datetime
    google_access_token: str | None = None  # Add Google access token for Google Picker

    @staticmethod
    def from_user(user: User) -> 'UserDto':
        return UserDto(
            id=user.id,
            email=user.email,
            role=user.role,  # Pydantic automatically converts SQLAlchemy enum
            is_banned=getattr(user, "is_banned", False),
            created_at=user.created_at,
            google_access_token=user.google_token  # Include Google token for frontend
        )

    model_config = SettingsConfigDict(from_attributes=True)
