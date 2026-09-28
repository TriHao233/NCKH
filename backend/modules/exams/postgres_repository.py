"""PostgreSQL exams and exam variants (EXAM_STORE=postgres)."""

from __future__ import annotations

from bson import ObjectId
from psycopg import errors

from core.config import settings
from core.postgres import postgres_connection
from db.bson_json import restore
from db.copy_business_data import projected_rows, upsert
from modules.exams.repository import object_id, utc_now
from modules.exams.schemas import MAX_VARIANTS_PER_EXAM

# Frozen question snapshots and print headers stay exactly as they were saved.
FROZEN_KEYS = {"content_snapshot", "header", "scoring_config"}


def _restore(value, key: str = ""):
    if key in FROZEN_KEYS:
        return value
    if isinstance(value, dict):
        return {name: _restore(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_restore(item, key[:-1] if key.endswith("s") else key) for item in value]
    return restore(value, key)


def _exam(row: dict | None) -> dict | None:
    if row is None:
        return None
    record = _restore(row["payload"] or {})
    record.update(
        _id=ObjectId(row["id"]), status=row["status"],
        subject_id=ObjectId(row["subject_id"]) if row["subject_id"] else None,
        created_by_user_id=(ObjectId(row["created_by_user_id"])
                            if row["created_by_user_id"] else None),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )
    return record


def _variant(row: dict | None) -> dict | None:
    if row is None:
        return None
    record = _restore(row["payload"] or {})
    record.update(_id=ObjectId(row["id"]), exam_id=ObjectId(row["exam_id"]),
                  created_at=row["created_at"])
    return record


def _save_exam(conn, exam: dict) -> None:
    # exam_questions mirrors the current question list; rebuild it on every save.
    conn.execute("DELETE FROM exam_questions WHERE exam_id=%s", (str(exam["_id"]),))
    for table, row in projected_rows("exams", exam):
        upsert(conn, table, row)


class PostgresExamRepository:
    def __init__(self):
        if settings.question_store != "postgres" or settings.catalog_store != "postgres":
            raise RuntimeError("EXAM_STORE=postgres requires QUESTION_STORE and CATALOG_STORE=postgres")

    def create(self, exam: dict) -> dict:
        with postgres_connection() as conn:
            _save_exam(conn, exam)
        return exam

    def find(self, exam_id: str | ObjectId) -> dict | None:
        with postgres_connection() as conn:
            return _exam(conn.execute("SELECT * FROM exams WHERE id=%s",
                                      (str(object_id(exam_id, "exam_id")),)).fetchone())

    def list(self, page: int, page_size: int,
             created_by_user_id: ObjectId | None) -> tuple[list[dict], int]:
        where, params = "", []
        if created_by_user_id is not None:
            where, params = " WHERE created_by_user_id=%s", [str(created_by_user_id)]
        with postgres_connection() as conn:
            total = conn.execute("SELECT count(*) AS n FROM exams" + where, params).fetchone()["n"]
            rows = conn.execute(
                "SELECT * FROM exams" + where
                + " ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s",
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
        return [_exam(row) for row in rows], total

    def update(self, exam_id: str | ObjectId, updates: dict) -> dict | None:
        key = str(object_id(exam_id, "exam_id"))
        with postgres_connection() as conn:
            exam = _exam(conn.execute("SELECT * FROM exams WHERE id=%s FOR UPDATE",
                                      (key,)).fetchone())
            if not exam:
                return None
            exam.update(updates)
            exam["updated_at"] = utc_now()
            _save_exam(conn, exam)
            return exam

    def delete(self, exam_id: str | ObjectId) -> bool:
        key = str(object_id(exam_id, "exam_id"))
        with postgres_connection() as conn:
            conn.execute("DELETE FROM exam_questions WHERE exam_id=%s", (key,))
            return conn.execute("DELETE FROM exams WHERE id=%s", (key,)).rowcount == 1

    def count_variants(self, exam_id: str | ObjectId) -> int:
        with postgres_connection() as conn:
            return conn.execute(
                "SELECT count(*) AS n FROM exam_variants WHERE exam_id=%s",
                (str(object_id(exam_id, "exam_id")),),
            ).fetchone()["n"]

    @staticmethod
    def open_exams_using_question(question_id: str | ObjectId) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                """SELECT DISTINCT e.* FROM exams e
                   JOIN exam_questions eq ON eq.exam_id=e.id
                   WHERE eq.question_id=%s
                     AND upper(e.status) NOT IN ('FINALIZED','ARCHIVED')""",
                (str(object_id(question_id, "question_id")),),
            ).fetchall()
        return [_exam(row) for row in rows]

    @staticmethod
    def count(*, subject_id=None, chapter_id=None) -> int:
        clauses, params = [], []
        if subject_id is not None:
            clauses.append("subject_id=%s")
            params.append(str(subject_id))
        if chapter_id is not None:
            clauses.append("payload->'matrix' @> %s::jsonb")
            params.append('[{"chapter_id":"' + str(chapter_id) + '"}]')
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with postgres_connection() as conn:
            return conn.execute("SELECT count(*) AS n FROM exams" + where,
                                params).fetchone()["n"]


class PostgresExamVariantRepository:
    def create(self, variant: dict) -> dict:
        exam_id = str(variant["exam_id"])
        try:
            with postgres_connection() as conn:
                # Khóa đề thi để giới hạn số mã đề không bị vượt khi tạo song song.
                if not conn.execute("SELECT 1 FROM exams WHERE id=%s FOR UPDATE",
                                    (exam_id,)).fetchone():
                    raise LookupError("Không tìm thấy đề thi")
                existing = conn.execute(
                    "SELECT count(*) AS n FROM exam_variants WHERE exam_id=%s", (exam_id,),
                ).fetchone()["n"]
                if existing >= MAX_VARIANTS_PER_EXAM:
                    raise ValueError(f"Đã đạt tối đa {MAX_VARIANTS_PER_EXAM} mã đề cho kỳ thi này")
                for table, row in projected_rows("exam_variants", variant):
                    upsert(conn, table, row)
        except errors.UniqueViolation as exc:
            raise ValueError("Mã đề này đã tồn tại trong kỳ thi") from exc
        return variant

    def find(self, variant_id: str | ObjectId) -> dict | None:
        with postgres_connection() as conn:
            return _variant(conn.execute(
                "SELECT * FROM exam_variants WHERE id=%s",
                (str(object_id(variant_id, "variant_id")),),
            ).fetchone())

    def list_by_exam(self, exam_id: str | ObjectId) -> list[dict]:
        with postgres_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM exam_variants WHERE exam_id=%s ORDER BY created_at, id",
                (str(object_id(exam_id, "exam_id")),),
            ).fetchall()
        return [_variant(row) for row in rows]

    def delete(self, variant_id: str | ObjectId) -> bool:
        with postgres_connection() as conn:
            return conn.execute(
                "DELETE FROM exam_variants WHERE id=%s",
                (str(object_id(variant_id, "variant_id")),),
            ).rowcount == 1
