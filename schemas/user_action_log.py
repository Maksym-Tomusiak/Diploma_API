from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class UserActionLogBase(BaseModel):
    """Base schema for user action log."""
    action_type: str
    details: Optional[dict] = None


class UserActionLogCreate(UserActionLogBase):
    """Schema for creating a user action log."""
    user_id: int


class UserActionLogDto(UserActionLogBase):
    """Schema for returning user action log data."""
    id: int
    user_id: int
    created_at: datetime
    
    # User info for admin view
    user_email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_log(cls, log: "UserActionLog"):
        """Create DTO from UserActionLog model."""
        return cls(
            id=log.id,
            user_id=log.user_id,
            action_type=log.action_type,
            details=log.details,
            created_at=log.created_at,
            user_email=log.user.email if log.user else None
        )


class UserActionLogListResponse(BaseModel):
    """Schema for paginated list of logs."""
    logs: list[UserActionLogDto]
    total: int
    limit: int
    offset: int
