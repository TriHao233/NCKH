from core.database import get_database
from modules.documents.repository import (
    MongoDocumentRepository,
    json_safe,
    serialize_document,
)


def _repository() -> MongoDocumentRepository:
    return MongoDocumentRepository(get_database())


def create_document_record(
    filename: str,
    title: str,
    *,
    uploaded_by_user_id=None,
    subject_id: str | None = None,
    chapter_id: str | None = None,
) -> str:
    document = _repository().create(
        {
            "original_filename": filename,
            "title": title,
            "subject_id": subject_id,
            "chapter_id": chapter_id,
        },
        uploaded_by_user_id,
    )
    return str(document["_id"])


def attach_original_artifact(
    document_id: str,
    *,
    uri: str,
    size_bytes: int,
    sha256: str,
    artifact_type: str = "ORIGINAL_PDF",
    mime_type: str = "application/pdf",
) -> None:
    _repository().attach_original_artifact(
        document_id,
        uri=uri,
        size_bytes=size_bytes,
        sha256=sha256,
        artifact_type=artifact_type,
        mime_type=mime_type,
    )


def attach_processing_artifact(
    document_id: str,
    job_id: str,
    *,
    uri: str,
    size_bytes: int,
    sha256: str,
    artifact_type: str,
    mime_type: str,
) -> None:
    _repository().attach_processing_artifact(
        document_id,
        job_id=job_id,
        uri=uri,
        size_bytes=size_bytes,
        sha256=sha256,
        artifact_type=artifact_type,
        mime_type=mime_type,
    )


def create_ocr_job(document_id: str, config: dict | None = None) -> str:
    job = _repository().create_job(document_id, "OCR", config=config)
    return str(job["_id"])


def update_document_status(
    document_id: str,
    job_id: str,
    status: str,
    stats: dict | None = None,
    error_message: str | None = None,
):
    normalized = {
        "queued": "QUEUED",
        "processing": "PROCESSING",
        "completed": "COMPLETED",
        "failed": "FAILED",
    }.get(status.lower(), status.upper())
    repository = _repository()
    repository.update_job(
        job_id,
        normalized,
        progress=100 if normalized == "COMPLETED" else None,
        stats=stats,
        error_message=error_message,
    )
    if normalized == "COMPLETED":
        document = repository.find_by_id(document_id)
        has_active_lineage = bool(
            ((document or {}).get("current_processing") or {}).get("chunk_set_id")
        )
        if document and not has_active_lineage:
            get_database().documents.update_one(
                {"_id": document["_id"], "archived_at": None},
                {
                    "$set": {
                        "status": "PROCESSING",
                        "pipeline_summary.chunk_status": "NOT_STARTED",
                        "pipeline_summary.index_status": "NOT_STARTED",
                    }
                },
            )


def save_document_pages(document_id: str, job_id: str, pages: list):
    return _repository().save_pages(document_id, job_id, pages)


def get_document_status(job_id: str) -> dict | None:
    repository = _repository()
    job = repository.find_job(job_id)
    if not job:
        return None
    document = repository.find_by_id(job["document_id"])
    return {
        "job": json_safe(job),
        "document": serialize_document(document) if document else None,
    }
