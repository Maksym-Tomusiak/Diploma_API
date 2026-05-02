from fastapi import APIRouter, HTTPException, status, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from uuid import UUID
from typing import Optional
from io import BytesIO

from core import (
    DocumentServiceDependency,
    CurrentUserDependency,
    OptionalUserDependency,
    UserActionLogServiceDependency,
    CheckResultServiceDependency,
    TemplateServiceDependency,
    UserServiceDependency,
)
from core.format_checker import FormatCheckerServiceDependency
from core.document_formatter import DocumentFormatterServiceDependency
from core.local_document import LocalDocumentService
from core.rate_limit import RateLimitServiceDependency
from schemas.document import DocumentCreate, DocumentDto, FormatDocumentRequest, FormatResultDto
from schemas.check_result import CheckDocumentRequest, CheckResultDto, UploadCheckResultDto
from schemas.template import TemplateParams

document_router = APIRouter(prefix="/documents", tags=["Documents"])


# ====================
# Upload Endpoints (must come before parameterized routes)
# ====================

@document_router.post("/upload/check", response_model=UploadCheckResultDto)
async def check_uploaded_document(
    request: Request,
    template_service: TemplateServiceDependency,
    rate_limit_service: RateLimitServiceDependency,
    current_user: OptionalUserDependency = None,
    log_service: UserActionLogServiceDependency = None,
    file: UploadFile = File(..., description="The .docx file to check"),
    template_id: Optional[int] = Form(None, description="Template ID to check against"),
    custom_params: Optional[str] = Form(None, description="Custom parameters as JSON string"),
    font_family: Optional[str] = Form(None, description="Font family for custom parameters"),
):
    """
    Check an uploaded .docx file's formatting against a template or custom parameters.
    
    Provide either:
    - template_id: Use an existing template's formatting rules
    - custom_params (JSON string) + optional font_family: Use custom formatting parameters
    
    File is not saved, only read and analyzed.
    
    Anonymous users: Limited to 10 checks per day.
    Authenticated users: Unlimited checks.
    """
    # Handle rate limiting for anonymous users
    remaining_checks = None
    if not current_user:
        # Anonymous user - apply rate limiting
        rate_info = rate_limit_service.check_and_increment_anonymous_limit(request)
        remaining_checks = rate_info["remaining_checks"]
    else:
        # Authenticated user - check for banned status
        if current_user.is_banned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot check documents while your account is banned",
            )
    
    # Validate file is provided and not empty
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )
    
    # Validate file type
    if not file.filename.endswith('.docx'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .docx files are supported",
        )
    
    # Read file content
    try:
        file_content = await file.read()
        if not file_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}",
        )
    
    # Get formatting parameters
    params: TemplateParams
    expected_font_family: str | None = None
    template_id_value: int | None = template_id
    custom_params_dict: dict | None = None
    
    if template_id:
        # Using template
        template = template_service.get_template(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found",
            )
        params = TemplateParams(**template.params)
        expected_font_family = template.font_family
    elif custom_params:
        # Using custom parameters
        import json
        try:
            custom_params_dict = json.loads(custom_params)
            params = TemplateParams(**custom_params_dict)
            expected_font_family = font_family
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid custom parameters: {str(e)}",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either template_id or custom_params must be provided",
        )
    
    # Perform check
    try:
        local_doc_service = LocalDocumentService()
        check_result = local_doc_service.check_document(
            file_content=file_content,
            params=params,
            expected_font_family=expected_font_family,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check document: {str(e)}",
        )
    
    # Log the check (only for authenticated users)
    if current_user and log_service:
        log_service.log_action(
            user_id=current_user.id,
            action_type="DOCUMENT_CHECK",
            details={
                "file_name": file.filename,
                "template_id": template_id_value,
                "custom_params": custom_params_dict,
                "check_passed": check_result.passed,
                "overall_score": check_result.overall_score,
                "issues_count": len(check_result.issues),
                "ip_address": request.client.host if request.client else None,
            }
        )
    
    result = UploadCheckResultDto(
        passed=check_result.passed,
        overall_score=check_result.overall_score,
        issues_count=len(check_result.issues),
        issues=[issue.to_dict() for issue in check_result.issues],
        processing_time_ms=check_result.processing_time_ms,
        document_title=check_result.document_title or file.filename,
    )
    
    # Add remaining checks info for anonymous users
    if remaining_checks is not None:
        result.remaining_anonymous_checks = remaining_checks
    
    return result


