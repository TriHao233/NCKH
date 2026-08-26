from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import BackgroundTasks
from pymongo import ReturnDocument

from core.audit import record_audit_event
from core.config import settings
from core.dependencies import CurrentUser
from modules.admin.job_metrics import collect_job_metrics
from modules.documents.repository import MongoDocumentRepository, RETRYABLE_DOCUMENT_JOB_TYPES
from modules.documents.service import DocumentService
from modules.generation.mongodb import create_generation_job, get_generation_job
from modules.questions.workflow_service import QuestionWorkflowService

ACTIVE_STATUSES = {"QUEUED", "PROCESSING", "queued", "processing"}
RETRYABLE_STATUSES = {"FAILED", "ERROR", "STALE", "failed"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def _job_time(job: dict) -> datetime | None:
    for key in ("updated_at", "finished_at", "started_at", "queued_at", "created_at"):
        value = job.get(key)
        if isinstance(value, datetime):
            return value
    return None


def _seconds_since(value: datetime | None) -> int | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return max(0, int((utc_now() - value).total_seconds()))


def _as_utc_datetime(value: datetime | str | None, field_name: str = "date") -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{field_name} không hợp lệ") from exc
    else:
        raise ValueError(f"{field_name} không hợp lệ")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _error_message(error: Any) -> str | None:
    if isinstance(error, dict):
        return error.get("message") or error.get("detail")
    if error:
        return str(error)
    return None


def _parse_object_id(value: str | ObjectId, field_name: str = "id") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"{field_name} không hợp lệ") from exc


def _generation_status_filter(status: str | None) -> str | dict | None:
    if not status:
        return None
    normalized = status.lower()
    if normalized == "active":
        return {"$in": ["queued", "processing"]}
    if normalized in {"retryable", "attention"}:
        return {"$in": ["failed"]}
    return normalized


def _uppercase_status_filter(status: str | None) -> str | dict | None:
    if not status:
        return None
    normalized = status.lower()
    if normalized == "active":
        return {"$in": ["QUEUED", "PROCESSING"]}
    if normalized in {"retryable", "attention"}:
        return {"$in": ["FAILED", "ERROR", "STALE"]}
    return status.upper()


