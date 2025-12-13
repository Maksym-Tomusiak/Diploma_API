from fastapi import APIRouter, HTTPException, status, Request

from core import DocumentServiceDependency, CurrentUserDependency, UserActionLogServiceDependency
from schemas.document import DocumentCreate, DocumentDto

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


@document_router.get("/{document_id}", response_model=DocumentDto)
async def get_document(
    document_id: int,
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
            "document_id": document.id,
            "google_doc_id": data.google_doc_id,
            "title": data.title,
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    return document


@document_router.delete("/{document_id}", response_model=DocumentDto)
async def delete_document(
    document_id: int,
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
            "document_id": document_id,
            "ip_address": request.client.host if request.client else None,
        }
    )
    
    return document
