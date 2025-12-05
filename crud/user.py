from typing import Annotated, Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionDep
from models import User


class UserRepository:
    def __init__(self, session: SessionDep):
        self.session = session

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        return self.session.get(User, user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        query = select(User).where(User.email == email)
        return self.session.scalars(query).first()

    def get_all_users(self) -> list[User]:
        query = select(User)
        return list(self.session.scalars(query).all())

    def create_user(self, user: User) -> User:
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def update_user(self, user: User) -> User:
        self.session.commit()
        self.session.refresh(user)
        return user

    def delete_user(self, user: User) -> User:
        self.session.delete(user)
        self.session.commit()
        return user


UserRepositoryDependency = Annotated[UserRepository, Depends(UserRepository)]
