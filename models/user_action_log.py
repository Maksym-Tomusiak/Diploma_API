from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB

from models.base import Base


class UserActionLog(Base):
    __tablename__ = 'user_action_logs'

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('users.id'),
        nullable=False,
        index=True
    )
    
    # Action type: "LOGIN", "LOGOUT", "DOCUMENT_UPLOAD", "FORMAT_REQUEST", etc.
    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    
    # Flexible details: store action-specific data as JSON
    details: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True
    )
    
    # Timestamp (automatically set)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        index=True,
        nullable=False
    )

    # Relationship to user to access email/name in admin panel
    user: Mapped["User"] = relationship("User", back_populates="action_logs")
