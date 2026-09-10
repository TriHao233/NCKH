from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.bootstrap import SCHEMA_VERSION

ACTIVE_DOCUMENT_JOB_STATUSES = {"QUEUED", "PROCESSING"}
RETRYABLE_DOCUMENT_JOB_STATUSES = {"FAILED", "ERROR", "STALE"}
RETRYABLE_DOCUMENT_JOB_TYPES = {"OCR", "CHUNK", "INDEX"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def object_id(value: str | ObjectId, field_name: str = "id") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except Exception as exc:
        raise ValueError(f"{field_name} không hợp lệ") from exc


def json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value if -(2**63) <= value < 2**63 else str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def compact_raw_extraction(value: dict | None) -> dict:
    """Keep Mongo audit metadata small; the full response lives in RAW_EXTRACTION_JSON."""
    raw = value or {}
    compact = {key: item for key, item in raw.items() if key not in {"candidates", "docling"}}
    if isinstance(raw.get("candidates"), list):
        compact["candidates"] = [
            {
                **{key: item for key, item in candidate.items() if key != "text"},
                "text_length": len(candidate.get("text") or ""),
            }
            for candidate in raw["candidates"]
            if isinstance(candidate, dict)
        ]
    if isinstance(raw.get("docling"), dict):
        compact["docling"] = {
            key: item
            for key, item in raw["docling"].items()
            if key not in {"text", "original_text", "raw_document", "structured_blocks"}
        }
        compact["docling"]["structured_block_count"] = len(raw["docling"].get("structured_blocks") or [])
    return json_safe(compact)


def serialize_document(document: dict) -> dict:
    return json_safe(
        {
            "id": document["_id"],
            "title": document["title"],
            "original_filename": document["original_filename"],
            "status": document["status"],
            "subject_id": document.get("subject_id"),
            "chapter_id": document.get("chapter_id"),
            "uploaded_by_user_id": document.get("uploaded_by_user_id"),
            "shared_with_user_ids": document.get("shared_with_user_ids") or [],
            "shared_scope": document.get("shared_scope") or "PRIVATE",
            "current_version": document.get("current_version", 1),
            "page_count": document.get("page_count"),
            "artifacts": document.get("artifacts") or [],
            "current_processing": document.get("current_processing") or {},
            "pending_processing": document.get("pending_processing") or {},
            "pipeline_summary": document.get("pipeline_summary") or {},
            "latest_error": document.get("latest_error"),
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
        }
    )


def serialize_document_job(job: dict) -> dict:
    status = job.get("status")
    job_type = job.get("job_type")
    return json_safe(
        {
            "id": job["_id"],
            "document_id": job.get("document_id"),
            "document_version": job.get("document_version"),
            "job_type": job.get("job_type"),
            "attempt_no": job.get("attempt_no"),
            "status": job.get("status"),
            "progress": job.get("progress"),
            "stats": job.get("stats"),
            "error": job.get("error"),
            "can_retry": status in RETRYABLE_DOCUMENT_JOB_STATUSES and job_type in RETRYABLE_DOCUMENT_JOB_TYPES,
            "can_cancel": status in ACTIVE_DOCUMENT_JOB_STATUSES,
            "queued_at": job.get("queued_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
        }
    )


def serialize_document_page(page: dict) -> dict:
    return json_safe(
        {
            "id": page["_id"],
            "document_id": page.get("document_id"),
            "document_version": page.get("document_version"),
            "ocr_job_id": page.get("ocr_job_id"),
            "page_number": page.get("page_number"),
            "unit_number": page.get("unit_number"),
            "source_location": page.get("source_location") or {},
            "raw_text": page.get("raw_text"),
            "cleaned_text": page.get("cleaned_text"),
            "content_blocks": page.get("content_blocks") or [],
            "assets": page.get("assets") or [],
            "raw_extraction": page.get("raw_extraction") or {},
            "quality": page.get("quality") or {},
            "formula_blocks": page.get("formula_blocks") or [],
            "created_at": page.get("created_at"),
        }
    )


class DocumentRepository(Protocol):
    def create(self, data: dict, uploaded_by_user_id: ObjectId | None) -> dict: ...

    def find_by_id(self, document_id: str | ObjectId) -> dict | None: ...

    def list(
        self,
        page: int,
        page_size: int,
        status: str | None,
        search: str | None,
        *,
        uploaded_by_user_id: ObjectId | None = None,
        visible_to_user_id: ObjectId | None = None,
    ) -> tuple[list[dict], int]: ...

    def update(self, document_id: str | ObjectId, fields: dict) -> dict | None: ...

    def archive(self, document_id: str | ObjectId) -> bool: ...

    def list_jobs(self, document_id: str | ObjectId, *, limit: int = 20) -> list[dict]: ...

    def list_pages(
        self,
        document_id: str | ObjectId,
        *,
        document_version: int | None = None,
        limit: int = 100,
    ) -> list[dict]: ...

    def update_page(
        self,
        document_id: str | ObjectId,
        page_id: str | ObjectId,
        *,
        document_version: int,
        cleaned_text: str,
    ) -> dict | None: ...

    def attach_processing_artifact(
        self,
        document_id: str | ObjectId,
        *,
        job_id: str | ObjectId,
        uri: str,
        size_bytes: int,
        sha256: str,
        artifact_type: str,
        mime_type: str,
    ) -> None: ...

    def create_job(self, document_id: str | ObjectId, job_type: str, config: dict | None = None) -> dict: ...

    def find_job(self, job_id: str | ObjectId) -> dict | None: ...

    def update_job(
        self,
        job_id: str | ObjectId,
        status: str,
        *,
        progress: int | None = None,
        stats: dict | None = None,
        error_message: str | None = None,
    ) -> dict | None: ...


class MongoDocumentRepository:
    def __init__(self, database: Database):
        self.db = database
        self.collection = database.documents

    def default_subject_id(self) -> ObjectId | None:
        subject = self.db.subjects.find_one({"subject_code": "CTDL", "is_active": True}, {"_id": 1})
        return subject["_id"] if subject else None

    def validate_subject_chapter(
        self,
        subject_id: ObjectId | None,
        chapter_id: ObjectId | None,
    ) -> None:
        if subject_id is None:
            if chapter_id is not None:
                raise ValueError("Chương phải thuộc một học phần")
            return
        subject = self.db.subjects.find_one(
            {"_id": subject_id, "is_active": True},
        )
        if not subject:
            raise ValueError("Học phần không tồn tại hoặc đã ngừng hoạt động")
        if chapter_id is None:
            return
        chapter_ids = {
            object_id(chapter.get("_id") or chapter.get("id"), "chapter_id")
            for chapter in subject.get("chapters", [])
            if chapter.get("_id") or chapter.get("id")
        }
        if chapter_id not in chapter_ids:
            raise ValueError("Chương không thuộc học phần đã chọn")

    def create(self, data: dict, uploaded_by_user_id: ObjectId | None) -> dict:
        now = utc_now()
        document_id = ObjectId()
        subject_id = object_id(data["subject_id"], "subject_id") if data.get("subject_id") else self.default_subject_id()
        chapter_id = object_id(data["chapter_id"], "chapter_id") if data.get("chapter_id") else None
        self.validate_subject_chapter(subject_id, chapter_id)
        artifacts = []
        if data.get("original_uri"):
            artifacts.append(
                {
                    "_id": ObjectId(),
                    "type": "ORIGINAL_PDF",
                    "document_version": 1,
                    "storage": {"provider": "LOCAL", "uri": data["original_uri"], "gridfs_file_id": None},
                    "mime_type": "application/pdf",
                    "size_bytes": data.get("size_bytes"),
                    "sha256": data.get("sha256"),
                    "is_current": True,
                    "created_at": now,
                }
            )
        record = {
            "_id": document_id,
            "schema_version": SCHEMA_VERSION,
            "subject_id": subject_id,
            "chapter_id": chapter_id,
            "uploaded_by_user_id": uploaded_by_user_id,
            "shared_with_user_ids": [],
            "shared_scope": "PRIVATE",
            "title": data["title"],
            "original_filename": data["original_filename"],
            "status": "UPLOADED",
            "current_version": 1,
            "page_count": None,
            "artifacts": artifacts,
            "current_processing": {
                "ocr_job_id": None,
                "chunk_set_id": None,
                "vector_collection_id": None,
            },
            "pending_processing": {},
            "pipeline_summary": {
                "ocr_status": "NOT_STARTED",
                "chunk_status": "NOT_STARTED",
                "index_status": "NOT_STARTED",
                "total_chunks": 0,
            },
            "latest_error": None,
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
        }
        self.collection.insert_one(record)
        return record

    def find_by_id(self, document_id: str | ObjectId) -> dict | None:
        return self.collection.find_one(
            {
                "_id": object_id(document_id, "document_id"),
                "schema_version": SCHEMA_VERSION,
                "archived_at": None,
            }
        )

    def list(
        self,
        page: int,
        page_size: int,
        status: str | None,
        search: str | None,
        *,
        uploaded_by_user_id: ObjectId | None = None,
        visible_to_user_id: ObjectId | None = None,
    ) -> tuple[list[dict], int]:
        query: dict = {"schema_version": SCHEMA_VERSION, "archived_at": None}
        if uploaded_by_user_id is not None:
            query["uploaded_by_user_id"] = uploaded_by_user_id
        filters = []
        if visible_to_user_id is not None:
            filters.append(
                {
                    "$or": [
                        {"uploaded_by_user_id": visible_to_user_id},
                        {"shared_with_user_ids": visible_to_user_id},
                        {"shared_scope": "SUBJECT"},
                    ]
                }
            )
        if status:
            query["status"] = status
        if search:
            filters.append(
                {
                    "$or": [
                        {"title": {"$regex": search, "$options": "i"}},
                        {"original_filename": {"$regex": search, "$options": "i"}},
                    ]
                }
            )
        if filters:
            query["$and"] = filters
        total = self.collection.count_documents(query)
        records = list(
            self.collection.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return records, total

    def update(self, document_id: str | ObjectId, fields: dict) -> dict | None:
        current = self.find_by_id(document_id)
        if not current:
            return None
        normalized = dict(fields)
        if "subject_id" in normalized:
            normalized["subject_id"] = object_id(normalized["subject_id"], "subject_id")
        if "chapter_id" in normalized:
            normalized["chapter_id"] = object_id(normalized["chapter_id"], "chapter_id")
        if "uploaded_by_user_id" in normalized and normalized["uploaded_by_user_id"] is not None:
            normalized["uploaded_by_user_id"] = object_id(
                normalized["uploaded_by_user_id"],
                "owner_user_id",
            )
        if "shared_with_user_ids" in normalized:
            normalized["shared_with_user_ids"] = [
                object_id(user_id, "shared_with_user_id")
                for user_id in normalized.get("shared_with_user_ids") or []
            ]
        self.validate_subject_chapter(
            normalized.get("subject_id", current.get("subject_id")),
            normalized.get("chapter_id", current.get("chapter_id")),
        )
        normalized["updated_at"] = utc_now()
        return self.collection.find_one_and_update(
            {
                "_id": object_id(document_id, "document_id"),
                "schema_version": SCHEMA_VERSION,
                "archived_at": None,
            },
            {"$set": normalized},
            return_document=ReturnDocument.AFTER,
        )

    def archive(self, document_id: str | ObjectId) -> bool:
        now = utc_now()
        result = self.collection.update_one(
            {
                "_id": object_id(document_id, "document_id"),
                "schema_version": SCHEMA_VERSION,
                "archived_at": None,
            },
            {"$set": {"status": "ARCHIVED", "archived_at": now, "updated_at": now}},
        )
        return result.matched_count == 1

    def list_jobs(self, document_id: str | ObjectId, *, limit: int = 20) -> list[dict]:
        document_oid = object_id(document_id, "document_id")
        return list(
            self.db.document_jobs.find({"document_id": document_oid})
            .sort("queued_at", -1)
            .limit(limit)
        )

    def list_pages(
        self,
        document_id: str | ObjectId,
        *,
        document_version: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query: dict = {"document_id": object_id(document_id, "document_id")}
        if document_version is not None:
            query["document_version"] = document_version
        return list(
            self.db.document_pages.find(query)
            .sort([("unit_number", 1), ("page_number", 1)])
            .limit(limit)
        )

    def update_page(
        self,
        document_id: str | ObjectId,
        page_id: str | ObjectId,
        *,
        document_version: int,
        cleaned_text: str,
    ) -> dict | None:
        document_oid = object_id(document_id, "document_id")
        now = utc_now()
        page = self.db.document_pages.find_one_and_update(
            {
                "_id": object_id(page_id, "page_id"),
                "document_id": document_oid,
                "document_version": document_version,
            },
            {
                "$set": {
                    "cleaned_text": cleaned_text,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if page:
            self.collection.update_one(
                {"_id": document_oid, "archived_at": None},
                {"$set": {"updated_at": now}},
            )
        return page

    def attach_original_artifact(
        self,
        document_id: str | ObjectId,
        *,
        uri: str,
        size_bytes: int,
        sha256: str,
        artifact_type: str = "ORIGINAL_PDF",
        mime_type: str = "application/pdf",
    ) -> None:
        now = utc_now()
        self.collection.update_one(
            {"_id": object_id(document_id, "document_id")},
            {
                "$push": {
                    "artifacts": {
                        "_id": ObjectId(),
                        "type": artifact_type,
                        "document_version": 1,
                        "storage": {
                            "provider": "LOCAL",
                            "uri": uri,
                            "gridfs_file_id": None,
                        },
                        "mime_type": mime_type,
                        "size_bytes": size_bytes,
                        "sha256": sha256,
                        "is_current": True,
                        "created_at": now,
                    }
                },
                "$set": {"updated_at": now},
            },
        )

    def attach_processing_artifact(
        self,
        document_id: str | ObjectId,
        *,
        job_id: str | ObjectId,
        uri: str,
        size_bytes: int,
        sha256: str,
        artifact_type: str,
        mime_type: str,
    ) -> None:
        document = self.find_by_id(document_id)
        job = self.find_job(job_id)
        if not document or not job or job.get("document_id") != document["_id"]:
            raise ValueError("Processing artifact không thuộc tài liệu/job")
        now = utc_now()
        self.collection.update_one(
            {"_id": document["_id"], "archived_at": None},
            {
                "$push": {
                    "artifacts": {
                        "_id": ObjectId(),
                        "type": artifact_type,
                        "document_version": job["document_version"],
                        "job_id": job["_id"],
                        "storage": {"provider": "LOCAL", "uri": uri, "gridfs_file_id": None},
                        "mime_type": mime_type,
                        "size_bytes": size_bytes,
                        "sha256": sha256,
                        "is_current": True,
                        "created_at": now,
                    }
                },
                "$set": {"updated_at": now},
            },
        )

    def create_job(self, document_id: str | ObjectId, job_type: str, config: dict | None = None) -> dict:
        document = self.find_by_id(document_id)
        if not document:
            raise ValueError("Không tìm thấy tài liệu")
        normalized_type = job_type.upper()
        latest = self.db.document_jobs.find_one(
            {
                "document_id": document["_id"],
                "document_version": document["current_version"],
                "job_type": normalized_type,
            },
            sort=[("attempt_no", -1)],
        )
        now = utc_now()
        current_processing = document.get("current_processing") or {}
        active_pointer = (
            current_processing.get("ocr_job_id")
            if normalized_type == "OCR"
            else current_processing.get("chunk_set_id") if normalized_type == "CHUNK" else None
        )
        record = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "document_id": document["_id"],
            "document_version": document["current_version"],
            "job_type": normalized_type,
            "attempt_no": int(latest.get("attempt_no", 0)) + 1 if latest else 1,
            "status": "QUEUED",
            "config": config or {},
            "progress": 0,
            "stats": None,
            "error": None,
            "queued_at": now,
            "started_at": None,
            "finished_at": None,
            "preserves_active_pipeline": bool(active_pointer),
            "previous_document_state": {
                "status": document.get("status"),
                "pipeline_status": (document.get("pipeline_summary") or {}).get(
                    normalized_type.lower() + "_status"
                ),
            },
        }
        self.db.document_jobs.insert_one(record)
        document_fields = {
            f"pipeline_attempts.{normalized_type.lower()}.status": "QUEUED",
            f"pipeline_attempts.{normalized_type.lower()}.job_id": record["_id"],
            "latest_error": None,
            "updated_at": now,
        }
        if not active_pointer:
            document_fields.update(
                {
                    "status": "PROCESSING",
                    f"pipeline_summary.{normalized_type.lower()}_status": "QUEUED",
                }
            )
        self.collection.update_one(
            {"_id": document["_id"]},
            {"$set": document_fields},
        )
        return record

    def find_job(self, job_id: str | ObjectId) -> dict | None:
        return self.db.document_jobs.find_one({"_id": object_id(job_id, "job_id")})

    def update_job(
        self,
        job_id: str | ObjectId,
        status: str,
        *,
        progress: int | None = None,
        stats: dict | None = None,
        error_message: str | None = None,
    ) -> dict | None:
        job = self.find_job(job_id)
        if not job:
            return None
        now = utc_now()
        normalized = status.upper()
        if job.get("status") == "CANCELLED" and normalized != "CANCELLED":
            return job
        fields: dict = {"status": normalized}
        if progress is not None:
            fields["progress"] = max(0, min(100, progress))
        if stats is not None:
            fields["stats"] = stats
        if error_message is not None:
            fields["error"] = {"message": error_message, "at": now}
        if normalized == "PROCESSING" and not job.get("started_at"):
            fields["started_at"] = now
        if normalized in {"COMPLETED", "FAILED", "CANCELLED"}:
            fields["finished_at"] = now
            if normalized == "COMPLETED":
                fields["progress"] = 100
        self.db.document_jobs.update_one({"_id": job["_id"]}, {"$set": fields})
        job_type_key = job["job_type"].lower()
        preserves_active = bool(job.get("preserves_active_pipeline"))
        document_fields: dict = {
            f"pipeline_attempts.{job_type_key}.status": normalized,
            f"pipeline_attempts.{job_type_key}.job_id": job["_id"],
            "updated_at": now,
        }
        if not preserves_active:
            document_fields[f"pipeline_summary.{job_type_key}_status"] = normalized
        if normalized in {"FAILED", "CANCELLED"}:
            message = error_message or ("Job đã bị hủy" if normalized == "CANCELLED" else None)
            if preserves_active:
                previous = job.get("previous_document_state") or {}
                document_fields["status"] = previous.get("status") or "READY"
                if previous.get("pipeline_status"):
                    document_fields[f"pipeline_summary.{job_type_key}_status"] = previous["pipeline_status"]
            else:
                document_fields["status"] = "FAILED"
            document_fields["latest_error"] = {
                "job_id": job["_id"],
                "job_type": job["job_type"],
                "message": message,
                "at": now,
            }
        if normalized == "COMPLETED" and job.get("job_type") == "OCR":
            document = self.find_by_id(job["document_id"]) or {}
            if (document.get("current_processing") or {}).get("chunk_set_id"):
                document_fields["pending_processing.ocr_job_id"] = job["_id"]
            else:
                document_fields["current_processing.ocr_job_id"] = job["_id"]
        if normalized == "CANCELLED" and job.get("job_type") == "CHUNK":
            chunk_sets = list(self.db.chunk_sets.find({"chunk_job_id": job["_id"]}, {"_id": 1}))
            chunk_set_ids = [chunk_set["_id"] for chunk_set in chunk_sets]
            self.db.chunk_sets.update_many(
                {"chunk_job_id": job["_id"]},
                {
                    "$set": {
                        "status": "CANCELLED",
                        "error": fields.get("error"),
                        "completed_at": now,
                    }
                },
            )
            if chunk_set_ids:
                self.db.chunk_embeddings.update_many(
                    {"chunk_set_id": {"$in": chunk_set_ids}, "status": "PENDING"},
                    {
                        "$set": {
                            "status": "CANCELLED",
                            "error": fields.get("error"),
                            "updated_at": now,
                        }
                    },
                )
        self.collection.update_one(
            {"_id": job["document_id"], "archived_at": None},
            {"$set": document_fields},
        )
        return self.find_job(job_id)

    def save_pages(self, document_id: str, ocr_job_id: str, pages: list[dict]) -> int:
        document_oid = object_id(document_id, "document_id")
        job = self.find_job(ocr_job_id)
        if not job or job["document_id"] != document_oid or job["job_type"] != "OCR":
            raise ValueError("OCR job không thuộc tài liệu")
        now = utc_now()
        records = [
            {
                "schema_version": SCHEMA_VERSION,
                "document_id": document_oid,
                "document_version": job["document_version"],
                "ocr_job_id": job["_id"],
                "unit_number": int(page.get("unit_number") or index),
                "page_number": int(page["page_number"]) if page.get("page_number") is not None else None,
                "source_location": json_safe(page.get("source_location") or {}),
                "raw_text": page.get("original_text") or page.get("text", ""),
                "cleaned_text": page.get("text", ""),
                "content_blocks": json_safe(page.get("content_blocks") or []),
                "assets": json_safe(page.get("assets") or []),
                "raw_extraction": compact_raw_extraction(page.get("raw_extraction")),
                "quality": json_safe(page.get("quality") or {}),
                "formula_blocks": json_safe(page.get("formula_blocks", [])),
                "created_at": now,
            }
            for index, page in enumerate(pages, start=1)
        ]
        self.db.document_pages.delete_many(
            {"document_id": document_oid, "ocr_job_id": job["_id"]}
        )
        if records:
            self.db.document_pages.insert_many(records, ordered=True)
        self.collection.update_one(
            {"_id": document_oid, "archived_at": None},
            {"$set": {"page_count": len(records), "updated_at": now}},
        )
        return len(records)
