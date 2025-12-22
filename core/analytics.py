from datetime import datetime, timedelta
from typing import List

from crud.analytics import AnalyticsRepository
from crud.user import UserRepository
from schemas.analytics import (
    AnalyticsDashboardResponse,
    DocumentProcessingStats,
    UserRegistrationStats,
    RecentUserDto,
    UserActionDto,
)


class AnalyticsService:
    def __init__(self, analytics_repo: AnalyticsRepository, user_repo: UserRepository):
        self.analytics_repo = analytics_repo
        self.user_repo = user_repo

    def get_dashboard_data(self) -> AnalyticsDashboardResponse:
        """Get all analytics data for the dashboard"""
        
        # Get document processing stats
        doc_stats = self.analytics_repo.get_document_processing_last_week()
        
        # Fill in missing dates with zeros
        seven_days_ago = datetime.utcnow().date() - timedelta(days=6)
        date_map = {}
        for row in doc_stats:
            date_map[row.date] = {
                "checks": row.checks or 0,
                "formatting": row.formatting or 0,
            }
        
        document_processing = []
        for i in range(7):
            date = seven_days_ago + timedelta(days=i)
            stats = date_map.get(date, {"checks": 0, "formatting": 0})
            document_processing.append(
                DocumentProcessingStats(
                    date=date.strftime("%Y-%m-%d"),
                    checks=stats["checks"],
                    formatting=stats["formatting"],
                )
            )
        
        # Get user registration stats
        user_stats = self.analytics_repo.get_user_registrations_last_week()
        user_date_map = {row.date: row.count for row in user_stats}
        
        user_registrations = []
        for i in range(7):
            date = seven_days_ago + timedelta(days=i)
            count = user_date_map.get(date, 0)
            user_registrations.append(
                UserRegistrationStats(
                    date=date.strftime("%Y-%m-%d"),
                    count=count,
                )
            )
        
        # Get recent users
        recent_users_data = self.analytics_repo.get_recent_users(limit=10)
        recent_users = [
            RecentUserDto(
                id=user.id,
                email=user.email,
                created_at=user.created_at,
                role=user.role.value,
            )
            for user in recent_users_data
        ]
        
        # Get recent bans/unbans
        recent_actions_data = self.analytics_repo.get_recent_bans_unbans(limit=4)
        recent_bans_unbans = []
        
        for action in recent_actions_data:
            # Get the user who was banned/unbanned (from details), not the admin who performed the action
            target_user_id = None
            if action.details:
                target_user_id = action.details.get("banned_user_id") or action.details.get("unbanned_user_id")
            
            target_user_email = "Unknown"
            if target_user_id:
                target_user = self.user_repo.get_user_by_id(target_user_id)
                if target_user:
                    target_user_email = target_user.email
            
            recent_bans_unbans.append(
                UserActionDto(
                    id=action.id,
                    user_id=action.user_id,
                    user_email=target_user_email,
                    action_type=action.action_type,
                    timestamp=action.created_at,
                    details=action.details or {},
                )
            )
        
        return AnalyticsDashboardResponse(
            document_processing=document_processing,
            user_registrations=user_registrations,
            recent_users=recent_users,
            recent_bans_unbans=recent_bans_unbans,
        )
