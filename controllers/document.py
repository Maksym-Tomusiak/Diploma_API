from fastapi import APIRouter, HTTPException, status, Request
from uuid import UUID

from core import (
    DocumentServiceDependency,
    CurrentUserDependency,
    UserActionLogServiceDependency,
    CheckResultServiceDependency,
    TemplateServiceDependency,
    UserServiceDependency,
)
from core.format_checker import FormatCheckerServiceDependency
from schemas.document import DocumentCreate, DocumentDto
from schemas.check_result import CheckDocumentRequest, CheckResultDto
from schemas.template import TemplateParams

document_router = APIRouter(prefix="/documents", tags=["Documents"])


@document_router.get("", response_model=list[DocumentDto])
async def get_user_documents(
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
):
    """
    Get all documents for the current user.
    """
    return document_service.get_user_documents(current_user.id)


@document_router.get("/by-google-id/{google_doc_id}", response_model=DocumentDto)
async def get_document_by_google_id(
    google_doc_id: str,
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
):
    """
    Get a document by Google Doc ID.
    Only the document owner can access it.
    """
    document = document_service.get_document_by_google_id(google_doc_id, current_user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


@document_router.get("/{document_id}", response_model=DocumentDto)
async def get_document(
    document_id: UUID,
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
):
    """
    Get a specific document by ID.
    Only the document owner can access it.
    """
    document = document_service.get_document(document_id, current_user.id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return document


@document_router.post("", response_model=DocumentDto, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: DocumentCreate,
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
):
    """
    Create a new document for formatting check.
    """
    # Explicit check for banned users
    if current_user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create documents while your account is banned",
        )
    
    document = document_service.create_document(data, current_user)
    
    # Log document creation
    log_service.log_action(
        user_id=current_user.id,
        action_type="DOCUMENT_CREATE",
        details={
            "document_id": str(document.id),
            "google_doc_id": data.google_doc_id,
            "title": data.title,
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    return document


@document_router.delete("/{document_id}", response_model=DocumentDto)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
):
    """
    Delete a document.
    Only the document owner can delete it.
    """
    # Explicit check for banned users
    if current_user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete documents while your account is banned",
        )
    
    document = document_service.delete_document(document_id, current_user.id)
    
    # Log document deletion
    log_service.log_action(
        user_id=current_user.id,
        action_type="DOCUMENT_DELETE",
        details={
            "document_id": str(document_id),
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    return document


@document_router.post("/{document_id}/check", response_model=CheckResultDto)
async def check_document(
    document_id: UUID,
    data: CheckDocumentRequest,
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
    template_service: TemplateServiceDependency,
    format_checker: FormatCheckerServiceDependency,
    check_result_service: CheckResultServiceDependency,
    user_service: UserServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
):
    """
    Check a document's formatting against a template or custom parameters.
    
    Provide either:
    - template_id: Use an existing template's formatting rules
    - custom_params + optional font_family: Use custom formatting parameters
    
    Custom parameters avoid creating template entities in the database.
    """
    # Check for banned users
    if current_user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot check documents while your account is banned",
        )
    
    # Verify document exists and belongs to user (admins can access any document)
    from models.user import UserRole
    is_admin = current_user.role == UserRole.ADMIN
    document = document_service.get_document(document_id, current_user.id, is_admin=is_admin)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    
    # Verify user has Google token
    if not current_user.google_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google access token found. Please log in again.",
        )
    
    # Get formatting parameters
    params: TemplateParams
    font_family: str | None = None
    template_id: int | None = None
    custom_params_dict: dict | None = None
    
    if data.template_id:
        # Using template
        template = template_service.get_template(data.template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found",
            )
        params = TemplateParams(**template.params)
        font_family = template.font_family
        template_id = data.template_id
    else:
        # Using custom params
        params = data.custom_params
        font_family = data.font_family
        custom_params_dict = params.model_dump()
    
    # Callback to save refreshed Google token
    def on_token_refresh(new_token: str):
        user_service.update_google_token(current_user.id, new_token)
    
    # Perform the format check
    check_result = format_checker.check_document(
        google_token=current_user.google_token,
        doc_id=document.google_doc_id,
        params=params,
        expected_font_family=font_family,
        refresh_token=current_user.google_refresh_token,
        on_token_refresh=on_token_refresh,
    )
    
    # Save the check result
    saved_result = check_result_service.create_check_result(
        document_id=document_id,
        passed=check_result.passed,
        overall_score=check_result.overall_score,
        issues=check_result.issues_as_dicts(),
        processing_time_ms=check_result.processing_time_ms,
        user_id=current_user.id,
        template_id=template_id,
        custom_params=custom_params_dict,
        custom_font_family=data.font_family if data.custom_params else None,
    )
    
    # Log the check action
    log_service.log_action(
        user_id=current_user.id,
        action_type="DOCUMENT_CHECK",
        details={
            "document_id": str(document_id),
            "template_id": template_id,
            "custom_params": custom_params_dict is not None,
            "passed": check_result.passed,
            "score": check_result.overall_score,
            "issues_count": len(check_result.issues),
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    return saved_result
