from pydantic import BaseModel, EmailStr, Field
from pydantic_settings import SettingsConfigDict
from datetime import datetime

from models.user import User, UserRole  # Import actual SQLAlchemy enum


class UserCreate(BaseModel):
    email: EmailStr = Field(..., description="User email address")


class UserDto(BaseModel):
    id: int = Field(..., gt=0)
    email: EmailStr
    role: UserRole  # Use actual SQLAlchemy enum (not string enum)
    is_banned: bool = False
    created_at: datetime

    @staticmethod
    def from_user(user: User) -> 'UserDto':
        return UserDto(
            id=user.id,
            email=user.email,
            role=user.role,  # Pydantic automatically converts SQLAlchemy enum
            is_banned=getattr(user, "is_banned", False),
            created_at=user.created_at
        )

    model_config = SettingsConfigDict(from_attributes=True)
