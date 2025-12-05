from fastapi import APIRouter, HTTPException, status

from core import CheckResultServiceDependency, CurrentUserDependency
from schemas.check_result import CheckResultDto

check_result_router = APIRouter(prefix="/check-results", tags=["Check Results"])


@check_result_router.get("/{check_result_id}", response_model=CheckResultDto)
async def get_check_result(
    check_result_id: int,
    current_user: CurrentUserDependency,
    check_result_service: CheckResultServiceDependency,
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
    return check_result


@check_result_router.get("/document/{document_id}", response_model=list[CheckResultDto])
async def get_document_check_results(
    document_id: int,
    current_user: CurrentUserDependency,
    check_result_service: CheckResultServiceDependency,
):
    """
    Get all check results for a specific document.
    Only the document owner can access them.
    """
    return check_result_service.get_document_check_results(document_id, current_user.id)