@document_router.post("/upload/format")
async def format_uploaded_document(
    current_user: CurrentUserDependency,
    template_service: TemplateServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
    file: UploadFile = File(...),
    template_id: Optional[int] = Form(None),
    custom_params: Optional[str] = Form(None),
    font_family: Optional[str] = Form(None),
):
    """
    Format an uploaded .docx file according to a template or custom parameters.
    
    Provide either:
    - template_id: Use an existing template's formatting rules
    - custom_params (JSON string) + optional font_family: Use custom formatting parameters
    
    Returns the formatted document as a downloadable .docx file.
    """
    # Check for banned users
    if current_user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot format documents while your account is banned",
        )
    
    # Validate file type
    if not file.filename or not file.filename.endswith('.docx'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .docx files are supported",
        )
    
    # Read file content
    try:
        file_content = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}",
        )
    
    # Get formatting parameters
    params: TemplateParams
    expected_font_family: str | None = None
    template_id_value: int | None = template_id
    custom_params_dict: dict | None = None
    
    if template_id:
        # Using template
        template = template_service.get_template(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found",
            )
        params = TemplateParams(**template.params)
        expected_font_family = template.font_family
    elif custom_params:
        # Using custom parameters
        import json
        try:
            custom_params_dict = json.loads(custom_params)
            params = TemplateParams(**custom_params_dict)
            expected_font_family = font_family
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid custom parameters: {str(e)}",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either template_id or custom_params must be provided",
        )
    
    # Perform formatting
    try:
        local_doc_service = LocalDocumentService()
        formatted_content, format_result = local_doc_service.format_document(
            file_content=file_content,
            params=params,
            expected_font_family=expected_font_family,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to format document: {str(e)}",
        )
    
    # Log the format operation
    log_service.log_action(
        user_id=current_user.id,
        action_type="DOCUMENT_FORMAT",
        details={
            "file_name": file.filename,
            "template_id": template_id_value,
            "custom_params": custom_params_dict,
            "changes_applied": format_result.changes_applied,
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    # Return formatted document as downloadable file
    # Use RFC 5987 encoding for non-ASCII filenames
    from urllib.parse import quote
    output_filename = f"formatted_{file.filename}"
    encoded_filename = quote(output_filename)
    
    return StreamingResponse(
        BytesIO(formatted_content),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        }
    )


# ====================
# Document Management Endpoints
# ====================

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
            "document_title": document.title,
            "template_id": template_id,
            "custom_params": custom_params_dict is not None,
            "passed": check_result.passed,
            "score": check_result.overall_score,
            "issues_count": len(check_result.issues),
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    return saved_result


@document_router.post("/{document_id}/format", response_model=FormatResultDto)
async def format_document(
    document_id: UUID,
    data: FormatDocumentRequest,
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
    template_service: TemplateServiceDependency,
    document_formatter: DocumentFormatterServiceDependency,
    user_service: UserServiceDependency,
    log_service: UserActionLogServiceDependency,
    request: Request,
):
    """
    Apply formatting to a document based on a template or custom parameters.
    
    This will modify the actual Google Doc, applying:
    - Font size and font family
    - Line spacing
    - Page margins
    
    Provide either:
    - template_id: Use an existing template's formatting rules
    - custom_params + optional font_family: Use custom formatting parameters
    """
    # Check for banned users
    if current_user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot format documents while your account is banned",
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
    elif data.custom_params:
        # Using custom params
        params = data.custom_params
        font_family = data.font_family
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either template_id or custom_params must be provided",
        )
    
    # Callback to save refreshed Google token
    def on_token_refresh(new_token: str):
        user_service.update_google_token(current_user.id, new_token)
    
    # Perform the format operation
    format_result = document_formatter.format_document(
        google_token=current_user.google_token,
        doc_id=document.google_doc_id,
        params=params,
        expected_font_family=font_family,
        refresh_token=current_user.google_refresh_token,
        on_token_refresh=on_token_refresh,
    )
    
    # Log the format action
    log_service.log_action(
        user_id=current_user.id,
        action_type="DOCUMENT_FORMAT",
        details={
            "document_id": str(document_id),
            "document_title": document.title,
            "template_id": template_id,
            "custom_params": data.custom_params is not None,
            "success": format_result.success,
            "changes_applied": format_result.changes_applied,
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    if not format_result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=format_result.error_message or "Failed to format document",
        )
    
    return FormatResultDto(
        success=format_result.success,
        changes_applied=format_result.changes_applied,
        changes=[
            {
                "type": c.type,
                "description": c.description,
                "before": c.before,
                "after": c.after,
            }
            for c in format_result.changes
        ],
        processing_time_ms=format_result.processing_time_ms,
        document_title=format_result.document_title,
    )

