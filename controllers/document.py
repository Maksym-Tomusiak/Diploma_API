from fastapi import APIRouter, HTTPException, status

from core import DocumentServiceDependency, CurrentUserDependency
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
):
    """
    Create a new document for formatting check.
    """
    return document_service.create_document(data, current_user)


@document_router.delete("/{document_id}", response_model=DocumentDto)
async def delete_document(
    document_id: int,
    current_user: CurrentUserDependency,
    document_service: DocumentServiceDependency,
):
    """
    Delete a document.
    Only the document owner can delete it.
    """
    return document_service.delete_document(document_id, current_user.id)
