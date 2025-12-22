from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status

from crud import UserRepositoryDependency
from models import User
from schemas.user import UserCreate, UserDto


class UserService:
    def __init__(self, user_repository: UserRepositoryDependency):
        self.user_repository = user_repository

    def get_user(self, user_id: int) -> Optional[UserDto]:
        """Get user by ID."""
        user = self.user_repository.get_user_by_id(user_id)
        if not user:
            return None
        return UserDto.from_user(user)

    def get_user_by_email(self, email: str) -> Optional[UserDto]:
        """Get user by email."""
        user = self.user_repository.get_user_by_email(email)
        if not user:
            return None
        return UserDto.from_user(user)

    def get_all_users(self) -> list[UserDto]:
        """Get all users."""
        users = self.user_repository.get_all_users()
        return [UserDto.from_user(user) for user in users]

    def create_user(self, data: UserCreate) -> UserDto:
        """Create a new user."""
        # Check if user already exists
        existing = self.user_repository.get_user_by_email(data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )

        user = User(email=data.email)
        created_user = self.user_repository.create_user(user)
        return UserDto.from_user(created_user)

    def get_or_create_user(self, email: str) -> UserDto:
        """Get existing user or create new one (for OAuth flow)."""
        user = self.user_repository.get_user_by_email(email)
        if not user:
            user = User(email=email)
            user = self.user_repository.create_user(user)
        return UserDto.from_user(user)

    def delete_user(self, user_id: int, admin_id: int) -> UserDto:
        """Delete a user by ID."""
        user = self.user_repository.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        from models.user import UserRole
        
        # Prevent admin from deleting themselves
        if user_id == admin_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot delete yourself",
            )
        
        # Prevent admin from deleting other admins
        if user.role == UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot delete another admin",
            )
        
        deleted_user = self.user_repository.delete_user(user)
        return UserDto.from_user(deleted_user)

    def ban_user(self, user_id: int, admin_id: int) -> UserDto:
        """Ban a user (admin only)."""
        user = self.user_repository.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        from models.user import UserRole
        
        # Prevent admin from banning themselves
        if user_id == admin_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot ban yourself",
            )
        
        # Prevent admin from banning other admins
        if user.role == UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot ban another admin",
            )
        
        user.is_banned = True
        updated = self.user_repository.update_user(user)
        return UserDto.from_user(updated)

    def unban_user(self, user_id: int) -> UserDto:
        """Unban a user (admin only)."""
        user = self.user_repository.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        user.is_banned = False
        updated = self.user_repository.update_user(user)
        return UserDto.from_user(updated)


UserServiceDependency = Annotated[UserService, Depends(UserService)]
