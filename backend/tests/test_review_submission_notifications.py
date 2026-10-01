from types import SimpleNamespace
from unittest.mock import Mock

from bson import ObjectId
import pytest

from core.config import settings
from modules.notifications.service import NotificationService, submission_review_recipients
from modules.questions.router import submit_question_for_review
from modules.questions.postgres_repository import PostgresQuestionRepository
from test_schema_v2 import InMemoryCollection, _current_user


def fixture():
    author, subject = ObjectId(), ObjectId()
    qid, vid = ObjectId(), ObjectId()
    question = {"_id": qid, "schema_version": 2, "lifecycle_status": "ACTIVE", "question_code": "Q-SUBMIT",
                "created_by_user_id": author, "current_version_id": vid, "subject_id": subject}
    version = {"_id": vid, "created_by_user_id": author}
    specialist = {"_id": ObjectId(), "role": "Reviewer", "is_active": True, "review_subject_ids": [subject]}
    db = SimpleNamespace(questions=InMemoryCollection([question]), question_versions=InMemoryCollection([version]),
        question_reviews=InMemoryCollection(), notifications=InMemoryCollection(), users=InMemoryCollection([specialist]))
    return db, question, version, specialist


def test_first_submission_notifies_specialists_once_and_keeps_resubmission_behavior():
    db, question, _, specialist = fixture()
    notifier = NotificationService(db)
    kwargs = {"question_id": str(question["_id"]), "actor_user_id": question["created_by_user_id"]}
    result = notifier.notify_question_submitted(previous_review_status="DRAFT", **kwargs)
    assert [item["type"] for item in result] == ["QUESTION_SUBMITTED_FOR_REVIEW"]
    assert result[0]["link"] == f"/kiem-duyet?questionId={question['_id']}"
    assert notifier.notify_question_submitted(previous_review_status="PENDING", **kwargs) == []
    assert len(db.notifications.records) == 1
    reviewer = ObjectId()
    db.question_reviews.insert_one({"_id": ObjectId(), "question_id": question["_id"], "decision": "NEEDS_REVISION",
                                   "reviewer_user_id": reviewer})
    result = notifier.notify_question_submitted(previous_review_status="DRAFT", **kwargs)
    assert result[0]["type"] == "QUESTION_RESUBMITTED"
    assert db.notifications.records[-1]["recipient_user_id"] == reviewer
    assert len(db.notifications.records) == 2


def test_submission_targets_subject_specialists_without_broadcast_or_author_self_notification():
    _, question, version, specialist = fixture()
    users = [specialist, {**specialist, "_id": ObjectId(), "permission_revokes": ["reviews.manage"]},
             {**specialist, "_id": ObjectId(), "is_active": False},
             {**specialist, "_id": question["created_by_user_id"]},
             {**specialist, "_id": ObjectId(), "role": "Admin"},
             {**specialist, "_id": ObjectId(), "review_subject_ids": []}]
    kwargs = {"question": question, "version": version, "actor_user_id": question["created_by_user_id"]}
    assert submission_review_recipients(users, **kwargs) == [specialist["_id"]]
    assert submission_review_recipients(users[1:], **kwargs) == []
    assert submission_review_recipients(users, **{**kwargs, "question": {**question, "subject_id": None}}) == []


def test_postgres_submission_builds_transactional_outbox_and_failure_never_writes_mongo(monkeypatch):
    db, question, version, specialist = fixture()
    for key in ("question_store", "notification_store", "user_store", "catalog_store"):
        monkeypatch.setattr(settings, key, "postgres")
    monkeypatch.setattr(PostgresQuestionRepository, "find_pair", lambda *_a: (question, version))
    monkeypatch.setattr(PostgresQuestionRepository, "latest_review", lambda *_a: None)
    monkeypatch.setattr("modules.notifications.service.review_candidate_users", lambda *_a: [specialist])
    author = _current_user("Teacher", question["created_by_user_id"])
    service = Mock()
    service.get.return_value = {"review_status": "DRAFT"}
    service.submit_for_review.return_value = {"review_status": "PENDING", "evaluation_status": "PASSED"}
    workflow = SimpleNamespace(db=db)
    result = submit_question_for_review(str(question["_id"]), author, service, workflow)
    assert result["review_status"] == "PENDING"
    outbox = service.submit_for_review.call_args.kwargs["notifications"]
    assert len(outbox) == 1 and outbox[0]["recipient_user_id"] == specialist["_id"]
    assert outbox[0]["type"] == "QUESTION_SUBMITTED_FOR_REVIEW"
    assert db.notifications.records == []
    service.submit_for_review.side_effect = RuntimeError("failed transaction")
    with pytest.raises(RuntimeError, match="failed transaction"):
        submit_question_for_review(str(question["_id"]), author, service, workflow)
    assert db.notifications.records == []
