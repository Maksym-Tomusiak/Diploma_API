from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
from typing import Optional
from datetime import datetime

from models.document import Document, DocumentStatus  # Import actual enum


class DocumentCreate(BaseModel):
    google_doc_id: str = Field(..., min_length=1, max_length=255, description="Google Docs document ID")
    template_id: int = Field(..., gt=0, description="Template ID for formatting rules")
    title: Optional[str] = Field(None, max_length=500, description="Document title from Google Docs")


class DocumentDto(BaseModel):
    id: int = Field(..., gt=0)
    google_doc_id: str
    title: Optional[str]
    status: DocumentStatus  # Use actual SQLAlchemy enum
    created_at: datetime
    last_checked_at: Optional[datetime] = None

    @staticmethod
    def from_document(doc: Document) -> 'DocumentDto':
        # Get the most recent check result timestamp
        last_checked = None
        if doc.check_results:
            # Sort by created_at descending and get the first one
            sorted_checks = sorted(doc.check_results, key=lambda x: x.created_at, reverse=True)
            if sorted_checks:
                last_checked = sorted_checks[0].created_at
        
        return DocumentDto(
            id=doc.id,
            google_doc_id=doc.google_doc_id,
            title=doc.title,
            status=doc.status,
            created_at=doc.created_at,
            last_checked_at=last_checked
        )

    model_config = SettingsConfigDict(from_attributes=True)
