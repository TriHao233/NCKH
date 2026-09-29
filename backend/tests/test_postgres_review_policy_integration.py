"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.questions.postgres_review_policy import PostgresReviewPolicyRepository
from modules.questions.workflow_schemas import ReviewPolicyPayload
from modules.questions.workflow_service import QuestionWorkflowService
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_admin_review_policy_is_postgres_backed_and_audited(monkeypatch):
    monkeypatch.setattr(settings, "review_policy_store", "postgres")
    monkeypatch.setattr(settings, "user_store", "postgres")
    suffix = uuid4().hex[:12]
    admin = PostgresUserRepository().create({
        "firebase_uid": f"policy-{suffix}",
        "email": f"policy-{suffix}@example.test",
        "display_name": "Admin", "role": "Admin",
    })
    actor = SimpleNamespace(id=admin["_id"], role="Admin")
    workflow = QuestionWorkflowService(SimpleNamespace())
    subject_id = ObjectId()
    try:
        updated = workflow.update_review_policy(
            ReviewPolicyPayload(
                secondary_on_override=True, secondary_below_score=0.7,
                secondary_subject_ids=[str(subject_id), str(subject_id)],
            ), actor,
        )
        assert updated["secondary_on_override"] is True
        assert updated["secondary_below_score"] == 0.7
        assert updated["secondary_subject_ids"] == [str(subject_id)]
        assert PostgresReviewPolicyRepository().get()["secondary_subject_ids"] == [subject_id]
        reasons = workflow._policy_secondary_reasons(
            {"subject_id": subject_id, "evaluation_status": "PASSED",
             "quality_summary": {"overall_score": 0.6}},
            SimpleNamespace(override=SimpleNamespace(applied=True)),
        )
        assert len(reasons) == 3
        with postgres_connection() as conn:
            audit = conn.execute(
                "SELECT actor_user_id, after_state FROM audit_logs "
                "WHERE action='REVIEW_POLICY_UPDATED' AND actor_user_id=%s",
                (str(admin["_id"]),),
            ).fetchone()
        assert audit["after_state"]["secondary_subject_ids"] == [str(subject_id)]
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM audit_logs WHERE action='REVIEW_POLICY_UPDATED' "
                         "AND actor_user_id=%s", (str(admin["_id"]),))
            conn.execute("DELETE FROM review_settings WHERE id='review_policy'")
            conn.execute("DELETE FROM users WHERE id=%s", (str(admin["_id"]),))


def test_shadow_copy_review_policy_preserves_existing_fields(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "postgres")
    now = datetime.now(timezone.utc)
    legacy = {"_id": "review_policy", "secondary_on_override": True,
              "secondary_below_score": 0.65,
              "secondary_subject_ids": [ObjectId()], "updated_at": now}
    try:
        with postgres_connection() as conn:
            for table, row in projected_rows("review_settings", legacy):
                upsert(conn, table, row)
        copied = PostgresReviewPolicyRepository().get()
        assert copied["secondary_on_override"] is True
        assert copied["secondary_below_score"] == 0.65
        assert copied["secondary_subject_ids"] == legacy["secondary_subject_ids"]
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM review_settings WHERE id='review_policy'")
