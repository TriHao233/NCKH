"""PostgreSQL source for Admin secondary-review policy."""

from __future__ import annotations

from bson import ObjectId
from psycopg.types.json import Jsonb

from core.postgres import postgres_connection
from core.postgres_audit import write_postgres_audit_event
from core.config import settings
from db.bson_json import restore
from db.copy_business_data import normalized
from modules.questions.workflow_schemas import ReviewPolicyPayload
from modules.questions.repository import utc_now


POLICY_ID = "review_policy"
POLICY_KEYS = ("secondary_on_override", "secondary_below_score", "secondary_subject_ids")


class PostgresReviewPolicyRepository:
    def __init__(self):
        if settings.user_store != "postgres":
            raise RuntimeError("REVIEW_POLICY_STORE=postgres requires USER_STORE=postgres")

    def get(self) -> dict:
        with postgres_connection() as conn:
            row = conn.execute("SELECT * FROM review_settings WHERE id=%s",
                               (POLICY_ID,)).fetchone()
        return self._record(row)

    @staticmethod
    def _record(row: dict | None) -> dict:
        if not row:
            return {"_id": POLICY_ID}
        record = restore(row["payload"] or {})
        record.update(_id=row["id"], updated_at=row["updated_at"],
                      updated_by_user_id=(ObjectId(row["updated_by_user_id"])
                                          if row["updated_by_user_id"] else None))
        return record

    def update(self, payload: ReviewPolicyPayload, actor_user_id: ObjectId,
               actor_role: str) -> dict:
        with postgres_connection() as conn:
            previous = conn.execute(
                "SELECT * FROM review_settings WHERE id=%s FOR UPDATE",
                (POLICY_ID,),
            ).fetchone()
            before = self._record(previous)
            now = utc_now()
            subject_ids = list(dict.fromkeys(
                ObjectId(item) for item in payload.secondary_subject_ids
            ))
            record = {
                "_id": POLICY_ID,
                "secondary_on_override": payload.secondary_on_override,
                "secondary_below_score": payload.secondary_below_score,
                "secondary_subject_ids": subject_ids,
                "updated_at": now, "updated_by_user_id": actor_user_id,
            }
            row = conn.execute(
                """INSERT INTO review_settings
                   (id, payload, updated_by_user_id, updated_at)
                   VALUES (%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET
                       payload=EXCLUDED.payload,
                       updated_by_user_id=EXCLUDED.updated_by_user_id,
                       updated_at=EXCLUDED.updated_at
                   RETURNING *""",
                (POLICY_ID, Jsonb(normalized(record)), str(actor_user_id), now),
            ).fetchone()
            after = self._record(row)
            write_postgres_audit_event(
                conn, action="REVIEW_POLICY_UPDATED", entity_type="review_policy",
                entity_id=POLICY_ID, actor_user_id=actor_user_id,
                actor_role=actor_role,
                before={key: normalized(before.get(key)) for key in POLICY_KEYS},
                after={key: normalized(after.get(key)) for key in POLICY_KEYS},
            )
        return after
