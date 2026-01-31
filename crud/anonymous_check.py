from typing import Annotated
from datetime import datetime, date

from fastapi import Depends
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from db import SessionDep
from models.anonymous_check import AnonymousCheck


class AnonymousCheckRepository:
    """Repository for managing anonymous check records."""
    
    def __init__(self, session: SessionDep):
        self.session = session
    
    def get_check_count_today(self, ip_address: str) -> int:
        """Get the number of checks performed by this IP today."""
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        result = self.session.execute(
            select(func.coalesce(func.sum(AnonymousCheck.check_count), 0))
            .where(
                and_(
                    AnonymousCheck.ip_address == ip_address,
                    AnonymousCheck.check_date >= today_start,
                    AnonymousCheck.check_date <= today_end
                )
            )
        ).scalar()
        
        return int(result) if result else 0
    
    def increment_check_count(self, ip_address: str) -> None:
        """Increment the check count for this IP address today."""
        today = date.today()
        today_datetime = datetime.combine(today, datetime.min.time())
        
        # Try to find existing record for today
        stmt = select(AnonymousCheck).where(
            and_(
                AnonymousCheck.ip_address == ip_address,
                AnonymousCheck.check_date == today_datetime
            )
        )
        existing = self.session.execute(stmt).scalar_one_or_none()
        
        if existing:
            # Increment existing count
            existing.check_count += 1
            existing.last_check_at = datetime.now()
        else:
            # Create new record for today
            new_check = AnonymousCheck(
                ip_address=ip_address,
                check_date=today_datetime,
                check_count=1,
                last_check_at=datetime.now()
            )
            self.session.add(new_check)
        
        self.session.commit()


AnonymousCheckRepositoryDependency = Annotated[AnonymousCheckRepository, Depends(AnonymousCheckRepository)]
