from datetime import datetime, timezone

from bson import ObjectId

from db.copy_business_data import copy_business_data, reconcile_deleted_users


class _Collection:
    def __init__(self, items=()):
        self.items = list(items)

    def find(self, *_args, **_kwargs):
        return list(self.items)


class _Database(dict):
    def __missing__(self, _name):
        return _Collection()

    def __getattr__(self, name):
        return self[name]


def test_deleted_users_detach_audit_actors_and_skip_their_notifications():
    live = str(ObjectId())
    gone = str(ObjectId())
    users = {live}

    audit = {"id": "a1", "actor_user_id": gone, "payload": {"actor": {"user_id": gone}}}
    kept, action = reconcile_deleted_users("audit_logs", audit, users)
    assert action == "actor_detached"
    assert kept["actor_user_id"] is None
    assert kept["payload"]["actor"]["user_id"] == gone, "history keeps the original actor"

    skipped, action = reconcile_deleted_users("notifications", {"recipient_user_id": gone}, users)
    assert (skipped, action) == (None, "skipped")

    for table, row in (("audit_logs", {"actor_user_id": live}),
                       ("audit_logs", {"actor_user_id": None}),
                       ("notifications", {"recipient_user_id": live}),
                       # Other tables are never rewritten: the FK must fail loudly.
                       ("questions", {"created_by_user_id": gone})):
        assert reconcile_deleted_users(table, row, users) == (row, None)


def test_copy_reports_deleted_user_rows_without_writing():
    now = datetime.now(timezone.utc)
    live, gone = ObjectId(), ObjectId()
    database = _Database(
        users=_Collection([{"_id": live, "firebase_uid": "u", "email": "u@example.test",
                            "display_name": "U", "role": "Teacher",
                            "created_at": now, "updated_at": now}]),
        notifications=_Collection([
            {"_id": ObjectId(), "recipient_user_id": live, "type": "X", "created_at": now},
            {"_id": ObjectId(), "recipient_user_id": gone, "type": "X", "created_at": now},
        ]),
        audit_logs=_Collection([
            {"_id": ObjectId(), "action": "a", "actor": {"user_id": gone},
             "entity": {"type": "question"}, "created_at": now},
        ]),
    )
    counts = copy_business_data(database, None, apply=False)
    assert counts["notifications"] == 1
    assert counts["notifications (skipped: user deleted)"] == 1
    assert counts["audit_logs"] == 1
    assert counts["audit_logs (actor_detached: user deleted)"] == 1
