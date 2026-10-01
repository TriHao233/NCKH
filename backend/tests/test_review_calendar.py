from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId

from core.config import settings
from modules.users.calendar_service import review_assignment_to_events, review_backlog_event
from modules.users.repository import MongoUserRepository
from modules.users.service import UserService
from modules.users.schemas import CalendarResponse
from test_schema_v2 import InMemoryCollection

NOW = datetime(2026, 9, 30, 6, tzinfo=timezone.utc)


def question(state="IN_REVIEW", user_id=None, **extra):
    return {"_id": ObjectId(), "question_code": "Q-TEST", "lifecycle_status": "ACTIVE", "review_status": "PENDING",
            "review_assignment": {"status": state, "reviewer_user_id": user_id,
                "assigned_at": NOW - timedelta(hours=1), "claimed_at": NOW - timedelta(minutes=5),
                "lock_expires_at": NOW + timedelta(minutes=25)},
            "review_submission": {"submitted_at": NOW - timedelta(hours=2)}, **extra}


def events(item):
    return review_assignment_to_events(item, now=NOW, lock_timeout_minutes=30, assignment_timeout_hours=72, sla_hours=48)


def test_review_events_have_stable_ids_and_due_dates():
    item = question()
    event = events(item)[0]
    assert event["id"] == f"review_review_in_progress_{item['_id']}"
    assert event["event_type"] == "review_in_progress"
    assert event["due_date"] == NOW + timedelta(minutes=25)
    assert event["status"] == "todo" and event["priority"] == "high"
    assigned = events(question("ASSIGNED"))[0]
    assert assigned["event_type"] == "review_assigned" and assigned["priority"] == "medium"
    assert assigned["due_date"] == NOW + timedelta(hours=71)


def test_expired_lock_and_sla_and_inactive_questions():
    item = question()
    item["review_assignment"]["lock_expires_at"] = NOW - timedelta(minutes=1)
    assert events(item)[0]["status"] == "overdue"
    assigned = question("ASSIGNED", review_submission={"submitted_at": NOW - timedelta(hours=49)})
    assert events(assigned)[0]["priority"] == "high"
    assert "quá hạn xử lý" in events(assigned)[0]["description"]
    assigned["review_assignment"]["assigned_at"] = NOW - timedelta(hours=73)
    assert events(assigned)[0]["status"] == "overdue"
    assert events(question("UNASSIGNED")) == []
    assert events(question(review_status="APPROVED")) == []
    assert events(question(lifecycle_status="ARCHIVED")) == []
    item["review_assignment"]["lock_expires_at"] = None
    assert events(item)[0]["due_date"] == NOW + timedelta(minutes=25)
    item["review_assignment"]["claimed_at"] = (NOW - timedelta(minutes=5)).replace(tzinfo=None)
    assert events(item)[0]["due_date"] == NOW + timedelta(minutes=25)


def test_backlog_zero_and_priority():
    assert review_backlog_event(0, NOW) is None
    event = review_backlog_event(3, NOW)
    assert event["related_entity_type"] == "review_queue" and event["related_entity_id"] is None
    assert event["priority"] == "medium" and "3 câu" in event["title"]
    assert review_backlog_event(20, NOW)["priority"] == "high"


def test_mongo_calendar_assignment_scope_backlog_and_permission_revokes(monkeypatch):
    first, other, admin = ObjectId(), ObjectId(), ObjectId()
    users = [{"_id": first, "role": "Reviewer"}, {"_id": admin, "role": "Admin"}]
    held, foreign = question(user_id=first), question(user_id=other)
    unassigned = question("UNASSIGNED")
    db = SimpleNamespace(users=InMemoryCollection(users), documents=InMemoryCollection(),
                         questions=InMemoryCollection([held, foreign, unassigned]))
    repository = MongoUserRepository(db)
    service = UserService(repository, None, None)
    monkeypatch.setattr(settings, "review_lock_timeout_minutes", 30)
    with patch("modules.users.calendar_service.utc_now", return_value=NOW):
        result = service.get_calendar(str(first))
        assert [item["related_entity_id"] for item in result["items"]] == [str(held["_id"])]
        CalendarResponse.model_validate(result)
        admin_result = service.get_calendar(str(admin))
        assert admin_result["items"][0]["event_type"] == "review_unassigned_backlog"
        assert "1 câu" in admin_result["items"][0]["title"]
        CalendarResponse.model_validate(admin_result)
        repository.update(first, {"permission_revokes": ["reviews.manage"]})
        assert service.get_calendar(str(first))["items"] == []
