from core.database import get_database, mongo_transaction
from modules.documents.repository import utc_now
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


def create_ocr_job(document_id: str, config: dict | None = None) -> str:
    job = _repository().create_job(document_id, "OCR", config=config)
    return str(job["_id"])


def update_document_status(
    document_id: str,
    job_id: str,
    status: str,
    stats: dict | None = None,
    error_message: str | None = None,
    worker_id: str | None = None,
    fencing_token: int | None = None,
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
        expected_worker_id=worker_id,
        expected_fencing_token=fencing_token,
    )
    job = repository.find_job(job_id)
    if worker_id is not None and (
        not job
        or job.get("worker_id") != worker_id
        or job.get("fencing_token") != fencing_token
    ):
        return
    if not job or job.get("status") != normalized:
        return
    if job and job.get("processing_revision_id"):
        revision_id = job["processing_revision_id"]
        now = utc_now()
        if normalized == "PROCESSING":
            get_database().document_processing_revisions.update_one(
                {"_id": revision_id, "status": {"$in": ["QUEUED", "PROCESSING"]}},
                {"$set": {"status": "PROCESSING", "updated_at": now}},
            )
        elif normalized == "COMPLETED":
            with mongo_transaction() as session:
                activation = get_database().documents.update_one(
                    {
                        "_id": job["document_id"],
                        "archived_at": None,
                        "current_processing.pending_ocr_job_id": job["_id"],
                    },
                    {
                        "$set": {
                            "current_processing.ocr_job_id": job["_id"],
                            "current_processing.processing_revision_id": revision_id,
                            "current_processing.pending_ocr_job_id": None,
                            "current_processing.pending_processing_revision_id": None,
                            "current_processing.chunk_set_id": None,
                            "current_processing.vector_collection_id": None,
                            "current_processing.index_manifest_id": None,
                            "updated_at": now,
                        }
                    },
                    session=session,
                )
                if not activation.matched_count:
                    raise RuntimeError("DOCUMENT_PROCESSING_REVISION_STALE")
                get_database().document_processing_revisions.update_many(
                    {
                        "document_id": job["document_id"],
                        "_id": {"$ne": revision_id},
                        "status": "ACTIVE",
                    },
                    {"$set": {"status": "SUPERSEDED", "superseded_at": now}},
                    session=session,
                )
                get_database().document_processing_revisions.update_one(
                    {"_id": revision_id},
                    {"$set": {"status": "ACTIVE", "completed_at": now, "updated_at": now}},
                    session=session,
                )
        elif normalized in {"FAILED", "CANCELLED"}:
            get_database().document_processing_revisions.update_one(
                {"_id": revision_id},
                {
                    "$set": {
                        "status": normalized,
                        "error": {"message": error_message, "at": now},
                        "completed_at": now,
                        "updated_at": now,
                    }
                },
            )
            get_database().documents.update_one(
                {
                    "_id": job["document_id"],
                    "current_processing.pending_ocr_job_id": job["_id"],
                },
                {
                    "$set": {
                        "current_processing.pending_ocr_job_id": None,
                        "current_processing.pending_processing_revision_id": None,
                    }
                },
            )
    if normalized == "COMPLETED":
        document = repository.find_by_id(document_id)
        if document:
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


def save_document_pages(
    document_id: str,
    job_id: str,
    pages: list,
    *,
    worker_id: str | None = None,
    fencing_token: int | None = None,
):
    return _repository().save_pages(
        document_id,
        job_id,
        pages,
        worker_id=worker_id,
        fencing_token=fencing_token,
    )


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
