from typing import Annotated, Optional, List
from datetime import datetime
from fastapi import Depends

from crud import UserActionLogRepositoryDependency
from models import UserActionLog


class UserActionLogService:
    def __init__(self, log_repository: UserActionLogRepositoryDependency):
        self.log_repository = log_repository

    def log_action(
        self,
        user_id: int,
        action_type: str,
        details: Optional[dict] = None
    ) -> UserActionLog:
        """Log a user action."""
        return self.log_repository.create_log(
            user_id=user_id,
            action_type=action_type,
            details=details
        )

    def get_user_logs(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[UserActionLog]:
        """Get logs for a specific user."""
        return self.log_repository.get_logs_by_user(user_id, limit, offset)

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
        Get all logs with filters (admin only).
        Returns (logs, total_count).
        """
        return self.log_repository.get_all_logs(
            limit=limit,
            offset=offset,
            action_type=action_type,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

    def get_log(self, log_id: int) -> Optional[UserActionLog]:
        """Get a specific log entry."""
        return self.log_repository.get_log_by_id(log_id)


UserActionLogServiceDependency = Annotated[UserActionLogService, Depends(UserActionLogService)]
