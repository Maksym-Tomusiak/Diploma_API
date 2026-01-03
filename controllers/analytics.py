from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.analytics import AnalyticsService
from crud.analytics import AnalyticsRepositoryDependency
from crud.user import UserRepositoryDependency
from db import get_db
from core import AdminUserDependency
from schemas.analytics import AnalyticsDashboardResponse

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_analytics_service(
    analytics_repository: AnalyticsRepositoryDependency = None,
    user_repository: UserRepositoryDependency = None
) -> AnalyticsService:
    return AnalyticsService(analytics_repository, user_repository)


AnalyticsServiceDependency = Annotated[AnalyticsService, Depends(get_analytics_service)]


@analytics_router.get("/dashboard", response_model=AnalyticsDashboardResponse)
async def get_dashboard_analytics(
    _: AdminUserDependency,
    analytics_service: AnalyticsServiceDependency,
):
    """
    Get analytics dashboard data.
    Requires admin privileges.
    """
    return analytics_service.get_dashboard_data()
