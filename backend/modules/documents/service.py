from core.database import get_database
from core.dependencies import CurrentUser
from modules.documents.repository import (
    DocumentRepository,
    MongoDocumentRepository,
    serialize_document,
    serialize_document_job,
)
from modules.documents.schemas import DocumentCreateRequest, DocumentUpdateRequest


class DocumentService:
    def __init__(self, repository: DocumentRepository):
        self.repository = repository

    @staticmethod
    def _owner_id(current_user: CurrentUser):
        return None if current_user.role == "Admin" else current_user.id

    @staticmethod
    def _ensure_access(record: dict | None, current_user: CurrentUser) -> None:
        if not record or current_user.role == "Admin":
            return
        if record.get("uploaded_by_user_id") != current_user.id:
            raise PermissionError("Bạn không có quyền truy cập tài liệu này")

    def create(self, payload: DocumentCreateRequest, uploaded_by_user_id) -> dict:
        return serialize_document(
            self.repository.create(payload.model_dump(), uploaded_by_user_id)
        )

    def get(self, document_id: str, current_user: CurrentUser | None = None) -> dict | None:
        record = self.repository.find_by_id(document_id)
        if current_user:
            self._ensure_access(record, current_user)
        return serialize_document(record) if record else None

    def list(
        self,
        page: int,
        page_size: int,
        status: str | None,
        search: str | None,
        current_user: CurrentUser | None = None,
    ) -> dict:
        records, total = self.repository.list(
            page,
            page_size,
            status,
            search,
            uploaded_by_user_id=self._owner_id(current_user) if current_user else None,
        )
        return {
            "items": [serialize_document(item) for item in records],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update(
        self,
        document_id: str,
        payload: DocumentUpdateRequest,
        current_user: CurrentUser | None = None,
    ) -> dict | None:
        if current_user:
            self._ensure_access(self.repository.find_by_id(document_id), current_user)
        fields = payload.model_dump(exclude_none=True)
        record = self.repository.update(document_id, fields)
        return serialize_document(record) if record else None

    def archive(self, document_id: str, current_user: CurrentUser | None = None) -> bool:
        if current_user:
            self._ensure_access(self.repository.find_by_id(document_id), current_user)
        return self.repository.archive(document_id)

    def list_jobs(
        self,
        document_id: str,
        current_user: CurrentUser,
        *,
        limit: int = 20,
    ) -> dict | None:
        record = self.repository.find_by_id(document_id)
        if not record:
            return None
        self._ensure_access(record, current_user)
        jobs = self.repository.list_jobs(document_id, limit=limit)
        return {"items": [serialize_document_job(job) for job in jobs]}

    def can_use(self, document_id: str, current_user: CurrentUser) -> bool:
        record = self.repository.find_by_id(document_id)
        if not record:
            return False
        self._ensure_access(record, current_user)
        return True


def get_document_service() -> DocumentService:
    return DocumentService(MongoDocumentRepository(get_database()))
