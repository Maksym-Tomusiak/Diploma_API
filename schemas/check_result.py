from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from models.check_result import CheckResult
from schemas.template import TemplateParams


class Issue(BaseModel):
    type: str
    severity: str  # "low", "medium", "high"
    details: str
    expected: Optional[str] = None
    actual: Optional[str] = None


class CheckDocumentRequest(BaseModel):
    """Request body for checking a document's formatting.
    
    Must provide either template_id OR custom_params (not both).
    When using custom_params, font_family can be optionally provided.
    """
    template_id: Optional[int] = Field(None, gt=0, description="ID of template to check against")
    custom_params: Optional[TemplateParams] = Field(None, description="Custom formatting parameters")
    font_family: Optional[str] = Field(None, max_length=255, description="Font family for custom params")

    @model_validator(mode='after')
    def validate_params(self):
        """Ensure either template_id or custom_params is provided, but not both."""
        if self.template_id is None and self.custom_params is None:
            raise ValueError("Either template_id or custom_params must be provided")
        if self.template_id is not None and self.custom_params is not None:
            raise ValueError("Cannot provide both template_id and custom_params")
        if self.font_family and self.template_id:
            raise ValueError("font_family can only be used with custom_params, not template_id")
        return self


class CheckResultDto(BaseModel):
    id: UUID
    document_id: UUID
    template_id: Optional[int] = Field(None, gt=0)  # Nullable when using custom params
    custom_params: Optional[dict] = None  # Stored custom params if used
    custom_font_family: Optional[str] = None  # Font family for custom mode
    passed: bool
    overall_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    issues_count: int = Field(..., ge=0)
    issues: List[Issue] = Field(default_factory=list)
    processing_time_ms: int = Field(..., ge=0)
    created_at: datetime

    @staticmethod
    def from_check_result(result: CheckResult) -> 'CheckResultDto':
        return CheckResultDto(
            id=result.id,
            document_id=result.document_id,
            template_id=result.template_id,
            custom_params=result.custom_params,
            custom_font_family=result.custom_font_family,
            passed=result.passed,
            overall_score=result.overall_score,
            issues_count=result.issues_count,
            issues=result.issues,
            processing_time_ms=result.processing_time_ms,
            created_at=result.created_at
        )

    model_config = SettingsConfigDict(from_attributes=True)


class UploadCheckResultDto(BaseModel):
    """
    Response model for uploaded file checks.
    Does not include database IDs since the file is not persisted.
    """
    passed: bool
    overall_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    issues_count: int = Field(..., ge=0)
    issues: List[Issue] = Field(default_factory=list)
    processing_time_ms: int = Field(..., ge=0)
    document_title: Optional[str] = None
    remaining_anonymous_checks: Optional[int] = None  # Only set for anonymous users
