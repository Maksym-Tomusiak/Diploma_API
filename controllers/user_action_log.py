from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException, status

from core import (
    UserActionLogServiceDependency,
    AdminUserDependency,
    CurrentUserDependency,
)
from schemas.user_action_log import UserActionLogDto, UserActionLogListResponse

user_action_log_router = APIRouter(prefix="/logs", tags=["User Action Logs"])


@user_action_log_router.get("")
def get_all_logs(
    admin_user: AdminUserDependency,
    log_service: UserActionLogServiceDependency,
    limit: int = Query(10, ge=1, le=1000, description="Number of logs to return"),
    skip: int = Query(0, ge=0, description="Number of logs to skip"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date (ISO format)"),
) -> dict:
    """
    Get all user action logs with optional filters (admin only).
    
    Supports filtering by:
    - action_type: Type of action performed
    - user_id: Specific user
    - start_date: Logs after this date
    - end_date: Logs before this date
    """
    logs, total = log_service.get_all_logs(
        limit=limit,
        offset=skip,
        action_type=action_type,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return {
        "logs": [UserActionLogDto.from_log(log) for log in logs],
        "total": total,
        "limit": limit,
        "skip": skip
    }


@user_action_log_router.get("/me", response_model=list[UserActionLogDto])
async def get_my_logs(
    current_user: CurrentUserDependency,
    log_service: UserActionLogServiceDependency,
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
):
    """
    Get action logs for the current authenticated user.
    """
    logs = log_service.get_user_logs(
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    return [UserActionLogDto.from_log(log) for log in logs]


@user_action_log_router.get("/{log_id}", response_model=UserActionLogDto)
async def get_log(
    log_id: int,
    admin_user: AdminUserDependency,
    log_service: UserActionLogServiceDependency,
):
    """
    Get a specific log entry by ID (admin only).
    """
    log = log_service.get_log(log_id)
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Log not found"
        )
    
    return UserActionLogDto.from_log(log)
