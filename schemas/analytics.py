from datetime import datetime
from pydantic import BaseModel
from typing import List


class DocumentProcessingStats(BaseModel):
    date: str
    checks: int
    formatting: int


class UserRegistrationStats(BaseModel):
    date: str
    count: int


class RecentUserDto(BaseModel):
    id: int
    email: str
    created_at: datetime
    role: str


class UserActionDto(BaseModel):
    id: int
    user_id: int
    user_email: str
    action_type: str
    timestamp: datetime
    details: dict


class AnalyticsDashboardResponse(BaseModel):
    document_processing: List[DocumentProcessingStats]
    user_registrations: List[UserRegistrationStats]
    recent_users: List[RecentUserDto]
    recent_bans_unbans: List[UserActionDto]
