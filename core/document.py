from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status

from crud import DocumentRepositoryDependency
from models import Document, User
from models.document import DocumentStatus
from schemas.document import DocumentCreate, DocumentDto


class DocumentService:
    def __init__(self, document_repository: DocumentRepositoryDependency):
        self.document_repository = document_repository

    def get_document(self, document_id: int, user_id: int) -> Optional[DocumentDto]:
        """Get document by ID with ownership check."""
        document = self.document_repository.get_document_by_id(document_id)
        if not document:
            return None
        if document.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this document",
            )
        return DocumentDto.from_document(document)

    def get_user_documents(self, user_id: int) -> list[DocumentDto]:
        """Get all documents for a user."""
        documents = self.document_repository.get_documents_by_user_id(user_id)
        return [DocumentDto.from_document(doc) for doc in documents]

    def create_document(self, data: DocumentCreate, user: User) -> DocumentDto:
        """Create a new document."""
        # Check if document already exists
        existing = self.document_repository.get_document_by_google_doc_id(data.google_doc_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document with this Google Doc ID already exists",
            )

        document = Document(
            user_id=user.id,
            google_doc_id=data.google_doc_id,
            status=DocumentStatus.PENDING,
        )
        created_document = self.document_repository.create_document(document)
        return DocumentDto.from_document(created_document)

    def update_document_status(self, document_id: int, user_id: int, new_status: DocumentStatus) -> DocumentDto:
        """Update document status."""
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

        document.status = new_status
        updated_document = self.document_repository.update_document(document)
        return DocumentDto.from_document(updated_document)

    def delete_document(self, document_id: int, user_id: int) -> DocumentDto:
        """Delete a document with ownership check."""
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

        deleted_document = self.document_repository.delete_document(document)
        return DocumentDto.from_document(deleted_document)


DocumentServiceDependency = Annotated[DocumentService, Depends(DocumentService)]
