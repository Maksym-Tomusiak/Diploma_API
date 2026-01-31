from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from datetime import datetime

from models.base import Base


class AnonymousCheck(Base):
    """Track anonymous document checks for rate limiting."""
    
    __tablename__ = "anonymous_checks"
    
    # Use IP address as identifier for anonymous users
    ip_address = Column(String, primary_key=True, nullable=False)
    check_date = Column(DateTime, primary_key=True, nullable=False, default=func.now())
    check_count = Column(Integer, nullable=False, default=1)
    
    # Track when the record was last updated
    last_check_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
