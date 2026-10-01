from datetime import datetime, timezone

from core import bootstrap
from modules.catalog.service import FALLBACK_EVALUATION_POLICY
from modules.questions.workflow_service import DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS

NAME = bootstrap.DEFAULT_POLICY_NAME
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


def _path(record: dict, path: str):
    value = record
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


class PolicyCollection:
    """The slice of a Mongo collection the policy seed uses."""

    def __init__(self, records=()):
        self.records = [dict(record) for record in records]

    def _matching(self, query: dict) -> list[dict]:
        return [record for record in self.records
                if all(_path(record, key) == value for key, value in query.items())]

    def find_one(self, query, _projection=None, sort=None):
        found = self._matching(query)
        for key, direction in reversed(sort or []):
            found.sort(key=lambda record: record[key], reverse=direction == -1)
        return found[0] if found else None

    def update_many(self, query, update):
        for record in self._matching(query):
            record.update(update["$set"])

    def update_one(self, query, update, upsert=False):
        if not self._matching(query) and upsert:
            self.records.append({**query, **update["$setOnInsert"]})


class Database:
    def __init__(self, records=()):
        self.evaluation_policies = PolicyCollection(records)

    def state(self) -> list[tuple[int, float, bool]]:
        return sorted(
            (record["version"], record["thresholds"]["pass_min"], record["is_active"])
            for record in self.evaluation_policies.records
            if record["policy_name"] == NAME
        )


def _policy(version: int, pass_min: float, active: bool, name: str = NAME) -> dict:
    return {
        "policy_name": name, "version": version, "is_active": active,
        "thresholds": {"yellow_min": 0.5, "green_min": max(0.75, pass_min), "pass_min": pass_min},
    }


def test_default_thresholds_agree_everywhere():
    assert DEFAULT_THRESHOLDS["pass_min"] == 0.70
    assert bootstrap.DEFAULT_POLICY_THRESHOLDS == DEFAULT_THRESHOLDS
    assert FALLBACK_EVALUATION_POLICY["thresholds"] == DEFAULT_THRESHOLDS
    assert bootstrap.DEFAULT_POLICY_WEIGHTS == DEFAULT_WEIGHTS


def test_new_database_gets_the_default_policy_active():
    db = Database()

    bootstrap._seed_evaluation_policy(db, NOW)

    assert db.state() == [(1, 0.70, True)]


def test_database_still_on_an_earlier_default_moves_to_the_current_one():
    # Databases created before the 0.65 default kept version 1 (0.80) active, because
    # version 2 was only activated when nothing else was.
    db = Database([_policy(1, 0.80, True), _policy(2, 0.65, False)])

    bootstrap._seed_evaluation_policy(db, NOW)

    assert db.state() == [(1, 0.80, False), (2, 0.65, False), (3, 0.70, True)]

    db = Database([_policy(2, 0.65, True)])
    bootstrap._seed_evaluation_policy(db, NOW)
    assert db.state() == [(2, 0.65, False), (3, 0.70, True)]


def test_policy_configured_by_an_admin_stays_active():
    db = Database([_policy(1, 0.80, False), _policy(2, 0.65, False), _policy(3, 0.85, True)])

    bootstrap._seed_evaluation_policy(db, NOW)

    assert db.state() == [(1, 0.80, False), (2, 0.65, False), (3, 0.85, True), (4, 0.70, False)]

    custom = _policy(1, 0.80, True, name="Chính sách của khoa")
    db = Database([custom])
    bootstrap._seed_evaluation_policy(db, NOW)
    assert db.state() == [(1, 0.70, False)]
    assert db.evaluation_policies.find_one({"policy_name": "Chính sách của khoa"})["is_active"]


def test_seed_runs_once():
    db = Database([_policy(1, 0.80, True)])
    bootstrap._seed_evaluation_policy(db, NOW)
    # An admin goes back to the old version afterwards: later startups leave it alone.
    for record in db.evaluation_policies.records:
        record["is_active"] = record["version"] == 1

    bootstrap._seed_evaluation_policy(db, NOW)

    assert db.state() == [(1, 0.80, True), (2, 0.70, False)]