class AdminJobService:
    def __init__(self, database):
        self.db = database

    def list_jobs(
        self,
        *,
        page: int,
        page_size: int,
        job_kind: str | None = None,
        status: str | None = None,
        user_id: str | None = None,
        stale_only: bool = False,
        search: str | None = None,
        date_from: datetime | str | None = None,
        date_to: datetime | str | None = None,
    ) -> dict:
        jobs = []
        requested_kinds = {job_kind.lower()} if job_kind else {"generation", "evaluation", "document"}
        user_oid = _parse_object_id(user_id, "user_id") if user_id else None
        date_from_utc = _as_utc_datetime(date_from, "date_from")
        date_to_utc = _as_utc_datetime(date_to, "date_to")
        if date_from_utc and date_to_utc and date_from_utc > date_to_utc:
            raise ValueError("Khoảng thời gian job không hợp lệ")
        scan_limit = max(page * page_size, page_size)
        if search or stale_only:
            scan_limit = max(scan_limit, 500)
        scanned_counts: list[int] = []
        exact_total = None
        if not search and not stale_only:
            exact_total = self._count_jobs(
                requested_kinds,
                status,
                user_oid,
                date_from_utc,
                date_to_utc,
            )

        if "generation" in requested_kinds:
            batch = self._generation_jobs(status, user_oid, date_from_utc, date_to_utc, scan_limit)
            scanned_counts.append(len(batch))
            jobs.extend(batch)
        if "evaluation" in requested_kinds:
            batch = self._evaluation_jobs(status, user_oid, date_from_utc, date_to_utc, scan_limit)
            scanned_counts.append(len(batch))
            jobs.extend(batch)
        if "document" in requested_kinds:
            batch = self._document_jobs(status, user_oid, date_from_utc, date_to_utc, scan_limit)
            scanned_counts.append(len(batch))
            jobs.extend(batch)


        # Enrich user names
        user_ids = []
        for job in jobs:
            actor = job.get('actor_user_id')
            if actor:
                user_ids.append(_parse_object_id(actor))
        if user_ids:
            users_map = {
                str(u['_id']): u.get('display_name') or str(u['_id'])
                for u in self.db.users.find({'_id': {'$in': user_ids}}, {'display_name': 1})
            }
            for job in jobs:
                actor = str(job.get('actor_user_id', ''))
                if actor and actor in users_map:
                    job['actor_user_name'] = users_map[actor]

        # Enrich entity labels (subjects)
        document_ids = []
        question_ids = []
        for job in jobs:
            entity = job.get('entity', {})
            if entity.get('type') == 'document' and entity.get('id'):
                try:
                    document_ids.append(_parse_object_id(entity['id']))
                except:
                    pass
            elif entity.get('type') == 'question' and entity.get('id'):
                try:
                    question_ids.append(_parse_object_id(entity['id']))
                except:
                    pass

        subject_ids = set()
        doc_subject_map = {}
        if document_ids:
            for doc in self.db.documents.find({"_id": {"$in": document_ids}}, {"subject_id": 1}):
                if doc.get("subject_id"):
                    subject_ids.add(doc["subject_id"])
                    doc_subject_map[str(doc["_id"])] = doc["subject_id"]

        question_subject_map = {}
        if question_ids:
            for qv in self.db.question_versions.find({"question_id": {"$in": question_ids}}, {"question_id": 1, "classification.subject.id": 1}):
                subj_id = (qv.get("classification") or {}).get("subject", {}).get("id")
                if subj_id:
                    subject_ids.add(subj_id)
                    question_subject_map[str(qv["question_id"])] = subj_id

        if subject_ids:
            subjects_map = {
                str(s["_id"]): s.get("subject_name") or s.get("subject_code") or str(s["_id"])
                for s in self.db.subjects.find({"_id": {"$in": list(subject_ids)}}, {"subject_name": 1, "subject_code": 1})
            }
            for job in jobs:
                entity = job.get('entity', {})
                subj_id = None
                if entity.get('type') == 'document' and entity.get('id'):
                    subj_id = doc_subject_map.get(str(entity['id']))
                elif entity.get('type') == 'question' and entity.get('id'):
                    subj_id = question_subject_map.get(str(entity['id']))
                if subj_id and str(subj_id) in subjects_map:
                    entity['label'] = subjects_map[str(subj_id)]

        if stale_only:
            jobs = [job for job in jobs if job["is_long_running"]]
        if search:
            term = search.strip().lower()
            jobs = [job for job in jobs if self._matches_search(job, term)]
        if date_from_utc or date_to_utc:
            jobs = [
                job for job in jobs
                if self._matches_date_range(job, date_from_utc, date_to_utc)
            ]

        jobs.sort(key=lambda item: item.get("sort_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        filtered_total = len(jobs)
        total = exact_total if exact_total is not None else filtered_total
        start = (page - 1) * page_size
        items = [self._public_item(job) for job in jobs[start:start + page_size]]
        scan_truncated = any(count >= scan_limit for count in scanned_counts)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "summary": self._summary(jobs),
            "scan_truncated": scan_truncated,
            "total_is_estimate": exact_total is None and scan_truncated,
            "summary_is_estimate": scan_truncated,
        }

    def operational_metrics(self) -> dict:
        return collect_job_metrics(self.db)

    def _count_jobs(
        self,
        requested_kinds: set[str],
        status: str | None,
        user_oid: ObjectId | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> int:
        total = 0
        if "generation" in requested_kinds:
            total += self.db.generation_jobs.count_documents(
                self._generation_query(status, user_oid, date_from, date_to)
            )
        if "evaluation" in requested_kinds:
            total += self.db.evaluation_jobs.count_documents(
                self._evaluation_query(status, user_oid, date_from, date_to)
            )
        if "document" in requested_kinds:
            total += self.db.document_jobs.count_documents(
                self._document_query(status, user_oid, date_from, date_to)
            )
        return total

    def retry_job(
        self,
        job_kind: str,
        job_id: str,
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
    ) -> dict:
        normalized = job_kind.lower()
        if normalized == "generation":
            result = self._retry_generation(job_id, background_tasks, current_user)
        elif normalized == "evaluation":
            result = self._retry_evaluation(job_id, background_tasks, current_user)
        elif normalized == "document":
            result = self._retry_document(job_id, background_tasks, current_user)
        else:
            raise ValueError("Loại job không hợp lệ")
        return result

    def cancel_job(self, job_kind: str, job_id: str, current_user: CurrentUser) -> dict:
        normalized = job_kind.lower()
        if normalized == "generation":
            result = self._cancel_generation(job_id, current_user)
        elif normalized == "evaluation":
            result = self._cancel_evaluation(job_id, current_user)
        elif normalized == "document":
            result = self._cancel_document(job_id, current_user)
        else:
            raise ValueError("Loại job không hợp lệ")
        return result

    def _generation_jobs(
        self,
        status: str | None,
        user_oid: ObjectId | None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 500,
    ) -> list[dict]:
        query = self._generation_query(status, user_oid, date_from, date_to)
        return [
            self._normalize_generation(job)
            for job in self.db.generation_jobs.find(query).sort("updated_at", -1).limit(limit)
        ]

    def _evaluation_jobs(
        self,
        status: str | None,
        user_oid: ObjectId | None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 500,
    ) -> list[dict]:
        query = self._evaluation_query(status, user_oid, date_from, date_to)
        return [
            self._normalize_evaluation(job)
            for job in self.db.evaluation_jobs.find(query).sort("updated_at", -1).limit(limit)
        ]

    def _document_jobs(
        self,
        status: str | None,
        user_oid: ObjectId | None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 500,
    ) -> list[dict]:
        query = self._document_query(status, user_oid, date_from, date_to)
        document_jobs = list(self.db.document_jobs.find(query).sort("queued_at", -1).limit(limit))
        document_ids = [job["document_id"] for job in document_jobs if job.get("document_id")]
        documents = {
            doc["_id"]: doc
            for doc in self.db.documents.find(
                {"_id": {"$in": document_ids}},
                {"title": 1, "original_filename": 1, "uploaded_by_user_id": 1},
            )
        }
        return [
            self._normalize_document(job, documents.get(job.get("document_id")))
            for job in document_jobs
        ]

    def _generation_query(self, status, user_oid, date_from, date_to) -> dict:
        query: dict = {}
        status_filter = _generation_status_filter(status)
        if status_filter is not None:
            query["status"] = status_filter
        if user_oid:
            query["requested_by_user_id"] = user_oid
        self._apply_date_query(query, "updated_at", date_from, date_to)
        return query

    def _evaluation_query(self, status, user_oid, date_from, date_to) -> dict:
        query: dict = {}
        status_filter = _uppercase_status_filter(status)
        if status_filter is not None:
            query["status"] = status_filter
        if user_oid:
            query["requested_by_user_id"] = user_oid
        self._apply_date_query(query, "updated_at", date_from, date_to)
        return query

    def _document_query(self, status, user_oid, date_from, date_to) -> dict:
        query: dict = {}
        status_filter = _uppercase_status_filter(status)
        if status_filter is not None:
            query["status"] = status_filter
        if user_oid:
            document_ids = [
                doc["_id"]
                for doc in self.db.documents.find({"uploaded_by_user_id": user_oid}, {"_id": 1})
            ]
            query["document_id"] = {"$in": document_ids}
        self._apply_date_query(query, "queued_at", date_from, date_to)
        return query

    @staticmethod
    def _apply_date_query(
        query: dict,
        field: str,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> None:
        bounds = {}
        if date_from:
            bounds["$gte"] = date_from
        if date_to:
            bounds["$lte"] = date_to
        if bounds:
            query[field] = bounds

    def _normalize_generation(self, job: dict) -> dict:
        status = job.get("status", "")
        updated_at = _job_time(job)
        request = job.get("request") or {}
        return {
            "kind": "generation",
            "id": str(job["_id"]),
            "type": "Generation",
            "status": status,
            "actor_user_id": job.get("requested_by_user_id"),
            "entity": {"type": "document", "id": request.get("document_id"), "label": request.get("document_id")},
            "progress": None,
            "error_message": job.get("error_message"),
            "queued_at": job.get("created_at"),
            "started_at": (job.get("metrics") or {}).get("server", {}).get("processing_started_at"),
            "finished_at": (job.get("metrics") or {}).get("server", {}).get("finished_at"),
            "updated_at": job.get("updated_at"),
            "sort_at": updated_at,
            "age_seconds": _seconds_since(updated_at),
            "is_long_running": status in ACTIVE_STATUSES and (_seconds_since(updated_at) or 0) > settings.job_recovery_timeout_minutes * 60,
            "can_retry": status in RETRYABLE_STATUSES,
            "can_cancel": status in ACTIVE_STATUSES,
            "snapshot": {
                "request": request,
                "metrics": job.get("metrics"),
                "summary": (job.get("result") or {}).get("summary"),
            },
        }

    def _normalize_evaluation(self, job: dict) -> dict:
        status = job.get("status", "")
        updated_at = _job_time(job)
        return {
            "kind": "evaluation",
            "id": str(job["_id"]),
            "type": "Evaluation",
            "status": status,
            "actor_user_id": job.get("requested_by_user_id"),
            "entity": {"type": "question", "id": job.get("question_id"), "label": job.get("question_version")},
            "progress": None,
            "error_message": _error_message(job.get("error")),
            "queued_at": job.get("queued_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "updated_at": job.get("updated_at"),
            "sort_at": updated_at,
            "age_seconds": _seconds_since(updated_at),
            "is_long_running": status in ACTIVE_STATUSES and (_seconds_since(updated_at) or 0) > settings.job_recovery_timeout_minutes * 60,
            "can_retry": status in RETRYABLE_STATUSES,
            "can_cancel": status in ACTIVE_STATUSES,
            "snapshot": {
                "evaluator_model_code": job.get("evaluator_model_code"),
                "attempt_no": job.get("attempt_no"),
                "trigger": job.get("trigger"),
                "policy_snapshot": job.get("policy_snapshot"),
                "source_snapshot": job.get("source_snapshot"),
                "result": job.get("result"),
            },
        }

    def _normalize_document(self, job: dict, document: dict | None) -> dict:
        status = job.get("status", "")
        updated_at = _job_time(job)
        return {
            "kind": "document",
            "id": str(job["_id"]),
            "type": job.get("job_type", "DOCUMENT"),
            "status": status,
            "actor_user_id": document.get("uploaded_by_user_id") if document else None,
            "entity": {
                "type": "document",
                "id": job.get("document_id"),
                "label": (document or {}).get("title") or (document or {}).get("original_filename"),
            },
            "progress": job.get("progress"),
            "error_message": _error_message(job.get("error")),
            "queued_at": job.get("queued_at"),
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "updated_at": job.get("updated_at") or job.get("finished_at") or job.get("started_at") or job.get("queued_at"),
            "sort_at": updated_at,
            "age_seconds": _seconds_since(updated_at),
            "is_long_running": status in ACTIVE_STATUSES and (_seconds_since(updated_at) or 0) > settings.job_recovery_timeout_minutes * 60,
            "can_retry": status in RETRYABLE_STATUSES and job.get("job_type") in RETRYABLE_DOCUMENT_JOB_TYPES,
            "can_cancel": status in ACTIVE_STATUSES,
            "snapshot": {
                "document_version": job.get("document_version"),
                "attempt_no": job.get("attempt_no"),
                "config": job.get("config"),
                "stats": job.get("stats"),
            },
        }

    @staticmethod
    def _matches_search(job: dict, term: str) -> bool:
        fields = [
            job.get("id"),
            job.get("kind"),
            job.get("type"),
            job.get("status"),
            job.get("error_message"),
            (job.get("entity") or {}).get("id"),
            (job.get("entity") or {}).get("label"),
        ]
        return any(term in str(value).lower() for value in fields if value is not None)

    @staticmethod
    def _matches_date_range(
        job: dict,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> bool:
        job_time = _as_utc_datetime(job.get("sort_at"))
        if not job_time:
            return False
        if date_from and job_time < date_from:
            return False
        if date_to and job_time > date_to:
            return False
        return True

    @staticmethod
    def _public_item(job: dict) -> dict:
        public = dict(job)
        public.pop("sort_at", None)
        return json_safe(public)

    @staticmethod
    def _summary(jobs: list[dict]) -> dict:
        return {
            "total": len(jobs),
            "active": sum(1 for job in jobs if job.get("status") in ACTIVE_STATUSES),
            "failed": sum(1 for job in jobs if job.get("status") in RETRYABLE_STATUSES),
            "long_running": sum(1 for job in jobs if job.get("is_long_running")),
        }

    def _retry_generation(
        self,
        job_id: str,
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
    ) -> dict:
        job = self.db.generation_jobs.find_one({"_id": _parse_object_id(job_id, "job_id")})
        if not job:
            raise LookupError("Không tìm thấy job")
        if job.get("status") not in RETRYABLE_STATUSES:
            raise ValueError("Chỉ retry job generation đã lỗi")
        new_job_id = create_generation_job(
            job.get("request") or {},
            requested_by_user_id=job.get("requested_by_user_id"),
        )
        self._audit(current_user, "admin.job_retry", "generation", job_id, {"new_job_id": new_job_id})
        return {"job": json_safe(get_generation_job(new_job_id))}

    def _retry_evaluation(
        self,
        job_id: str,
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
    ) -> dict:
        job = self.db.evaluation_jobs.find_one({"_id": _parse_object_id(job_id, "job_id")})
        if not job:
            raise LookupError("Không tìm thấy job")
        if job.get("status") not in RETRYABLE_STATUSES:
            raise ValueError("Chỉ retry job evaluation đã lỗi hoặc stale")
        question = self.db.questions.find_one({"_id": job.get("question_id")})
        if not question:
            raise LookupError("Không tìm thấy câu hỏi của job")
        queued = QuestionWorkflowService(self.db).enqueue_auto_evaluation(
            str(question["_id"]),
            expected_version=question["current_version"],
            requested_by_user_id=job.get("requested_by_user_id") or current_user.id,
            evaluator_model_code=job.get("evaluator_model_code") or settings.evaluation_model_provider,
            trigger="ADMIN_RETRY",
        )
        self._audit(current_user, "admin.job_retry", "evaluation", job_id, {"new_job_id": queued.get("_id")})
        return {"job": json_safe(queued)}

    def _retry_document(
        self,
        job_id: str,
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
    ) -> dict:
        repository = MongoDocumentRepository(self.db)
        job = repository.find_job(job_id)
        if not job:
            raise LookupError("Không tìm thấy job")
        result = DocumentService(repository).retry_job(str(job["document_id"]), job_id, background_tasks, current_user)
        self._audit(current_user, "admin.job_retry", "document", job_id, {"new_job_id": result["job"]["id"]})
        return result

    def _cancel_generation(self, job_id: str, current_user: CurrentUser) -> dict:
        now = utc_now()
        result = self.db.generation_jobs.find_one_and_update(
            {"_id": _parse_object_id(job_id, "job_id"), "status": {"$in": ["queued", "processing"]}},
            {
                "$set": {
                    "status": "failed",
                    "error_message": f"Cancelled by admin {current_user.email}",
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            raise ValueError("Job không ở trạng thái có thể hủy")
        self._audit(current_user, "admin.job_cancel", "generation", job_id)
        return {"job": json_safe(result)}

    def _cancel_evaluation(self, job_id: str, current_user: CurrentUser) -> dict:
        now = utc_now()
        error = {"message": f"Cancelled by admin {current_user.email}", "at": now}
        result = self.db.evaluation_jobs.find_one_and_update(
            {"_id": _parse_object_id(job_id, "job_id"), "status": {"$in": ["QUEUED", "PROCESSING"]}},
            {
                "$set": {
                    "status": "STALE",
                    "error": error,
                    "finished_at": now,
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not result:
            raise ValueError("Job không ở trạng thái có thể hủy")
        self.db.questions.update_one(
            {
                "_id": result.get("question_id"),
                "quality_summary.latest_evaluation_job_id": result["_id"],
            },
            {"$set": {"evaluation_status": "STALE", "quality_summary.error": error, "updated_at": now}},
        )
        self._audit(current_user, "admin.job_cancel", "evaluation", job_id)
        return {"job": json_safe(result)}

    def _cancel_document(self, job_id: str, current_user: CurrentUser) -> dict:
        repository = MongoDocumentRepository(self.db)
        job = repository.find_job(job_id)
        if not job:
            raise LookupError("Không tìm thấy job")
        result = DocumentService(repository).cancel_job(str(job["document_id"]), job_id, current_user)
        self._audit(current_user, "admin.job_cancel", "document", job_id)
        return result

    @staticmethod
    def _audit(
        current_user: CurrentUser,
        action: str,
        entity_type: str,
        entity_id: str,
        metadata: dict | None = None,
    ) -> None:
        record_audit_event(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=current_user.id,
            actor_role=current_user.role,
            metadata=metadata or {},
        )
