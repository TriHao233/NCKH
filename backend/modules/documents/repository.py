from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.bootstrap import SCHEMA_VERSION
from core.config import settings
from core.database import mongo_transaction

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
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


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
            "worker_id": job.get("worker_id"),
            "heartbeat_at": job.get("heartbeat_at"),
            "lease_expires_at": job.get("lease_expires_at"),
            "checkpoint": job.get("checkpoint"),
        }
    )


def serialize_document_page(page: dict) -> dict:
    return json_safe(
        {
            "id": page["_id"],
            "document_id": page.get("document_id"),
            "document_version": page.get("document_version"),
            "ocr_job_id": page.get("ocr_job_id"),
            "processing_revision_id": page.get("processing_revision_id"),
            "revision_no": page.get("revision_no"),
            "page_number": page.get("page_number"),
            "raw_text": page.get("raw_text"),
            "cleaned_text": page.get("cleaned_text"),
            "formula_blocks": page.get("formula_blocks") or [],
            "layout_blocks": page.get("layout_blocks") or [],
            "visual_blocks": page.get("visual_blocks") or [],
            "extraction_method": page.get("extraction_method"),
            "quality_flags": page.get("quality_flags") or [],
            "corrected_from_page_id": page.get("corrected_from_page_id"),
            "corrected_by_user_id": page.get("corrected_by_user_id"),
            "created_at": page.get("created_at"),
            "updated_at": page.get("updated_at"),
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
        visible_subject_ids: tuple[ObjectId, ...] = (),
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
        corrected_by_user_id: ObjectId | None = None,
    ) -> dict | None: ...

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
        expected_worker_id: str | None = None,
        expected_fencing_token: int | None = None,
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
                "processing_revision_id": None,
                "pending_ocr_job_id": None,
                "pending_processing_revision_id": None,
                "chunk_set_id": None,
                "vector_collection_id": None,
            },
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
        visible_subject_ids: tuple[ObjectId, ...] = (),
    ) -> tuple[list[dict], int]:
        query: dict = {"schema_version": SCHEMA_VERSION, "archived_at": None}
        if uploaded_by_user_id is not None:
            query["uploaded_by_user_id"] = uploaded_by_user_id
        filters = []
        if visible_to_user_id is not None:
            subject_scope = {
                "shared_scope": "SUBJECT",
                "subject_id": {"$in": list(visible_subject_ids)},
            }
            filters.append(
                {
                    "$or": [
                        {"uploaded_by_user_id": visible_to_user_id},
                        {"shared_with_user_ids": visible_to_user_id},
                        subject_scope,
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
        document_oid = object_id(document_id, "document_id")
        query: dict = {"document_id": document_oid}
        document = self.find_by_id(document_oid)
        active_revision_id = (document.get("current_processing") or {}).get(
            "processing_revision_id"
        ) if document else None
        active_ocr_job_id = (document.get("current_processing") or {}).get(
            "ocr_job_id"
        ) if document else None
        if active_revision_id:
            query["processing_revision_id"] = active_revision_id
        elif active_ocr_job_id:
            query["ocr_job_id"] = active_ocr_job_id
        if document_version is not None:
            query["document_version"] = document_version
        return list(
            self.db.document_pages.find(query)
            .sort("page_number", 1)
            .limit(limit)
        )

    def update_page(
        self,
        document_id: str | ObjectId,
        page_id: str | ObjectId,
        *,
        document_version: int,
        cleaned_text: str,
        corrected_by_user_id: ObjectId | None = None,
    ) -> dict | None:
        document_oid = object_id(document_id, "document_id")
        source_page_id = object_id(page_id, "page_id")
        now = utc_now()
        document = self.find_by_id(document_oid)
        if not document:
            return None
        active_revision_id = (document.get("current_processing") or {}).get(
            "processing_revision_id"
        )
        active_ocr_job_id = (document.get("current_processing") or {}).get("ocr_job_id")
        page_query = {
            "_id": source_page_id,
            "document_id": document_oid,
            "document_version": document_version,
        }
        if active_revision_id:
            page_query["processing_revision_id"] = active_revision_id
        elif active_ocr_job_id:
            page_query["ocr_job_id"] = active_ocr_job_id
        source_page = self.db.document_pages.find_one(page_query)
        if not source_page:
            return None

        latest_revision = self.db.document_processing_revisions.find_one(
            {"document_id": document_oid}, sort=[("revision_no", -1)]
        )
        revision_no = int((latest_revision or {}).get("revision_no", 0)) + 1
        correction_job_id = ObjectId()
        revision_id = ObjectId()
        pages = list(
            self.db.document_pages.find(
                {
                    "document_id": document_oid,
                    **(
                        {"processing_revision_id": active_revision_id}
                        if active_revision_id
                        else {"ocr_job_id": active_ocr_job_id}
                    ),
                }
            ).sort("page_number", 1)
        )
        copied_pages = []
        corrected_page = None
        for original in pages:
            copied = {
                **original,
                "_id": ObjectId(),
                "ocr_job_id": correction_job_id,
                "processing_revision_id": revision_id,
                "revision_no": revision_no,
                "created_at": now,
                "updated_at": now,
            }
            if original["_id"] == source_page_id:
                copied["cleaned_text"] = cleaned_text
                copied["corrected_from_page_id"] = original["_id"]
                copied["corrected_by_user_id"] = corrected_by_user_id
                corrected_page = copied
            copied_pages.append(copied)
        page_set_hash = self._page_set_hash(copied_pages)
        correction_job = {
            "_id": correction_job_id,
            "schema_version": SCHEMA_VERSION,
            "document_id": document_oid,
            "document_version": document_version,
            "processing_revision_id": revision_id,
            "job_type": "CORRECTION",
            "attempt_no": revision_no,
            "status": "COMPLETED",
            "config": {"source_page_id": source_page_id},
            "progress": 100,
            "stats": {"page_count": len(copied_pages), "page_set_hash": page_set_hash},
            "error": None,
            "queued_at": now,
            "started_at": now,
            "finished_at": now,
        }
        revision = {
            "_id": revision_id,
            "schema_version": SCHEMA_VERSION,
            "document_id": document_oid,
            "document_version": document_version,
            "revision_no": revision_no,
            "source_job_id": correction_job_id,
            "parent_revision_id": active_revision_id,
            "kind": "CORRECTION",
            "status": "ACTIVE",
            "page_count": len(copied_pages),
            "page_set_hash": page_set_hash,
            "manifest": {
                "corrected_page_id": source_page_id,
                "corrected_by_user_id": corrected_by_user_id,
            },
            "created_at": now,
            "completed_at": now,
        }
        with mongo_transaction() as session:
            self.db.document_jobs.insert_one(correction_job, session=session)
            self.db.document_processing_revisions.update_many(
                {"document_id": document_oid, "status": "ACTIVE"},
                {"$set": {"status": "SUPERSEDED", "superseded_at": now}},
                session=session,
            )
            self.db.document_processing_revisions.insert_one(revision, session=session)
            if copied_pages:
                self.db.document_pages.insert_many(copied_pages, ordered=True, session=session)
            activation_filter: dict = {"_id": document_oid, "archived_at": None}
            if active_revision_id:
                activation_filter["current_processing.processing_revision_id"] = active_revision_id
            elif active_ocr_job_id:
                activation_filter["current_processing.ocr_job_id"] = active_ocr_job_id
            activation = self.collection.update_one(
                activation_filter,
                {
                    "$set": {
                        "current_processing.ocr_job_id": correction_job_id,
                        "current_processing.processing_revision_id": revision_id,
                        "current_processing.chunk_set_id": None,
                        "current_processing.vector_collection_id": None,
                        "pipeline_summary.ocr_status": "COMPLETED",
                        "pipeline_summary.chunk_status": "NOT_STARTED",
                        "pipeline_summary.index_status": "NOT_STARTED",
                        "status": "PROCESSING",
                        "latest_error": None,
                        "updated_at": now,
                    }
                },
                session=session,
            )
            if not activation.matched_count:
                raise RuntimeError("DOCUMENT_PROCESSING_REVISION_CONFLICT")
        return corrected_page

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
        processing_revision_id = ObjectId() if normalized_type == "OCR" else None
        latest_revision = self.db.document_processing_revisions.find_one(
            {"document_id": document["_id"]}, sort=[("revision_no", -1)]
        ) if normalized_type == "OCR" else None
        revision_no = int((latest_revision or {}).get("revision_no", 0)) + 1
        record = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "document_id": document["_id"],
            "document_version": document["current_version"],
            "job_type": normalized_type,
            "processing_revision_id": processing_revision_id,
            "attempt_no": int(latest.get("attempt_no", 0)) + 1 if latest else 1,
            "status": "QUEUED",
            "config": config or {},
            "progress": 0,
            "stats": None,
            "error": None,
            "queued_at": now,
            "started_at": None,
            "finished_at": None,
            "worker_id": None,
            "lease_expires_at": None,
            "heartbeat_at": None,
            "fencing_token": 0,
            "run_attempt": 0,
        }
        self.db.document_jobs.insert_one(record)
        if normalized_type == "OCR":
            self.db.document_processing_revisions.insert_one(
                {
                    "_id": processing_revision_id,
                    "schema_version": SCHEMA_VERSION,
                    "document_id": document["_id"],
                    "document_version": document["current_version"],
                    "revision_no": revision_no,
                    "source_job_id": record["_id"],
                    "parent_revision_id": (document.get("current_processing") or {}).get(
                        "processing_revision_id"
                    ),
                    "kind": "OCR",
                    "status": "QUEUED",
                    "page_count": 0,
                    "page_set_hash": None,
                    "manifest": {},
                    "created_at": now,
                    "completed_at": None,
                }
            )
        self.collection.update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    "status": "PROCESSING",
                    f"pipeline_summary.{normalized_type.lower()}_status": "QUEUED",
                    "latest_error": None,
                    "updated_at": now,
                    **(
                        {
                            "current_processing.pending_ocr_job_id": record["_id"],
                            "current_processing.pending_processing_revision_id": processing_revision_id,
                        }
                        if normalized_type == "OCR"
                        else (
                            {"current_processing.pending_chunk_job_id": record["_id"]}
                            if normalized_type == "CHUNK"
                            else (
                                {"current_processing.pending_index_job_id": record["_id"]}
                                if normalized_type == "INDEX"
                                else {}
                            )
                        )
                    ),
                }
            },
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
        expected_worker_id: str | None = None,
        expected_fencing_token: int | None = None,
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
        job_filter: dict = {"_id": job["_id"]}
        if expected_worker_id is not None:
            job_filter["worker_id"] = expected_worker_id
        if expected_fencing_token is not None:
            job_filter["fencing_token"] = expected_fencing_token
        update_result = self.db.document_jobs.update_one(job_filter, {"$set": fields})
        if not update_result.matched_count:
            return None
        document_fields: dict = {
            f"pipeline_summary.{job['job_type'].lower()}_status": normalized,
            "updated_at": now,
        }
        if normalized in {"FAILED", "CANCELLED"}:
            message = error_message or ("Job đã bị hủy" if normalized == "CANCELLED" else None)
            document_fields["status"] = "FAILED"
            document_fields["latest_error"] = {
                "job_id": job["_id"],
                "job_type": job["job_type"],
                "message": message,
                "at": now,
            }
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
        pending_field = {
            "OCR": "current_processing.pending_ocr_job_id",
            "CHUNK": "current_processing.pending_chunk_job_id",
            "INDEX": "current_processing.pending_index_job_id",
        }.get(job.get("job_type"))
        document_filter: dict = {"_id": job["document_id"], "archived_at": None}
        if pending_field:
            document_filter["$or"] = [
                {pending_field: job["_id"]},
                {pending_field: {"$exists": False}},
            ]
        self.collection.update_one(
            document_filter,
            {"$set": document_fields},
        )
        if normalized == "CANCELLED" and job.get("job_type") == "OCR":
            revision_id = job.get("processing_revision_id")
            if revision_id:
                self.db.document_processing_revisions.update_one(
                    {"_id": revision_id, "status": {"$in": ["QUEUED", "PROCESSING"]}},
                    {
                        "$set": {
                            "status": "CANCELLED",
                            "completed_at": now,
                            "error": fields.get("error"),
                            "updated_at": now,
                        }
                    },
                )
            self.collection.update_one(
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
        return self.find_job(job_id)

    def claim_job(self, job_id: str | ObjectId, worker_id: str) -> dict | None:
        now = utc_now()
        lease_expires_at = now + timedelta(seconds=max(settings.job_lease_seconds, 1))
        return self.db.document_jobs.find_one_and_update(
            {
                "_id": object_id(job_id, "job_id"),
                "$or": [
                    {"status": "QUEUED"},
                    {"status": "PROCESSING", "lease_expires_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "status": "PROCESSING",
                    "worker_id": worker_id,
                    "started_at": now,
                    "heartbeat_at": now,
                    "lease_expires_at": lease_expires_at,
                    "updated_at": now,
                },
                "$inc": {"fencing_token": 1, "run_attempt": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

    def heartbeat_job(self, job_id: str | ObjectId, worker_id: str, fencing_token: int) -> bool:
        now = utc_now()
        result = self.db.document_jobs.update_one(
            {
                "_id": object_id(job_id, "job_id"),
                "status": "PROCESSING",
                "worker_id": worker_id,
                "fencing_token": fencing_token,
            },
            {
                "$set": {
                    "heartbeat_at": now,
                    "lease_expires_at": now + timedelta(seconds=max(settings.job_lease_seconds, 1)),
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def update_checkpoint(
        self,
        job_id: str | ObjectId,
        worker_id: str,
        fencing_token: int,
        checkpoint: dict,
        *,
        progress: int | None = None,
    ) -> bool:
        fields: dict = {"checkpoint": checkpoint, "updated_at": utc_now()}
        if progress is not None:
            fields["progress"] = max(0, min(99, progress))
        result = self.db.document_jobs.update_one(
            {
                "_id": object_id(job_id, "job_id"),
                "status": "PROCESSING",
                "worker_id": worker_id,
                "fencing_token": fencing_token,
            },
            {"$set": fields},
        )
        return result.matched_count == 1

    def save_pages(self, document_id: str, ocr_job_id: str, pages: list[dict]) -> int:
        document_oid = object_id(document_id, "document_id")
        job = self.find_job(ocr_job_id)
        if not job or job["document_id"] != document_oid or job["job_type"] != "OCR":
            raise ValueError("OCR job không thuộc tài liệu")
        now = utc_now()
        revision_id = job.get("processing_revision_id") or job["_id"]
        revision = self.db.document_processing_revisions.find_one({"_id": revision_id}) or {}
        revision_no = int(revision.get("revision_no", job.get("attempt_no", 1)))
        records = [
            {
                "schema_version": SCHEMA_VERSION,
                "document_id": document_oid,
                "document_version": job["document_version"],
                "ocr_job_id": job["_id"],
                "processing_revision_id": revision_id,
                "revision_no": revision_no,
                "page_number": int(page["page_number"]),
                "raw_text": (
                    page.get("original_text")
                    if page.get("original_text") is not None
                    else page.get("text", "")
                ),
                "cleaned_text": page.get("text", ""),
                "formula_blocks": page.get("formula_blocks", []),
                "layout_blocks": page.get("layout_blocks", []),
                "visual_blocks": page.get("visual_blocks", []),
                "extraction_method": page.get("extraction_method", "OCR"),
                "quality_flags": page.get("quality_flags", []),
                "created_at": now,
                "updated_at": now,
            }
            for page in pages
        ]
        # A retry may rewrite its own unfinished page set, but never deletes a
        # previous revision that questions or chunks can still reference.
        self.db.document_pages.delete_many({"processing_revision_id": revision_id})
        if records:
            self.db.document_pages.insert_many(records, ordered=True)
        page_set_hash = self._page_set_hash(records)
        manifest = {
            "page_set_hash": page_set_hash,
            "page_count": len(records),
            "methods": sorted({record["extraction_method"] for record in records}),
        }
        output_uri = (job.get("config") or {}).get("output_path")
        if output_uri and Path(output_uri).is_file():
            manifest["markdown"] = {
                "uri": output_uri,
                "sha256": hashlib.sha256(Path(output_uri).read_bytes()).hexdigest(),
            }
        self.db.document_processing_revisions.update_one(
            {"_id": revision_id},
            {
                "$set": {
                    "page_count": len(records),
                    "page_set_hash": page_set_hash,
                    "manifest": manifest,
                    "updated_at": now,
                }
            },
        )
        self.collection.update_one(
            {"_id": document_oid, "archived_at": None},
            {"$set": {"page_count": len(records), "updated_at": now}},
        )
        return len(records)

    @staticmethod
    def _page_set_hash(pages: list[dict]) -> str:
        payload = [
            {
                "page_number": int(page.get("page_number", 0)),
                "raw_text": page.get("raw_text", ""),
                "cleaned_text": page.get("cleaned_text", ""),
                "formula_blocks": page.get("formula_blocks") or [],
                "extraction_method": page.get("extraction_method"),
            }
            for page in pages
        ]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
