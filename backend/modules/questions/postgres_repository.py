"""Transactional PostgreSQL question/version aggregate (runtime routing follows)."""

from __future__ import annotations

from copy import deepcopy

from bson import ObjectId

from core.postgres import postgres_connection
from db.bson_json import restore
from db.copy_business_data import projected_rows, upsert
from modules.questions.repository import object_id, utc_now


def _question(row: dict | None) -> dict | None:
    if row is None:
        return None
    record = restore(row["payload"] or {})
    record.update({
        "_id": ObjectId(row["id"]), "question_code": row["question_code"],
        "subject_id": ObjectId(row["subject_id"]) if row["subject_id"] else None,
        "created_by_user_id": (ObjectId(row["created_by_user_id"])
                               if row["created_by_user_id"] else None),
        "current_version": row["current_version"],
        "current_version_id": (ObjectId(row["current_version_id"])
                               if row["current_version_id"] else None),
        "approved_version_id": (ObjectId(row["approved_version_id"])
                                if row["approved_version_id"] else None),
        "lifecycle_status": row["lifecycle_status"],
        "review_status": row["review_status"],
        "evaluation_status": row["evaluation_status"],
        "publication_status": row["publication_status"],
        "review_assignment": restore(row["assignment"] or {}),
        "created_at": row["created_at"], "updated_at": row["updated_at"],
    })
    return record


def _version(row: dict | None) -> dict | None:
    if row is None:
        return None
    record = restore(row["payload"] or {})
    record.update({
        "_id": ObjectId(row["id"]), "question_id": ObjectId(row["question_id"]),
        "version": row["version"], "origin": row["origin"],
        "content": row["content"], "question_data": restore(row["question_data"]),
        "classification": restore(row["classification"]),
        "clos": restore(row["clos"]), "sources": restore(row["sources"]),
        "content_hash": row["content_hash"],
        "created_by_user_id": (ObjectId(row["created_by_user_id"])
                               if row["created_by_user_id"] else None),
        "generation_run_id": (ObjectId(row["generation_run_id"])
                              if row["generation_run_id"] else None),
        "created_at": row["created_at"],
    })
    return record


