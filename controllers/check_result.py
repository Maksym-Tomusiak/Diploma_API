from fastapi import APIRouter, HTTPException, status, Request
from uuid import UUID

from core import CheckResultServiceDependency, CurrentUserDependency, UserActionLogServiceDependency
from schemas.check_result import CheckResultDto

check_result_router = APIRouter(prefix="/check-results", tags=["Check Results"])


@check_result_router.get("/{check_result_id}", response_model=CheckResultDto)
async def get_check_result(
    check_result_id: UUID,
    current_user: CurrentUserDependency,
    check_result_service: CheckResultServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
):
    """
    Get a specific check result by ID.
    Only the document owner can access it.
    """
    check_result = check_result_service.get_check_result(check_result_id, current_user.id)
    if not check_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check result not found",
        )
    
    # Log check result access
    log_service.log_action(
        user_id=current_user.id,
        action_type="CHECK_RESULT_VIEW",
        details={
            "check_result_id": str(check_result_id),
            "document_id": str(check_result.document_id),
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    return check_result


@check_result_router.get("/document/{document_id}", response_model=list[CheckResultDto])
async def get_document_check_results(
    document_id: UUID,
    current_user: CurrentUserDependency,
    check_result_service: CheckResultServiceDependency,
):
    """
    Get all check results for a specific document.
    Only the document owner can access them.
    """
    return check_result_service.get_document_check_results(document_id, current_user.id)
