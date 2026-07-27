from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.database import Database

from modules.admin.audit_service import AdminAuditService
from modules.admin.jobs_service import ACTIVE_STATUSES, RETRYABLE_STATUSES, AdminJobService, json_safe
from modules.admin.moodle_service import MoodleTargetService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


MODEL_WINDOW_DAYS = 30
MODEL_SUCCESS_STATUSES = {"COMPLETED", "PASSED", "SUCCESS", "SUCCEEDED"}
MODEL_FAILED_STATUSES = {"FAILED", "ERROR", "STALE", "FAILED_VALIDATION"}
MODEL_ACTIVE_STATUSES = {"QUEUED", "PROCESSING", "RUNNING", "GENERATING"}


def _as_aware_utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _path_value(record: dict, path: str):
    current = record
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _duration_ms(record: dict, *, duration_path: str, start_key: str = "started_at", end_key: str = "finished_at") -> int | None:
    duration = _path_value(record, duration_path)
    if isinstance(duration, (int, float)):
        return max(0, int(duration))
    start = _as_aware_utc(record.get(start_key))
    end = _as_aware_utc(record.get(end_key))
    if start and end and end >= start:
        return int((end - start).total_seconds() * 1000)
    return None


class AdminOverviewService:
    def __init__(self, database: Database):
        self.db = database

    def overview(self) -> dict:
        job_service = AdminJobService(self.db)
        job_page = job_service.list_jobs(page=1, page_size=500)
        retryable_jobs = job_service.list_jobs(page=1, page_size=5, status="retryable")
        moodle_summary = MoodleTargetService(self.db)._publication_summary(None)
        audit_page = AdminAuditService(self.db).list(page=1, page_size=5)
        pending_review = self._question_count({"review_status": "PENDING"})
        failed_documents = self._document_count({"status": "FAILED"})
        retryable_job_count = job_page["summary"].get("failed", 0)
        long_running_job_count = job_page["summary"].get("long_running", 0)

        attention = [
            {
                "key": "pending_review",
                "label": "Câu hỏi chờ duyệt",
                "count": pending_review,
                "severity": "warning" if pending_review else "neutral",
                "path": "/kiem-duyet?status=PENDING",
            },
            {
                "key": "retryable_jobs",
                "label": "Job cần xử lý",
                "count": retryable_job_count,
                "severity": "danger" if retryable_job_count else "neutral",
                "path": "/quan-ly-job?status=retryable",
            },
            {
                "key": "long_running_jobs",
                "label": "Job quá ngưỡng",
                "count": long_running_job_count,
                "severity": "warning" if long_running_job_count else "neutral",
                "path": "/quan-ly-job?stale_only=true",
            },
            {
                "key": "failed_documents",
                "label": "Tài liệu lỗi",
                "count": failed_documents,
                "severity": "danger" if failed_documents else "neutral",
                "path": "/quan-ly?tab=documents&status=FAILED",
            },
        ]

        return json_safe(
            {
                "generated_at": utc_now(),
                "users": {
                    "total": self._count("users", {}),
                    "active": self._count("users", {"is_active": True}),
                    "admins": self._count("users", {"role": "Admin", "is_active": True}),
                    "teachers": self._count("users", {"role": "Teacher", "is_active": True}),
                    "reviewers": self._count("users", {"role": "Reviewer", "is_active": True}),
                },
                "questions": {
                    "total": self._question_count({}),
                    "draft": self._question_count({"review_status": "DRAFT"}),
                    "pending": pending_review,
                    "approved": self._question_count({"review_status": "APPROVED"}),
                    "needs_revision": self._question_count({"review_status": "NEEDS_REVISION"}),
                    "rejected": self._question_count({"review_status": "REJECTED"}),
                    "published": self._question_count({"publication_status": "PUBLISHED"}),
                    "quality": self._quality_summary(),
                },
                "documents": {
                    "total": self._document_count({}),
                    "uploaded": self._document_count({"status": "UPLOADED"}),
                    "processing": self._document_count({"status": "PROCESSING"}),
                    "ready": self._document_count({"status": {"$in": ["READY", "INDEXED", "COMPLETED"]}}),
                    "failed": failed_documents,
                },
                "jobs": {
                    **job_page["summary"],
                    "breakdown": self._job_breakdown(job_page["items"]),
                },
                "moodle": {
                    "targets": self._count("moodle_targets", {}),
                    "active_targets": self._count("moodle_targets", {"is_active": True}),
                    "publications": moodle_summary,
                },
                "model_performance": self._model_performance(),
                "attention": attention,
                "recent_jobs": retryable_jobs["items"],
                "recent_audit": audit_page["items"],
            }
        )

    def _count(self, collection_name: str, query: dict) -> int:
        return getattr(self.db, collection_name).count_documents(query)

    def _question_count(self, query: dict) -> int:
        return self._count(
            "questions",
            {"lifecycle_status": "ACTIVE", **query},
        )

    def _document_count(self, query: dict) -> int:
        return self._count(
            "documents",
            {"archived_at": None, **query},
        )

    def _quality_summary(self) -> dict:
        return {
            "green": self._question_count({"quality_summary.color": "GREEN"}),
            "yellow": self._question_count({"quality_summary.color": "YELLOW"}),
            "red": self._question_count({"quality_summary.color": "RED"}),
            "not_evaluated": self._question_count(
                {
                    "$or": [
                        {"quality_summary.color": {"$exists": False}},
                        {"quality_summary.color": None},
                    ]
                }
            ),
        }

    @staticmethod
    def _job_group(job: dict) -> tuple[str, str]:
        if job.get("kind") == "generation":
            return "generation", "Sinh câu hỏi"
        if job.get("kind") == "evaluation":
            return "evaluation", "Đánh giá AI"
        if job.get("kind") == "document":
            job_type = str(job.get("type") or "").upper()
            if "OCR" in job_type:
                return "ocr", "OCR"
            if "CHUNK" in job_type or "INDEX" in job_type:
                return "chunk", "Chunk/Index"
            return "document", "Tài liệu"
        return "other", "Khác"

    def _job_breakdown(self, jobs: list[dict]) -> list[dict]:
        order = ["generation", "evaluation", "ocr", "chunk", "document", "other"]
        groups = {
            key: {
                "key": key,
                "label": label,
                "total": 0,
                "active": 0,
                "failed": 0,
                "long_running": 0,
            }
            for key, label in [
                ("generation", "Sinh câu hỏi"),
                ("evaluation", "Đánh giá AI"),
                ("ocr", "OCR"),
                ("chunk", "Chunk/Index"),
                ("document", "Tài liệu"),
                ("other", "Khác"),
            ]
        }
        for job in jobs:
            key, label = self._job_group(job)
            group = groups.setdefault(
                key,
                {"key": key, "label": label, "total": 0, "active": 0, "failed": 0, "long_running": 0},
            )
            status = job.get("status")
            group["total"] += 1
            if status in ACTIVE_STATUSES:
                group["active"] += 1
            if status in RETRYABLE_STATUSES:
                group["failed"] += 1
            if job.get("is_long_running"):
                group["long_running"] += 1
        return [groups[key] for key in order if groups[key]["total"] > 0]

    def _model_performance(self) -> list[dict]:
        since = utc_now() - timedelta(days=MODEL_WINDOW_DAYS)
        groups: dict[str, dict] = {}
        self._collect_evaluation_model_performance(groups, since)
        self._collect_generation_model_performance(groups, since)

        rows = []
        for group in groups.values():
            latencies = group.pop("_latencies")
            total = group["total"]
            failed = group["failed"]
            group["error_rate"] = round(failed / total, 3) if total else None
            group["avg_latency_ms"] = round(sum(latencies) / len(latencies)) if latencies else None
            rows.append(group)
        rows.sort(key=lambda item: (item["failed"], item["total"], item["model_code"]), reverse=True)
        return rows[:8]

    def _model_group(self, groups: dict[str, dict], *, kind: str, kind_label: str, model_code: str) -> dict:
        key = f"{kind}:{model_code}"
        return groups.setdefault(
            key,
            {
                "key": key,
                "kind": kind,
                "kind_label": kind_label,
                "model_code": model_code,
                "total": 0,
                "completed": 0,
                "failed": 0,
                "active": 0,
                "_latencies": [],
            },
        )

    def _collect_evaluation_model_performance(self, groups: dict[str, dict], since: datetime) -> None:
        collection = getattr(self.db, "evaluation_jobs", None)
        if collection is None:
            return
        query = {
            "$or": [
                {"updated_at": {"$gte": since}},
                {"finished_at": {"$gte": since}},
                {"queued_at": {"$gte": since}},
            ]
        }
        for job in collection.find(query).sort("updated_at", -1).limit(1000):
            model_code = job.get("evaluator_model_code") or "unknown"
            group = self._model_group(
                groups,
                kind="evaluation",
                kind_label="Đánh giá",
                model_code=str(model_code),
            )
            self._add_model_job(group, job, _duration_ms(job, duration_path="duration_ms"))

    def _collect_generation_model_performance(self, groups: dict[str, dict], since: datetime) -> None:
        collection = getattr(self.db, "generation_runs", None)
        if collection is None:
            return
        query = {
            "$or": [
                {"updated_at": {"$gte": since}},
                {"finished_at": {"$gte": since}},
                {"created_at": {"$gte": since}},
            ]
        }
        for run in collection.find(query).sort("finished_at", -1).limit(1000):
            model = run.get("model") or {}
            model_code = (
                model.get("model_code")
                or model.get("provider")
                or model.get("model_name")
                or "unknown"
            )
            group = self._model_group(
                groups,
                kind="generation",
                kind_label="Sinh câu hỏi",
                model_code=str(model_code),
            )
            self._add_model_job(group, run, _duration_ms(run, duration_path="execution.latency_ms"))

    @staticmethod
    def _add_model_job(group: dict, record: dict, duration_ms: int | None) -> None:
        status = str(record.get("status") or "").upper()
        group["total"] += 1
        if status in MODEL_SUCCESS_STATUSES:
            group["completed"] += 1
        elif status in MODEL_FAILED_STATUSES:
            group["failed"] += 1
        elif status in MODEL_ACTIVE_STATUSES:
            group["active"] += 1
        if duration_ms is not None:
            group["_latencies"].append(duration_ms)
