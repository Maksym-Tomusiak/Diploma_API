from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status

from crud import CheckResultRepositoryDependency, DocumentRepositoryDependency
from models import CheckResult
from schemas.check_result import CheckResultDto


class CheckResultService:
    def __init__(
        self,
        check_result_repository: CheckResultRepositoryDependency,
        document_repository: DocumentRepositoryDependency,
    ):
        self.check_result_repository = check_result_repository
        self.document_repository = document_repository

    def get_check_result(self, check_result_id: UUID, user_id: UUID) -> Optional[CheckResultDto]:
        """Get check result by ID with ownership validation."""
        check_result = self.check_result_repository.get_check_result_by_id(check_result_id)
        if not check_result:
            return None

        # Verify user owns the document
        document = self.document_repository.get_document_by_id(check_result.document_id)
        if not document or document.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this check result",
            )

        return CheckResultDto.from_check_result(check_result)

    def get_document_check_results(self, document_id: UUID, user_id: UUID) -> list[CheckResultDto]:
        """Get all check results for a document with ownership validation."""
        # Verify user owns the document
        document = self.document_repository.get_document_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        if document.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this document",
            )

        check_results = self.check_result_repository.get_check_results_by_document_id(document_id)
        return [CheckResultDto.from_check_result(cr) for cr in check_results]

    def create_check_result(
        self,
        document_id: UUID,
        passed: bool,
        overall_score: Optional[float],
        issues: list[dict],
        processing_time_ms: int,
        user_id: UUID,
        template_id: Optional[int] = None,
        custom_params: Optional[dict] = None,
        custom_font_family: Optional[str] = None,
    ) -> CheckResultDto:
        """Create a new check result for a document.
        
        Args:
            document_id: ID of the document being checked
            passed: Whether the check passed
            overall_score: Score from 0.0 to 1.0
            issues: List of formatting issues found
            processing_time_ms: Time taken for the check
            user_id: ID of the user performing the check
            template_id: ID of template used (optional, None if custom params)
            custom_params: Custom formatting params used (optional)
            custom_font_family: Font family for custom mode (optional)
        """
        # Verify user owns the document
        document = self.document_repository.get_document_by_id(document_id)
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        if document.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this document",
            )

        check_result = CheckResult(
            document_id=document_id,
            template_id=template_id,
            custom_params=custom_params,
            custom_font_family=custom_font_family,
            passed=passed,
            overall_score=overall_score,
            issues_count=len(issues),
            issues=issues,
            processing_time_ms=processing_time_ms,
        )
        created_result = self.check_result_repository.create_check_result(check_result)
        return CheckResultDto.from_check_result(created_result)


CheckResultServiceDependency = Annotated[CheckResultService, Depends(CheckResultService)]
