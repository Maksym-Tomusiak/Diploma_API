from typing import Annotated, Optional, List
from datetime import datetime, timedelta
from fastapi import Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc

from db import SessionDep
from models import UserActionLog


class UserActionLogRepository:
    def __init__(self, db: SessionDep):
        self.db = db

    def create_log(
        self,
        user_id: int,
        action_type: str,
        details: Optional[dict] = None
    ) -> UserActionLog:
        """Create a new user action log entry."""
        log_entry = UserActionLog(
            user_id=user_id,
            action_type=action_type,
            details=details,
            created_at=datetime.utcnow()
        )
        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(log_entry)
        return log_entry

    def get_logs_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[UserActionLog]:
        """Get action logs for a specific user."""
        return (
            self.db.query(UserActionLog)
            .filter(UserActionLog.user_id == user_id)
            .order_by(desc(UserActionLog.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_all_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        action_type: Optional[str] = None,
        user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> tuple[List[UserActionLog], int]:
        """
        Get all action logs with optional filters.
        Returns (logs, total_count).
        """
        query = self.db.query(UserActionLog).options(joinedload(UserActionLog.user))

        # Apply filters
        if action_type:
            query = query.filter(UserActionLog.action_type == action_type)
        if user_id:
            query = query.filter(UserActionLog.user_id == user_id)
        if start_date:
            query = query.filter(UserActionLog.created_at >= start_date)
        if end_date:
            query = query.filter(UserActionLog.created_at <= end_date)

        # Get total count
        total_count = query.count()

        # Apply pagination and ordering
        logs = (
            query
            .order_by(desc(UserActionLog.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

        return logs, total_count

    def get_log_by_id(self, log_id: int) -> Optional[UserActionLog]:
        """Get a specific log entry by ID."""
        return (
            self.db.query(UserActionLog)
            .options(joinedload(UserActionLog.user))
            .filter(UserActionLog.id == log_id)
            .first()
        )

    def delete_old_logs(self, days: int = 90) -> int:
        """Delete logs older than specified days. Returns number of deleted records."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        deleted = (
            self.db.query(UserActionLog)
            .filter(UserActionLog.created_at < cutoff_date)
            .delete()
        )
        self.db.commit()
        return deleted


UserActionLogRepositoryDependency = Annotated[UserActionLogRepository, Depends(UserActionLogRepository)]
