from core.database import get_database
from modules.documents.repository import (
    DocumentRepository,
    MongoDocumentRepository,
    serialize_document,
)
from modules.documents.schemas import DocumentCreateRequest, DocumentUpdateRequest


class DocumentService:
    def __init__(self, repository: DocumentRepository):
        self.repository = repository

    def create(self, payload: DocumentCreateRequest, uploaded_by_user_id) -> dict:
        return serialize_document(
            self.repository.create(payload.model_dump(), uploaded_by_user_id)
        )

    def get(self, document_id: str) -> dict | None:
        record = self.repository.find_by_id(document_id)
        return serialize_document(record) if record else None

    def list(
        self,
        page: int,
        page_size: int,
        status: str | None,
        search: str | None,
    ) -> dict:
        records, total = self.repository.list(page, page_size, status, search)
        return {
            "items": [serialize_document(item) for item in records],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update(self, document_id: str, payload: DocumentUpdateRequest) -> dict | None:
        fields = payload.model_dump(exclude_none=True)
        record = self.repository.update(document_id, fields)
        return serialize_document(record) if record else None

    def archive(self, document_id: str) -> bool:
        return self.repository.archive(document_id)


def get_document_service() -> DocumentService:
    return DocumentService(MongoDocumentRepository(get_database()))
