from fastapi import APIRouter, HTTPException, status, Request

from core import UserServiceDependency, CurrentUserDependency, AdminUserDependency, UserActionLogServiceDependency
from schemas.user import UserDto

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.get("", response_model=list[UserDto])
async def get_all_users(
    admin_user: AdminUserDependency,
    user_service: UserServiceDependency,
):
    """
    Get all users (admin only).
    """
    return user_service.get_all_users()


@user_router.get("/me", response_model=UserDto)
async def get_current_user(current_user: CurrentUserDependency):
    """
    Get current authenticated user.
    """
    return UserDto.from_user(current_user)


@user_router.get("/{user_id}", response_model=UserDto)
async def get_user(
    user_id: int,
    current_user: CurrentUserDependency,
    user_service: UserServiceDependency,
):
    """
    Get user by ID.
    Regular users can only view their own profile.
    Admins can view any user.
    """
    from models.user import UserRole
    
    # Check access permissions
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    user = user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@user_router.delete("/{user_id}", response_model=UserDto)
async def delete_user(
    user_id: int,
    admin_user: AdminUserDependency,
    user_service: UserServiceDependency,
):
    """
    Delete a user (admin only).
    """
    return user_service.delete_user(user_id)


@user_router.post("/{user_id}/ban", response_model=UserDto)
async def ban_user(
    user_id: int,
    admin_user: AdminUserDependency,
    user_service: UserServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
):
    """Ban a user (admin only)."""
    result = user_service.ban_user(user_id)
    # Log action
    log_service.log_action(
        user_id=admin_user.id,
        action_type="ADMIN_BAN_USER",
        details={"banned_user_id": user_id, "ip_address": request.client.host if request.client else None},
    )
    return result


@user_router.post("/{user_id}/unban", response_model=UserDto)
async def unban_user(
    user_id: int,
    admin_user: AdminUserDependency,
    user_service: UserServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
):
    """Unban a user (admin only)."""
    result = user_service.unban_user(user_id)
    # Log action
    log_service.log_action(
        user_id=admin_user.id,
        action_type="ADMIN_UNBAN_USER",
        details={"unbanned_user_id": user_id, "ip_address": request.client.host if request.client else None},
    )
    return result
