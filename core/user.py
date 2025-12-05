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

    def delete_user(self, user_id: int) -> UserDto:
        """Delete a user by ID."""
        user = self.user_repository.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        deleted_user = self.user_repository.delete_user(user)
        return UserDto.from_user(deleted_user)


UserServiceDependency = Annotated[UserService, Depends(UserService)]
