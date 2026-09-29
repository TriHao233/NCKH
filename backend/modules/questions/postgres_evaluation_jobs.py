"""PostgreSQL evaluation queue with version guards and worker leases."""

from __future__ import annotations

from datetime import timedelta

from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from db.bson_json import restore
from db.copy_business_data import projected_rows, upsert
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.questions.repository import object_id, utc_now


ACTIVE = {"QUEUED", "PROCESSING"}
RETRYABLE_QUESTION_STATUSES = {
    "NOT_STARTED", "FAILED", "ERROR", "STALE", "INSUFFICIENT_EVIDENCE",
    "EVIDENCE_VALIDATION_FAILED",
}


def _job(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = restore(row["payload"] or {})
    result.update({
        "_id": ObjectId(row["id"]),
        "question_id": ObjectId(row["question_id"]),
        "question_version_id": ObjectId(row["question_version_id"]),
        "requested_by_user_id": (ObjectId(row["requested_by_user_id"])
                                 if row["requested_by_user_id"] else None),
        "status": row["status"], "evaluator_model_code": row["evaluator_model_code"],
        "attempt_no": row["attempt_no"],
        "locked_by": row["lease_owner"],
        "lease_expires_at": row["lease_expires_at"],
        "next_attempt_at": row["next_attempt_at"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    })
    return result


class PostgresEvaluationJobs:
    @staticmethod
    def _save(conn, job: dict) -> None:
        for table, row in projected_rows("evaluation_jobs", job):
            upsert(conn, table, row)

    def get(self, job_id: str | ObjectId) -> dict | None:
        with postgres_connection() as conn:
            row = conn.execute("SELECT * FROM evaluation_jobs WHERE id=%s",
                               (str(object_id(job_id, "evaluation_job_id")),)).fetchone()
        return _job(row)

    def next_queued_id(self) -> str | None:
        with postgres_connection() as conn:
            row = conn.execute(
                """SELECT id FROM evaluation_jobs
                   WHERE (status='QUEUED' AND
                          (next_attempt_at IS NULL OR next_attempt_at <= now()))
                      OR (status='PROCESSING' AND lease_expires_at <= now())
                   ORDER BY created_at, id LIMIT 1"""
            ).fetchone()
        return row["id"] if row else None

    def enqueue(self, question_id: str | ObjectId,
                expected_version_id: ObjectId, job: dict) -> dict:
        repository = PostgresQuestionRepository()
        with postgres_connection() as conn:
            pair = repository._pair(conn, question_id, lock=True)
            if not pair or pair[1]["_id"] != expected_version_id:
                raise RuntimeError("VERSION_CONFLICT")
            question, version = pair
            if question["evaluation_status"] == "PASSED":
                raise ValueError("Câu hỏi đã có kết quả AI đạt cho phiên bản hiện tại")
            dedupe_key = job.get("dedupe_key")
            if dedupe_key:
                existing = conn.execute(
                    """SELECT * FROM evaluation_jobs
                       WHERE payload->>'dedupe_key'=%s
                         AND status IN ('QUEUED','PROCESSING') LIMIT 1""",
                    (dedupe_key,),
                ).fetchone()
                if existing:
                    return _job(existing)
            if question["evaluation_status"] not in RETRYABLE_QUESTION_STATUSES:
                raise RuntimeError("VERSION_CONFLICT")
            attempt = conn.execute(
                """SELECT count(*) AS n FROM evaluation_jobs
                   WHERE question_version_id=%s AND evaluator_model_code=%s""",
                (str(version["_id"]), job["evaluator_model_code"]),
            ).fetchone()["n"] + 1
            job["attempt_no"] = attempt
            job["status"] = "QUEUED"
            self._save(conn, job)
            question["evaluation_status"] = "QUEUED"
            question["quality_summary"] = {
                "latest_evaluation_job_id": job["_id"],
                "evaluated_version_id": version["_id"],
                "evaluation_queued_at": job.get("queued_at") or job["created_at"],
                "evaluator_model_code": job["evaluator_model_code"],
            }
            question["updated_at"] = utc_now()
            repository._save_question(conn, question)
            stale = conn.execute(
                """SELECT * FROM evaluation_jobs
                   WHERE question_id=%s AND question_version_id<>%s
                     AND status IN ('QUEUED','PROCESSING') FOR UPDATE""",
                (str(question["_id"]), str(version["_id"])),
            ).fetchall()
            now = utc_now()
            for row in stale:
                old = _job(row)
                old.update(status="STALE", updated_at=now, finished_at=now,
                           superseded_by_job_id=job["_id"],
                           expires_at=now + timedelta(days=settings.job_retention_days),
                           locked_by=None, worker_id=None,
                           lease_expires_at=None, next_attempt_at=None,
                           error={"message": "Evaluation được thay thế bởi phiên bản câu hỏi mới hơn",
                                  "stage": "SUPERSEDED", "at": now})
                self._save(conn, old)
            return job

    def claim(self, job_id: str | ObjectId, worker_id: str) -> dict | None:
        key = str(object_id(job_id, "evaluation_job_id"))
        repository = PostgresQuestionRepository()
        with postgres_connection() as conn:
            identity = conn.execute(
                "SELECT question_id FROM evaluation_jobs WHERE id=%s", (key,),
            ).fetchone()
            if not identity:
                return None
            pair = repository._pair(conn, identity["question_id"], lock=True)
            row = conn.execute("SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE",
                               (key,)).fetchone()
            if not row:
                return None
            now = utc_now()
            if not ((row["status"] == "QUEUED" and
                     (row["next_attempt_at"] is None or row["next_attempt_at"] <= now))
                    or (row["status"] == "PROCESSING" and
                        row["lease_expires_at"] is not None and
                        row["lease_expires_at"] <= now)):
                return None
            job = _job(row)
            if not pair or pair[1]["_id"] != job["question_version_id"]:
                job.update(status="STALE", updated_at=now,
                           error={"message": "Phiên bản câu hỏi đã thay đổi"})
                self._save(conn, job)
                return None
            job.update(status="PROCESSING", locked_by=worker_id,
                       worker_id=worker_id,
                       lease_expires_at=now + timedelta(seconds=settings.job_lease_seconds),
                       heartbeat_at=now, started_at=now, updated_at=now,
                       next_attempt_at=None,
                       processing_attempt_count=int(job.get("processing_attempt_count") or 0) + 1)
            self._save(conn, job)
            question, version = pair
            if question["evaluation_status"] in ACTIVE:
                summary = question.get("quality_summary") or {}
                summary.update(latest_evaluation_job_id=job["_id"],
                               evaluation_started_at=now)
                question.update(evaluation_status="PROCESSING",
                                quality_summary=summary, updated_at=now)
                repository._save_question(conn, question)
            return job

    def heartbeat(self, job_id: str | ObjectId, worker_id: str) -> bool:
        key = str(object_id(job_id, "evaluation_job_id"))
        with postgres_connection() as conn:
            row = conn.execute(
                "SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE", (key,),
            ).fetchone()
            if not row or row["status"] != "PROCESSING" or row["lease_owner"] != worker_id:
                return False
            job = _job(row)
            now = utc_now()
            job.update(heartbeat_at=now,
                       lease_expires_at=now + timedelta(seconds=settings.job_lease_seconds),
                       updated_at=now)
            self._save(conn, job)
            return True

    def finish(self, job_id: str | ObjectId, worker_id: str,
               result: dict, **fields) -> bool:
        key = str(object_id(job_id, "evaluation_job_id"))
        with postgres_connection() as conn:
            row = conn.execute("SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE",
                               (key,)).fetchone()
            if not row or row["status"] != "PROCESSING" or row["lease_owner"] != worker_id:
                return False
            job = _job(row)
            now = utc_now()
            job.update(fields)
            job.update(status="COMPLETED", result=result, finished_at=now,
                       expires_at=now + timedelta(days=settings.job_retention_days),
                       updated_at=now, locked_by=None, worker_id=None,
                       lease_expires_at=None, next_attempt_at=None)
            self._save(conn, job)
            return True

    def mark_enqueue_error(self, question_id: str | ObjectId, *,
                           expected_version: int, evaluator_model_code: str,
                           message: str) -> dict | None:
        repository = PostgresQuestionRepository()
        with postgres_connection() as conn:
            pair = repository._pair(conn, question_id, lock=True)
            if (not pair or pair[0]["current_version"] != expected_version
                    or pair[0]["evaluation_status"] not in RETRYABLE_QUESTION_STATUSES):
                return None
            question, _version = pair
            now = utc_now()
            question.update(
                evaluation_status="ERROR",
                quality_summary={
                    "evaluated_version_id": None,
                    "evaluator_model_code": evaluator_model_code,
                    "error": {"message": message, "at": now, "stage": "ENQUEUE"},
                },
                updated_at=now,
            )
            repository._save_question(conn, question)
            return question

    def mark_error(self, job_id: str | ObjectId, *, worker_id: str | None,
                   message: str, status: str = "ERROR",
                   question_status: str = "ERROR", code: str = "EVALUATION_ERROR",
                   evidence: dict | None = None,
                   raw_response_excerpt: str | None = None,
                   duration_ms: int | None = None,
                   dead_lettered: bool = False) -> dict | None:
        key = str(object_id(job_id, "evaluation_job_id"))
        repository = PostgresQuestionRepository()
        with postgres_connection() as conn:
            identity = conn.execute("SELECT question_id FROM evaluation_jobs WHERE id=%s",
                                    (key,)).fetchone()
            if not identity:
                return None
            pair = repository._pair(conn, identity["question_id"], lock=True)
            row = conn.execute("SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE",
                               (key,)).fetchone()
            if (not row or row["status"] not in ACTIVE
                    or (worker_id is not None and row["lease_owner"] != worker_id)):
                return None
            job = _job(row)
            now = utc_now()
            error = {"code": code, "message": message,
                     "raw_model_response_excerpt": (raw_response_excerpt or "")[:1200] or None,
                     "at": now}
            job.update(status=status, error=error, finished_at=now,
                       duration_ms=duration_ms, updated_at=now,
                       locked_by=None, worker_id=None,
                       lease_expires_at=None, next_attempt_at=None)
            if dead_lettered:
                job["dead_lettered_at"] = now
            if status in {"ERROR", "STALE", "CANCELLED"}:
                job["expires_at"] = now + timedelta(days=settings.job_retention_days)
            self._save(conn, job)
            if (status != "STALE" and pair
                    and pair[1]["_id"] == job["question_version_id"]):
                question, _version = pair
                question.update(
                    evaluation_status=question_status,
                    quality_summary={
                        "latest_evaluation_job_id": job["_id"],
                        "evaluated_version_id": job["question_version_id"],
                        "evaluator_model_code": job["evaluator_model_code"],
                        "error": error, "evidence": evidence or {},
                    }, updated_at=now,
                )
                repository._save_question(conn, question)
            return job

    def retry_or_dead_letter(self, job_id: str | ObjectId, worker_id: str,
                             message: str, *, duration_ms: int,
                             raw_response_excerpt: str | None = None) -> dict | None:
        key = str(object_id(job_id, "evaluation_job_id"))
        repository = PostgresQuestionRepository()
        with postgres_connection() as conn:
            identity = conn.execute("SELECT question_id FROM evaluation_jobs WHERE id=%s",
                                    (key,)).fetchone()
            if not identity:
                return None
            pair = repository._pair(conn, identity["question_id"], lock=True)
            row = conn.execute("SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE",
                               (key,)).fetchone()
            if not row or row["status"] != "PROCESSING" or row["lease_owner"] != worker_id:
                return None
            job = _job(row)
            attempts = int(job.get("processing_attempt_count") or 1)
            max_attempts = int(job.get("max_attempts") or settings.job_max_attempts)
            if attempts < max_attempts:
                now = utc_now()
                error = {"message": message,
                         "raw_model_response_excerpt": (raw_response_excerpt or "")[:1200] or None,
                         "at": now}
                delay = min(settings.job_retry_base_seconds * (2 ** max(0, attempts - 1)),
                            settings.job_retry_max_seconds)
                job.update(status="QUEUED", next_attempt_at=now + timedelta(seconds=delay),
                           error=error, updated_at=now, locked_by=None,
                           worker_id=None, lease_expires_at=None)
                self._save(conn, job)
                if pair and pair[1]["_id"] == job["question_version_id"]:
                    question, _version = pair
                    question["evaluation_status"] = "QUEUED"
                    summary = question.get("quality_summary") or {}
                    summary["last_retry_error"] = error
                    question["quality_summary"] = summary
                    question["updated_at"] = now
                    repository._save_question(conn, question)
                return job
        # Hết lượt thử: dead-letter giống lỗi cuối để câu hỏi hiện đủ lỗi cho người duyệt.
        return self.mark_error(job_id, worker_id=worker_id, message=message,
                               raw_response_excerpt=raw_response_excerpt,
                               duration_ms=duration_ms, dead_lettered=True)

    def update_snapshots(self, job_id: str | ObjectId, fields: dict) -> bool:
        key = str(object_id(job_id, "evaluation_job_id"))
        with postgres_connection() as conn:
            row = conn.execute("SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE",
                               (key,)).fetchone()
            if not row or row["status"] != "PROCESSING":
                return False
            job = _job(row)
            job.update(fields)
            job["updated_at"] = utc_now()
            self._save(conn, job)
            return True

    def recover_stale(self, cutoff, message: str) -> int:
        """Đánh dấu STALE các job còn active nhưng không cập nhật từ trước `cutoff`."""
        repository = PostgresQuestionRepository()
        with postgres_connection() as conn:
            rows = conn.execute(
                """SELECT id, question_id FROM evaluation_jobs
                   WHERE status IN ('QUEUED','PROCESSING') AND updated_at < %s
                   ORDER BY question_id, id""",
                (cutoff,),
            ).fetchall()
        recovered = 0
        for identity in rows:
            with postgres_connection() as conn:
                pair = repository._pair(conn, identity["question_id"], lock=True)
                row = conn.execute(
                    "SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE", (identity["id"],),
                ).fetchone()
                if not row or row["status"] not in ACTIVE or row["updated_at"] >= cutoff:
                    continue
                job = _job(row)
                now = utc_now()
                error = {"message": message, "at": now}
                job.update(status="STALE", error=error, finished_at=now, updated_at=now,
                           expires_at=now + timedelta(days=settings.job_retention_days),
                           locked_by=None, worker_id=None,
                           lease_expires_at=None, next_attempt_at=None)
                self._save(conn, job)
                recovered += 1
                if not pair:
                    continue
                question, _version = pair
                summary = question.get("quality_summary") or {}
                if (question["evaluation_status"] in ACTIVE
                        and summary.get("latest_evaluation_job_id") == job["_id"]):
                    summary["error"] = error
                    question.update(evaluation_status="STALE", quality_summary=summary,
                                    updated_at=now)
                    repository._save_question(conn, question)
        return recovered

    # ---- Admin views -----------------------------------------------------

    @staticmethod
    def _admin_where(statuses: list[str] | None, requested_by_user_id: ObjectId | None,
                     date_from, date_to) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        legacy_cancel = "(status='STALE' AND error->>'message' LIKE 'Cancelled by admin %%')"
        if statuses == ["CANCELLED"]:
            # Bản cũ ghi hủy của Admin thành STALE + message; vẫn hiển thị là CANCELLED.
            clauses.append(f"(status='CANCELLED' OR {legacy_cancel})")
        elif statuses:
            clauses.append("status=ANY(%s)")
            params.append(statuses)
            if "STALE" in statuses:
                clauses.append(f"NOT {legacy_cancel}")
        if requested_by_user_id is not None:
            clauses.append("requested_by_user_id=%s")
            params.append(str(requested_by_user_id))
        if date_from is not None:
            clauses.append("updated_at >= %s")
            params.append(date_from)
        if date_to is not None:
            clauses.append("updated_at <= %s")
            params.append(date_to)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def admin_jobs(self, statuses: list[str] | None, requested_by_user_id: ObjectId | None,
                   date_from, date_to, limit: int) -> list[dict]:
        where, params = self._admin_where(statuses, requested_by_user_id, date_from, date_to)
        with postgres_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM evaluation_jobs" + where
                + " ORDER BY updated_at DESC, id DESC LIMIT %s", [*params, limit],
            ).fetchall()
        return [_job(row) for row in rows]

    def count_admin_jobs(self, statuses: list[str] | None,
                         requested_by_user_id: ObjectId | None, date_from, date_to) -> int:
        where, params = self._admin_where(statuses, requested_by_user_id, date_from, date_to)
        with postgres_connection() as conn:
            return conn.execute("SELECT count(*) AS n FROM evaluation_jobs" + where,
                                params).fetchone()["n"]

    def active_job_ids(self, question_id: str | ObjectId) -> set[str]:
        with postgres_connection() as conn:
            rows = conn.execute(
                "SELECT id FROM evaluation_jobs WHERE question_id=%s "
                "AND status IN ('QUEUED','PROCESSING')",
                (str(object_id(question_id, "question_id")),),
            ).fetchall()
        return {row["id"] for row in rows}

    def cancel(self, job_id: str | ObjectId, error: dict) -> dict | None:
        """Admin hủy job đang chờ/chạy; câu hỏi quay về NOT_STARTED nếu job là lượt mới nhất."""
        key = str(object_id(job_id, "evaluation_job_id"))
        repository = PostgresQuestionRepository()
        with postgres_connection() as conn:
            identity = conn.execute("SELECT question_id FROM evaluation_jobs WHERE id=%s",
                                    (key,)).fetchone()
            if not identity:
                return None
            pair = repository._pair(conn, identity["question_id"], active_only=False, lock=True)
            row = conn.execute("SELECT * FROM evaluation_jobs WHERE id=%s FOR UPDATE",
                               (key,)).fetchone()
            if not row or row["status"] not in ACTIVE:
                return None
            job = _job(row)
            now = error.get("at") or utc_now()
            job.update(status="CANCELLED", error=error, finished_at=now, updated_at=now,
                       expires_at=now + timedelta(days=settings.job_retention_days),
                       locked_by=None, worker_id=None,
                       lease_expires_at=None, next_attempt_at=None)
            self._save(conn, job)
            if pair:
                question, _version = pair
                summary = dict(question.get("quality_summary") or {})
                if summary.get("latest_evaluation_job_id") == job["_id"]:
                    for field in ("overall_score", "color", "latest_evaluation_id"):
                        summary.pop(field, None)
                    summary["error"] = error
                    question.update(evaluation_status="NOT_STARTED",
                                    quality_summary=summary, updated_at=now)
                    repository._save_question(conn, question)
            return job

    def queue_metrics(self) -> dict:
        with postgres_connection() as conn:
            row = conn.execute(
                """SELECT
                     count(*) FILTER (WHERE status='QUEUED') AS queued,
                     count(*) FILTER (WHERE status='PROCESSING') AS processing,
                     count(*) FILTER (WHERE status='QUEUED' AND next_attempt_at > now())
                       AS retry_wait,
                     count(*) FILTER (WHERE payload->>'dead_lettered_at' IS NOT NULL)
                       AS dead_lettered,
                     count(*) FILTER (WHERE status='PROCESSING' AND lease_expires_at <= now())
                       AS expired_leases,
                     min(created_at) FILTER (WHERE status='QUEUED') AS oldest_queued
                   FROM evaluation_jobs"""
            ).fetchone()
        return dict(row)

    def recent_jobs(self, since, limit: int = 1000) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM evaluation_jobs
                   WHERE updated_at >= %s OR created_at >= %s
                      OR (payload->>'finished_at')::timestamptz >= %s
                   ORDER BY updated_at DESC, id DESC LIMIT %s""",
                (since, since, since, limit),
            ).fetchall()
        return [_job(row) for row in rows]
