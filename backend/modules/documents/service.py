from pathlib import Path

from fastapi import BackgroundTasks

from core.config import resolve_path, settings
from core.database import get_database
from core.dependencies import CurrentUser
from modules.documents.repository import (
    ACTIVE_DOCUMENT_JOB_STATUSES,
    DocumentRepository,
    MongoDocumentRepository,
    RETRYABLE_DOCUMENT_JOB_STATUSES,
    RETRYABLE_DOCUMENT_JOB_TYPES,
    serialize_document,
    serialize_document_job,
    serialize_document_page,
)
from modules.documents.schemas import DocumentCreateRequest, DocumentPageUpdateRequest, DocumentUpdateRequest


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

    def list_pages(
        self,
        document_id: str,
        current_user: CurrentUser,
        *,
        limit: int = 100,
    ) -> dict | None:
        record = self.repository.find_by_id(document_id)
        if not record:
            return None
        self._ensure_access(record, current_user)
        pages = self.repository.list_pages(
            document_id,
            document_version=record.get("current_version"),
            limit=limit,
        )
        return {"items": [serialize_document_page(page) for page in pages]}

    def update_page(
        self,
        document_id: str,
        page_id: str,
        payload: DocumentPageUpdateRequest,
        current_user: CurrentUser,
    ) -> dict | None:
        record = self.repository.find_by_id(document_id)
        if not record:
            return None
        self._ensure_access(record, current_user)
        self._ensure_ocr_editable(record)
        page = self.repository.update_page(
            document_id,
            page_id,
            document_version=record.get("current_version", 1),
            cleaned_text=payload.cleaned_text,
        )
        return serialize_document_page(page) if page else None

    def retry_job(
        self,
        document_id: str,
        job_id: str,
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
    ) -> dict:
        document, job = self._accessible_job(document_id, job_id, current_user)
        if job.get("status") not in RETRYABLE_DOCUMENT_JOB_STATUSES:
            raise ValueError("Chỉ hỗ trợ retry job đã lỗi")
        if job.get("job_type") not in RETRYABLE_DOCUMENT_JOB_TYPES:
            raise ValueError("Hiện chỉ hỗ trợ retry OCR/CHUNK job")
        if job.get("job_type") == "CHUNK":
            from modules.rag.chunking import queue_chunk_retry

            queued = queue_chunk_retry(
                background_tasks,
                document_id=str(document["_id"]),
                config=job.get("config") or {},
            )
            new_job = self.repository.find_job(queued["chunk_job_id"])
            return {"job": serialize_document_job(new_job)}
        if job.get("job_type") == "INDEX":
            from modules.rag.chunking import queue_document_reindex

            queued = queue_document_reindex(
                background_tasks,
                document_id=str(document["_id"]),
                collection_name=(job.get("config") or {}).get("collection_name"),
            )
            new_job = self.repository.find_job(queued["index_job_id"])
            return {"job": serialize_document_job(new_job)}

        artifact = self._original_source_artifact(document)
        upload_path = ((artifact.get("storage") or {}).get("uri"))
        source_format = "docx" if artifact.get("type") == "ORIGINAL_DOCX" else "pdf"
        config = {**(job.get("config") or {}), "source_format": source_format}
        new_job = self.repository.create_job(document["_id"], "OCR", config=config)

        from modules.ocr.ocr import process_docx_background, process_ocr_background

        output_path = resolve_path(settings.ocr_output_dir) / f"{document['_id']}_result.md"
        processor = process_docx_background if source_format == "docx" else process_ocr_background
        background_tasks.add_task(
            processor,
            document_id=str(document["_id"]),
            job_id=str(new_job["_id"]),
            upload_path=str(Path(upload_path)),
            output_path=str(output_path),
            document_title=document.get("title") or document.get("original_filename") or "Document",
        )
        return {"job": serialize_document_job(new_job)}

    def cancel_job(
        self,
        document_id: str,
        job_id: str,
        current_user: CurrentUser,
    ) -> dict:
        _document, job = self._accessible_job(document_id, job_id, current_user)
        if job.get("status") not in ACTIVE_DOCUMENT_JOB_STATUSES:
            raise ValueError("Job không ở trạng thái có thể hủy")
        updated = self.repository.update_job(
            job_id,
            "CANCELLED",
            error_message=f"Cancelled by {current_user.role} {current_user.email}",
        )
        return {"job": serialize_document_job(updated)}

    def reindex(
        self,
        document_id: str,
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
    ) -> dict:
        record = self.repository.find_by_id(document_id)
        if not record:
            raise LookupError("Không tìm thấy tài liệu")
        self._ensure_access(record, current_user)
        summary = record.get("pipeline_summary") or {}
        current_processing = record.get("current_processing") or {}
        if not current_processing.get("chunk_set_id") or summary.get("chunk_status") != "COMPLETED":
            raise ValueError("Tài liệu cần chunk thành công trước khi re-index")
        from modules.rag.chunking import queue_document_reindex

        queued = queue_document_reindex(background_tasks, document_id=str(record["_id"]))
        new_job = self.repository.find_job(queued["index_job_id"])
        return {"job": serialize_document_job(new_job)}

    def can_use(self, document_id: str, current_user: CurrentUser) -> bool:
        record = self.repository.find_by_id(document_id)
        if not record:
            return False
        self._ensure_access(record, current_user)
        return True

    def _accessible_job(
        self,
        document_id: str,
        job_id: str,
        current_user: CurrentUser,
    ) -> tuple[dict, dict]:
        document = self.repository.find_by_id(document_id)
        if not document:
            raise LookupError("Không tìm thấy tài liệu")
        self._ensure_access(document, current_user)
        job = self.repository.find_job(job_id)
        if not job or str(job.get("document_id")) != str(document["_id"]):
            raise LookupError("Không tìm thấy job tài liệu")
        return document, job

    @staticmethod
    def _original_source_artifact(document: dict) -> dict:
        artifact = next(
            (
                item for item in document.get("artifacts", [])
                if item.get("type") in {"ORIGINAL_PDF", "ORIGINAL_DOCX"} and item.get("is_current", True)
            ),
            None,
        )
        upload_path = ((artifact or {}).get("storage") or {}).get("uri")
        if not upload_path:
            raise ValueError("Không tìm thấy file gốc để retry xử lý tài liệu")
        return artifact

    @staticmethod
    def _ensure_ocr_editable(document: dict) -> None:
        summary = document.get("pipeline_summary") or {}
        blocking_statuses = {"QUEUED", "PROCESSING", "COMPLETED"}
        if summary.get("chunk_status") in blocking_statuses or summary.get("index_status") in blocking_statuses:
            raise ValueError("Chỉ sửa OCR trước khi chunk/index hoặc sau khi chunk/index lỗi/hủy")


def get_document_service() -> DocumentService:
    return DocumentService(MongoDocumentRepository(get_database()))
