from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
from typing import List, Optional
from datetime import datetime

from models.check_result import CheckResult


class Issue(BaseModel):
    type: str
    severity: str  # "low", "medium", "high"
    details: str


class CheckResultDto(BaseModel):
    id: int = Field(..., gt=0)
    document_id: int = Field(..., gt=0)
    template_id: int = Field(..., gt=0)
    passed: bool
    overall_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    issues_count: int = Field(..., ge=0)
    issues: List[Issue] = Field(default_factory=list)
    processing_time_ms: int = Field(..., gt=0)
    created_at: datetime

    @staticmethod
    def from_check_result(result: CheckResult) -> 'CheckResultDto':
        return CheckResultDto(
            id=result.id,
            document_id=result.document_id,
            template_id=result.template_id,
            passed=result.passed,
            overall_score=result.overall_score,
            issues_count=result.issues_count,
            issues=result.issues,
            processing_time_ms=result.processing_time_ms,
            created_at=result.created_at
        )

    model_config = SettingsConfigDict(from_attributes=True)