class PostgresQuestionRepository:
    def list(
        self, page: int, page_size: int, review_status: str | None,
        search: str | None, *, question_type: str | None = None,
        bloom_level: int | None = None, document_id: str | None = None,
        subject_id: str | None = None, chapter_id: str | None = None,
        clo_id: str | None = None, difficulty: str | None = None,
        quality_color: str | None = None, min_score: float | None = None,
        publication_status: str | None = None,
        evaluation_status: str | None = None,
        assignment_status: str | None = None,
        assigned_reviewer_user_id: ObjectId | None = None,
        creator_user_id: ObjectId | None = None,
        owner_user_id: ObjectId | None = None,
        visible_to_user_id: ObjectId | None = None,
        approved_current_only: bool = False,
        waiting_since=None, overdue_at=None,
        override_only: bool = False,
        created_from=None, created_to=None,
        submitted_from=None, submitted_to=None,
        include_status_counts: bool = False,
        sort_by: str = "priority",
        source_presence: str | None = None,
        secondary_status: str | None = None,
    ):
        clauses = ["q.lifecycle_status='ACTIVE'"]
        params = []

        def add(expression, *values):
            clauses.append(expression)
            params.extend(values)

        if publication_status:
            add("q.publication_status=%s", publication_status)
        if evaluation_status:
            statuses = [item.strip().upper() for item in evaluation_status.split(",")
                        if item.strip()]
            if statuses:
                add("q.evaluation_status=ANY(%s)", statuses)
        if assignment_status == "UNASSIGNED":
            add("(q.assignment->>'status' IS NULL OR q.assignment->>'status'='UNASSIGNED')")
        elif assignment_status:
            add("q.assignment->>'status'=%s", assignment_status)
        if assigned_reviewer_user_id is not None:
            add("q.assignment->>'reviewer_user_id'=%s", str(assigned_reviewer_user_id))
        if quality_color:
            add("q.payload->'quality_summary'->>'color'=%s", quality_color.upper())
        if min_score is not None:
            add("(q.payload->'quality_summary'->>'overall_score')::numeric >= %s", float(min_score))
        if waiting_since is not None:
            add("q.updated_at <= %s", waiting_since)
        if overdue_at is not None:
            add("(q.assignment->>'lock_expires_at')::timestamptz <= %s", overdue_at)
        if secondary_status:
            add("q.payload->'secondary_review'->>'status'=%s", secondary_status)
        if override_only:
            add("""EXISTS (SELECT 1 FROM question_reviews review
                 WHERE review.id=q.payload->>'latest_review_id'
                   AND review.payload->'override'->>'applied'='true')""")
        if created_from is not None:
            add("q.created_at >= %s", created_from)
        if created_to is not None:
            add("q.created_at <= %s", created_to)
        if submitted_from is not None:
            add("(q.payload->'review_submission'->>'submitted_at')::timestamptz >= %s",
                submitted_from)
        if submitted_to is not None:
            add("(q.payload->'review_submission'->>'submitted_at')::timestamptz <= %s",
                submitted_to)
        if subject_id:
            add("q.subject_id=%s", str(object_id(subject_id, "subject_id")))
        if approved_current_only:
            add("q.approved_version_id=q.current_version_id")
        if creator_user_id is not None:
            add("(q.created_by_user_id=%s OR v.created_by_user_id=%s)",
                str(creator_user_id), str(creator_user_id))
        if owner_user_id is not None:
            add("(q.created_by_user_id=%s OR v.created_by_user_id=%s)",
                str(owner_user_id), str(owner_user_id))
        if visible_to_user_id is not None:
            uid = str(visible_to_user_id)
            add("""(q.created_by_user_id=%s OR v.created_by_user_id=%s
                 OR q.payload->'shared_with_user_ids' ? %s
                 OR q.payload->>'shared_scope'='SUBJECT')""", uid, uid, uid)
        if question_type:
            add("v.classification->>'assessment_type'=%s", question_type.upper())
        if bloom_level is not None:
            add("(v.classification->'bloom'->>'level')::integer=%s", int(bloom_level))
        if document_id:
            add("v.payload->>'document_id'=%s", str(object_id(document_id, "document_id")))
        if chapter_id:
            add("v.classification->'chapter'->>'id'=%s",
                str(object_id(chapter_id, "chapter_id")))
        if clo_id:
            add("v.clos @> %s::jsonb", '[{"id":"' + str(object_id(clo_id, "clo_id")) + '"}]')
        if difficulty:
            add("v.classification->>'difficulty'=%s", difficulty)
        if source_presence == "WITH_SOURCE":
            add("jsonb_array_length(v.sources)>0")
        elif source_presence == "MISSING_SOURCE":
            add("jsonb_array_length(v.sources)=0")
        if search:
            pattern = f"%{search}%"
            add("(q.question_code ILIKE %s OR v.content ILIKE %s)", pattern, pattern)

        base_where = " AND ".join(clauses)
        status_clause = ""
        status_params = []
        if review_status == "PROCESSED":
            status_clause = " AND q.review_status=ANY(%s)"
            status_params = [["APPROVED", "NEEDS_REVISION", "REJECTED"]]
        elif review_status:
            status_clause = " AND q.review_status=%s"
            status_params = [review_status]
        source = " FROM questions q JOIN question_versions v ON v.id=q.current_version_id WHERE "
        order = {
            "oldest": "q.created_at, q.id",
            "newest": "q.created_at DESC, q.id DESC",
            "updated": "q.updated_at DESC, q.id DESC",
            "ai_lowest": "(q.payload->'quality_summary'->>'overall_score')::numeric NULLS LAST, q.id",
            "priority": """CASE
                WHEN q.assignment->>'status'='IN_REVIEW'
                     AND (q.assignment->>'lock_expires_at')::timestamptz <= now() THEN 0
                WHEN q.review_status='PENDING' AND
                     (q.payload->'review_submission'->>'submitted_at')::timestamptz <=
                     now() - interval '24 hours' THEN 1
                WHEN q.payload->'secondary_review'->>'status'='AWAITING_SECONDARY' THEN 2
                WHEN q.payload->'quality_summary'->>'color'='RED'
                     AND q.evaluation_status IN ('PASSED','FAILED') THEN 3
                WHEN q.evaluation_status IN ('NOT_STARTED','ERROR','STALE') THEN 4
                ELSE 5 END,
                (q.payload->'review_submission'->>'submitted_at')::timestamptz NULLS LAST,
                q.id""",
        }.get(sort_by)
        if order is None:
            raise ValueError("Kiểu sắp xếp hàng kiểm duyệt không hợp lệ")
        with postgres_connection() as conn:
            total = conn.execute(
                "SELECT count(*) AS n" + source + base_where + status_clause,
                [*params, *status_params],
            ).fetchone()["n"]
            rows = conn.execute(
                "SELECT q.*" + source + base_where + status_clause
                + " ORDER BY " + order + " LIMIT %s OFFSET %s",
                [*params, *status_params, page_size, (page - 1) * page_size],
            ).fetchall()
            version_ids = [row["current_version_id"] for row in rows]
            version_rows = conn.execute(
                "SELECT * FROM question_versions WHERE id=ANY(%s)", (version_ids,),
            ).fetchall() if version_ids else []
            versions = {row["id"]: _version(row) for row in version_rows}
            pairs = [(_question(row), versions[row["current_version_id"]]) for row in rows]
            if include_status_counts:
                counts = conn.execute(
                    "SELECT q.review_status, count(*) AS n" + source + base_where
                    + " GROUP BY q.review_status", params,
                ).fetchall()
                return pairs, total, {row["review_status"]: row["n"] for row in counts}
        return pairs, total

    @staticmethod
    def _save_question(conn, question: dict) -> None:
        for table, row in projected_rows("questions", question):
            upsert(conn, table, row)

    @staticmethod
    def _save_version(conn, version: dict) -> None:
        for table, row in projected_rows("question_versions", version):
            upsert(conn, table, row)

    @staticmethod
    def _pair(conn, question_id: str | ObjectId, *, active_only: bool = True,
              lock: bool = False) -> tuple[dict, dict] | None:
        query = "SELECT * FROM questions WHERE id=%s"
        if active_only:
            query += " AND lifecycle_status='ACTIVE'"
        if lock:
            query += " FOR UPDATE"
        row = conn.execute(query, (str(object_id(question_id, "question_id")),)).fetchone()
        if not row:
            return None
        question = _question(row)
        version_row = conn.execute(
            "SELECT * FROM question_versions WHERE id=%s AND question_id=%s",
            (str(question["current_version_id"]), str(question["_id"])),
        ).fetchone()
        if not version_row:
            raise RuntimeError("Question aggregate bị thiếu current version")
        return question, _version(version_row)

    def find_pair(self, question_id: str | ObjectId) -> tuple[dict, dict] | None:
        with postgres_connection() as conn:
            return self._pair(conn, question_id)

    def create(self, aggregate: dict, version: dict) -> tuple[dict, dict]:
        with postgres_connection() as conn:
            self._save_question(conn, aggregate)
            self._save_version(conn, version)
        return aggregate, version

    def create_version(self, question_id: str | ObjectId, expected_version: int,
                       version: dict, *, review_submission: dict | None = None
                       ) -> tuple[dict, dict] | None:
        with postgres_connection() as conn:
            pair = self._pair(conn, question_id, lock=True)
            if not pair:
                return None
            question, current = pair
            if question["current_version"] != expected_version:
                raise RuntimeError("VERSION_CONFLICT")
            new_version = deepcopy(current)
            new_version.update(version)
            new_version.update(_id=ObjectId(), question_id=question["_id"],
                               version=expected_version + 1)
            now = utc_now()
            question.update({
                "current_version": expected_version + 1,
                "current_version_id": new_version["_id"],
                "evaluation_status": "NOT_STARTED",
                "review_status": "DRAFT",
                "publication_status": ("STALE" if question["publication_status"] == "PUBLISHED"
                                       else question["publication_status"]),
                "review_assignment": {
                    "status": "UNASSIGNED", "reviewer_user_id": None,
                    "assigned_by_user_id": None, "assigned_at": None,
                    "claimed_at": None, "lock_expires_at": None,
                    "last_released_at": None, "release_reason": None,
                },
                "review_submission": {}, "secondary_review": {},
                "quality_summary": {},
                "subject_id": ((new_version.get("classification") or {}).get("subject") or {}).get("id"),
                "updated_at": now,
            })
            self._save_version(conn, new_version)
            self._save_question(conn, question)
            return question, new_version

    def update_review_status(self, question_id: str | ObjectId,
                             allowed_statuses: set[str], review_status: str, *,
                             review_submission: dict | None = None
                             ) -> tuple[dict, dict] | None:
        with postgres_connection() as conn:
            pair = self._pair(conn, question_id, lock=True)
            if not pair or pair[0]["review_status"] not in allowed_statuses:
                return None
            question, version = pair
            now = utc_now()
            question["review_status"] = review_status
            question["review_assignment"] = {
                "status": "UNASSIGNED", "reviewer_user_id": None,
                "assigned_by_user_id": None, "assigned_at": None,
                "claimed_at": None, "lock_expires_at": None,
                "last_released_at": None, "release_reason": None,
            }
            question["updated_at"] = now
            if review_status == "PENDING" and review_submission:
                submitted = deepcopy(review_submission)
                submitted["submitted_at"] = now
                question["review_submission"] = submitted
            self._save_question(conn, question)
            return question, version

    def archive(self, question_id: str | ObjectId) -> bool:
        with postgres_connection() as conn:
            pair = self._pair(conn, question_id, lock=True)
            if not pair:
                return False
            question, _version_record = pair
            question.update(lifecycle_status="ARCHIVED", archived_at=utc_now(),
                            updated_at=utc_now())
            self._save_question(conn, question)
            return True

    def list_versions(self, question_id: str | ObjectId) -> list[dict]:
        key = str(object_id(question_id, "question_id"))
        with postgres_connection() as conn:
            if not conn.execute("SELECT 1 FROM questions WHERE id=%s", (key,)).fetchone():
                return []
            rows = conn.execute(
                "SELECT * FROM question_versions WHERE question_id=%s ORDER BY version DESC",
                (key,),
            ).fetchall()
        return [_version(row) for row in rows]

    def update_sharing(self, question_id: str | ObjectId,
                       fields: dict) -> tuple[dict, dict] | None:
        with postgres_connection() as conn:
            pair = self._pair(conn, question_id, lock=True)
            if not pair:
                return None
            question, version = pair
            normalized = dict(fields)
            if "shared_with_user_ids" in normalized:
                normalized["shared_with_user_ids"] = [
                    object_id(item, "shared_with_user_id")
                    for item in normalized.get("shared_with_user_ids") or []
                ]
            question.update(normalized)
            question["updated_at"] = utc_now()
            self._save_question(conn, question)
            return question, version
