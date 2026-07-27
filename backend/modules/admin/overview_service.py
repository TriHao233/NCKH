from __future__ import annotations

from datetime import datetime, timezone

from pymongo.database import Database

from modules.admin.audit_service import AdminAuditService
from modules.admin.jobs_service import AdminJobService, json_safe
from modules.admin.moodle_service import MoodleTargetService


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdminOverviewService:
    def __init__(self, database: Database):
        self.db = database

    def overview(self) -> dict:
        job_page = AdminJobService(self.db).list_jobs(page=1, page_size=5)
        retryable_jobs = AdminJobService(self.db).list_jobs(page=1, page_size=5, status="retryable")
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
                },
                "documents": {
                    "total": self._document_count({}),
                    "uploaded": self._document_count({"status": "UPLOADED"}),
                    "processing": self._document_count({"status": "PROCESSING"}),
                    "ready": self._document_count({"status": {"$in": ["READY", "INDEXED", "COMPLETED"]}}),
                    "failed": failed_documents,
                },
                "jobs": job_page["summary"],
                "moodle": {
                    "targets": self._count("moodle_targets", {}),
                    "active_targets": self._count("moodle_targets", {"is_active": True}),
                    "publications": moodle_summary,
                },
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
