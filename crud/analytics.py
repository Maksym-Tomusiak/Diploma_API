from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.orm import Session

from models.document import Document
from models.user import User
from models.user_action_log import UserActionLog


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_document_processing_last_week(self):
        """Get document processing statistics for the last 7 days"""
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        # Count documents created (which represents processing activity)
        # Since we log DOCUMENT_CREATE when documents are processed
        query = (
            select(
                func.date(UserActionLog.created_at).label("date"),
                func.count(
                    case((UserActionLog.action_type == "DOCUMENT_CREATE", 1))
                ).label("checks"),
                func.count(
                    case((UserActionLog.action_type == "CHECK_RESULT_VIEW", 1))
                ).label("formatting"),
            )
            .where(
                and_(
                    UserActionLog.created_at >= seven_days_ago,
                    or_(
                        UserActionLog.action_type == "DOCUMENT_CREATE",
                        UserActionLog.action_type == "CHECK_RESULT_VIEW",
                    )
                )
            )
            .group_by(func.date(UserActionLog.created_at))
            .order_by(func.date(UserActionLog.created_at))
        )
        
        return self.db.execute(query).all()

    def get_user_registrations_last_week(self):
        """Get user registration statistics for the last 7 days"""
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        
        query = (
            select(
                func.date(User.created_at).label("date"),
                func.count(User.id).label("count"),
            )
            .where(User.created_at >= seven_days_ago)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
        
        return self.db.execute(query).all()

    def get_recent_users(self, limit: int = 10):
        """Get most recently registered users"""
        query = (
            select(User)
            .order_by(User.created_at.desc())
            .limit(limit)
        )
        
        return self.db.scalars(query).all()

    def get_recent_bans_unbans(self, limit: int = 4):
        """Get recent ban and unban actions"""
        query = (
            select(UserActionLog)
            .where(
                or_(
                    UserActionLog.action_type == "ADMIN_BAN_USER",
                    UserActionLog.action_type == "ADMIN_UNBAN_USER",
                )
            )
            .order_by(UserActionLog.created_at.desc())
            .limit(limit)
        )
        
        return self.db.scalars(query).all()
