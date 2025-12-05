from typing import Annotated, Optional

from fastapi import Depends
from sqlalchemy import select

from db import SessionDep
from models import Document


class DocumentRepository:
    def __init__(self, session: SessionDep):
        self.session = session

    def get_document_by_id(self, document_id: int) -> Optional[Document]:
        return self.session.get(Document, document_id)

    def get_documents_by_user_id(self, user_id: int) -> list[Document]:
        query = select(Document).where(Document.user_id == user_id)
        return list(self.session.scalars(query).all())

    def get_document_by_google_doc_id(self, google_doc_id: str) -> Optional[Document]:
        query = select(Document).where(Document.google_doc_id == google_doc_id)
        return self.session.scalars(query).first()

    def create_document(self, document: Document) -> Document:
        self.session.add(document)
        self.session.commit()
        self.session.refresh(document)
        return document

    def update_document(self, document: Document) -> Document:
        self.session.commit()
        self.session.refresh(document)
        return document

    def delete_document(self, document: Document) -> Document:
        self.session.delete(document)
        self.session.commit()
        return document


DocumentRepositoryDependency = Annotated[DocumentRepository, Depends(DocumentRepository)]
