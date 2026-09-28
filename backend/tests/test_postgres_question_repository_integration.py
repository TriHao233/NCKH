"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.dependencies import CurrentUser
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.questions.postgres_repository import PostgresQuestionRepository
from modules.questions.workflow_service import QuestionWorkflowService
from modules.questions.workflow_schemas import (
    EvaluationCreateRequest, EvaluationScores, ReviewCreateRequest,
    ReviewDraftUpsertRequest, SecondaryReviewRequest,
)
from modules.questions.repository import serialize_question
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_question_versions_submit_sharing_and_archive_are_transactional(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "postgres")
    monkeypatch.setattr(settings, "catalog_store", "postgres")
    monkeypatch.setattr(settings, "notification_store", "postgres")
    suffix = uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    user = PostgresUserRepository().create({
        "firebase_uid": f"question-{suffix}",
        "email": f"question-{suffix}@example.test",
        "display_name": "Teacher", "role": "Teacher",
    })
    reviewer = PostgresUserRepository().create({
        "firebase_uid": f"review-{suffix}",
        "email": f"review-{suffix}@example.test",
        "display_name": "Reviewer", "role": "Reviewer",
    })
    subject_id = ObjectId()
    with postgres_connection() as conn:
        for table, row in projected_rows("subjects", {
            "_id": subject_id, "subject_code": f"Q-{suffix}",
            "subject_name": "Question subject", "created_at": now, "updated_at": now,
        }):
            upsert(conn, table, row)
    question_id, version_id = ObjectId(), ObjectId()
    aggregate = {
        "_id": question_id, "schema_version": 2,
        "question_code": f"Q-{suffix}", "subject_id": subject_id,
        "created_by_user_id": user["_id"],
        "current_version": 1, "current_version_id": version_id,
        "approved_version_id": None, "lifecycle_status": "ACTIVE",
        "review_status": "DRAFT", "evaluation_status": "NOT_STARTED",
        "publication_status": "NOT_PUBLISHED",
        "review_assignment": {"status": "UNASSIGNED"},
        "quality_summary": {}, "review_submission": {},
        "shared_scope": "PRIVATE", "shared_with_user_ids": [],
        "created_at": now, "updated_at": now,
    }
    version = {
        "_id": version_id, "question_id": question_id, "version": 1,
        "origin": "MANUAL", "content": "Câu hỏi một",
        "question_data": {"options": {"A": "đúng"}, "correct_answer": "A"},
        "classification": {"subject": {"id": subject_id}},
        "clos": [], "sources": [], "content_hash": f"hash-{suffix}-1",
        "created_by_user_id": user["_id"], "generation_run_id": None,
        "created_at": now,
    }
    repository = PostgresQuestionRepository()
    try:
        repository.create(aggregate, version)
        found = repository.find_pair(question_id)
        assert found[0]["current_version_id"] == version_id
        assert found[1]["content"] == "Câu hỏi một"
        assert found[1]["classification"]["subject"]["id"] == subject_id
        assert serialize_question(*found)["id"] == str(question_id)

        next_pair = repository.create_version(
            question_id, 1, {"content": "Câu hỏi hai",
                             "content_hash": f"hash-{suffix}-2"},
        )
        assert next_pair[0]["current_version"] == 2
        assert next_pair[1]["version"] == 2
        with pytest.raises(RuntimeError, match="VERSION_CONFLICT"):
            repository.create_version(question_id, 1, {"content": "stale"})
        assert [item["version"] for item in repository.list_versions(question_id)] == [2, 1]
        assert repository.list_versions(question_id)[1]["content"] == "Câu hỏi một"

        monkeypatch.setattr(settings, "question_store", "postgres")
        workflow = QuestionWorkflowService(SimpleNamespace())
        scoring_job_id = ObjectId()
        with postgres_connection() as conn:
            for table, row in projected_rows("evaluation_jobs", {
                "_id": scoring_job_id, "question_id": question_id,
                "question_version_id": next_pair[1]["_id"],
                "requested_by_user_id": user["_id"],
                "status": "PROCESSING", "evaluator_model_code": "gemini",
                "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
        evaluation = workflow.evaluate(
            str(question_id), EvaluationCreateRequest(
                expected_version=2,
                scores=EvaluationScores(
                    faithfulness=0.9, contextual_relevancy=0.9,
                    answer_relevancy=0.9, bloom_alignment=0.9,
                    clo_alignment=0.9,
                ),
                model_snapshot={"model_code": "gemini"},
                policy_snapshot={
                    "version": 1,
                    "weights": {key: 0.2 for key in (
                        "faithfulness", "contextual_relevancy",
                        "answer_relevancy", "bloom_alignment", "clo_alignment")},
                    "thresholds": {"yellow_min": 0.5, "green_min": 0.75,
                                   "pass_min": 0.65},
                },
                evaluation_job_id=str(scoring_job_id),
            ), user["_id"], require_active_job=True,
        )
        assert evaluation["passed"] is True
        assert repository.find_pair(question_id)[0]["evaluation_status"] == "PASSED"
        assert repository.find_pair(question_id)[0]["quality_summary"]["color"] == "GREEN"
        with postgres_connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM question_evaluations WHERE question_id=%s",
                                (str(question_id),)).fetchone()["n"] == 1
            conn.execute("UPDATE evaluation_jobs SET status='COMPLETED' WHERE id=%s",
                         (str(scoring_job_id),))

        submitted = repository.update_review_status(
            question_id, {"DRAFT"}, "PENDING",
            review_submission={"submitted_by_user_id": user["_id"]},
        )
        assert submitted[0]["review_status"] == "PENDING"
        assert submitted[0]["review_submission"]["submitted_by_user_id"] == user["_id"]
        assert repository.update_review_status(question_id, {"DRAFT"}, "PENDING") is None

        reviewer_actor = CurrentUser(
            id=reviewer["_id"], firebase_uid="", email="reviewer@example.test",
            role="Reviewer", is_active=True, permissions=("reviews.manage",),
        )
        assert workflow.claim_review(str(question_id), reviewer_actor)["review_assignment"]["status"] == "IN_REVIEW"
        assert workflow.release_review(str(question_id), reviewer_actor)["review_assignment"]["status"] == "UNASSIGNED"

        claimed = repository.claim_review(
            question_id, actor_user_id=reviewer["_id"], actor_role="Reviewer",
            lock_expires_at=now + timedelta(hours=1), now=now,
        )
        assert claimed[0]["review_assignment"]["reviewer_user_id"] == reviewer["_id"]
        with pytest.raises(PermissionError, match="Reviewer khác"):
            repository.claim_review(
                question_id, actor_user_id=ObjectId(), actor_role="Reviewer",
                lock_expires_at=now + timedelta(hours=1), now=now,
            )
        renewed = repository.renew_review(
            question_id, actor_user_id=reviewer["_id"],
            lock_expires_at=now + timedelta(hours=2), now=now,
        )
        assert renewed[0]["review_assignment"]["lock_expires_at"] == now + timedelta(hours=2)
        released = repository.release_review(
            question_id, actor_user_id=reviewer["_id"], actor_role="Reviewer",
            assignment={"status": "UNASSIGNED", "reviewer_user_id": None}, now=now,
        )
        assert released[0]["review_assignment"]["status"] == "UNASSIGNED"
        with postgres_connection() as conn:
            assert conn.execute(
                "SELECT count(*) AS n FROM audit_logs WHERE entity_id=%s",
                (str(question_id),),
            ).fetchone()["n"] == 5
        draft = workflow.save_review_draft(
            str(question_id), ReviewDraftUpsertRequest(
                expected_version=2, decision="APPROVED", draft={"overall_note": "Đạt"}),
            reviewer_actor,
        )
        assert workflow.get_review_draft(str(question_id), reviewer_actor)["_id"] == draft["_id"]
        saved_again = repository.save_review_draft(
            question_id, reviewer["_id"], expected_version=2,
            decision="NEEDS_REVISION", draft={"overall_note": "Sửa"},
        )
        assert str(saved_again["_id"]) == draft["_id"]
        assert saved_again["decision"] == "NEEDS_REVISION"

        comment_id = ObjectId()
        comment = repository.add_comment({
            "_id": comment_id, "question_id": question_id,
            "question_version_id": next_pair[1]["_id"],
            "author_user_id": reviewer["_id"], "body": "Nhận xét",
            "mention_user_ids": [user["_id"]],
            "created_at": now, "updated_at": now,
        }, actor_role="Reviewer")
        assert comment["body"] == "Nhận xét"
        assert workflow.list_comments(str(question_id), reviewer_actor)["items"][0]["_id"] == str(comment_id)
        with pytest.raises(PermissionError):
            repository.change_comment(question_id, comment_id,
                                      actor_user_id=user["_id"], actor_role="Teacher",
                                      body="Không được")
        edited = repository.change_comment(question_id, comment_id,
                                           actor_user_id=reviewer["_id"],
                                           actor_role="Reviewer", body="Đã sửa")
        assert edited["body"] == "Đã sửa"
        repository.change_comment(question_id, comment_id,
                                  actor_user_id=reviewer["_id"],
                                  actor_role="Reviewer", delete=True)
        assert repository.list_comments(question_id) == []

        shared = repository.update_sharing(question_id, {
            "shared_scope": "SUBJECT", "shared_with_user_ids": [user["_id"]],
        })
        assert shared[0]["shared_scope"] == "SUBJECT"
        assert shared[0]["shared_with_user_ids"] == [user["_id"]]
        listed, total, status_counts = repository.list(
            1, 10, "PENDING", "Câu hỏi hai", subject_id=str(subject_id),
            question_type=None, visible_to_user_id=user["_id"],
            include_status_counts=True,
        )
        assert total == 1 and listed[0][0]["_id"] == question_id
        assert status_counts == {"PENDING": 1}
        assert repository.list(1, 10, "APPROVED", None)[1] == 0
        assert repository.list(1, 10, None, None, source_presence="MISSING_SOURCE")[1] == 1
        with postgres_connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM question_versions WHERE question_id=%s",
                                (str(question_id),)).fetchone()["n"] == 2
        repository.claim_review(
            question_id, actor_user_id=reviewer["_id"], actor_role="Reviewer",
            lock_expires_at=now + timedelta(hours=1), now=now,
        )
        evaluation_job_id = ObjectId()
        with postgres_connection() as conn:
            for table, row in projected_rows("evaluation_jobs", {
                "_id": evaluation_job_id, "question_id": question_id,
                "question_version_id": next_pair[1]["_id"],
                "requested_by_user_id": user["_id"],
                "status": "QUEUED", "evaluator_model_code": "gemini",
                "created_at": now, "updated_at": now,
            }):
                upsert(conn, table, row)
        assert repository.active_evaluation_job_ids(question_id) == [evaluation_job_id]
        reviewed = workflow.review(
            str(question_id), ReviewCreateRequest(expected_version=2,
                                                  decision="APPROVED", note="Đạt"),
            reviewer_actor,
        )
        review_id = ObjectId(reviewed["_id"])
        decided = repository.find_pair(question_id)[0]
        assert decided["review_status"] == "APPROVED"
        assert decided["approved_version_id"] == next_pair[1]["_id"]
        assert repository.find_review(review_id)["reviewer_user_id"] == reviewer["_id"]
        assert repository.get_review_draft(question_id, reviewer["_id"]) is None
        with pytest.raises(RuntimeError, match="VERSION_CONFLICT"):
            repository.record_review(
                {"_id": ObjectId(), "question_id": question_id,
                 "question_version_id": next_pair[1]["_id"],
                 "reviewer_user_id": reviewer["_id"], "decision": "APPROVED",
                 "reviewed_at": now},
                {"review_status": "APPROVED"},
                expected_version_id=next_pair[1]["_id"],
                expected_latest_review_id=None, actor_role="Reviewer",
                audit_action="QUESTION_APPROVED",
            )
        with postgres_connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM question_reviews WHERE question_id=%s",
                                (str(question_id),)).fetchone()["n"] == 1
            assert conn.execute("SELECT status FROM evaluation_jobs WHERE id=%s",
                                (str(evaluation_job_id),)).fetchone()["status"] == "CANCELLED"
        secondary = repository.set_secondary_review(
            question_id, expected_version_id=next_pair[1]["_id"],
            expected_review_status="APPROVED",
            fields={
                "review_status": "PENDING", "approved_version_id": None,
                "secondary_review": {
                    "required": True, "status": "AWAITING_SECONDARY",
                    "primary_review_id": review_id,
                    "primary_reviewer_user_id": reviewer["_id"],
                },
                "review_assignment": {"status": "UNASSIGNED"},
                "updated_at": datetime.now(timezone.utc),
            },
            actor_user_id=user["_id"], actor_role="Admin",
            reason="Two reviewers required",
        )
        assert secondary[0]["review_status"] == "PENDING"
        assert secondary[0]["approved_version_id"] is None
        assert secondary[0]["secondary_review"]["primary_review_id"] == review_id
        admin_actor = CurrentUser(
            id=user["_id"], firebase_uid="", email="admin@example.test",
            role="Admin", is_active=True,
        )
        configured = workflow.set_secondary_review(
            str(question_id), SecondaryReviewRequest(required=True, reason="Double check"),
            admin_actor,
        )
        assert configured["secondary_review"]["status"] == "AWAITING_SECONDARY"
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(
                repository.create_version, question_id, 2,
                {"content": f"Đồng thời {index}",
                 "content_hash": f"hash-{suffix}-race-{index}"},
            ) for index in (1, 2)]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except RuntimeError as exc:
                    outcomes.append(str(exc))
        assert sum(isinstance(result, tuple) for result in outcomes) == 1
        assert outcomes.count("VERSION_CONFLICT") == 1
        assert repository.find_pair(question_id)[0]["current_version"] == 3
        assert [item["version"] for item in repository.list_versions(question_id)] == [3, 2, 1]
        assert repository.archive(question_id) is True
        assert repository.find_pair(question_id) is None
        assert repository.archive(question_id) is False
        assert len(repository.list_versions(question_id)) == 3
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM notifications WHERE recipient_user_id=ANY(%s)",
                         ([str(user["_id"]), str(reviewer["_id"])],))
            conn.execute("DELETE FROM audit_logs WHERE entity_id=%s", (str(question_id),))
            conn.execute("DELETE FROM question_comments WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM question_review_drafts WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM question_reviews WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM question_evaluations WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM evaluation_jobs WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("UPDATE questions SET current_version_id=NULL, approved_version_id=NULL "
                         "WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM question_versions WHERE question_id=%s",
                         (str(question_id),))
            conn.execute("DELETE FROM questions WHERE id=%s", (str(question_id),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject_id),))
            conn.execute("DELETE FROM users WHERE id=%s", (str(user["_id"]),))
            conn.execute("DELETE FROM users WHERE id=%s", (str(reviewer["_id"]),))
