"""Infer conservative subject memberships from owned records.

The command is dry-run by default and uses upserts keyed by
``(user_id, subject_id, origin=BACKFILL)`` so ``--apply`` is repeatable.
It grants only TEACHER membership; reviewer scope must be assigned explicitly.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.bootstrap import SCHEMA_VERSION  # noqa: E402
from core.database import get_rag_db  # noqa: E402


def _valid_pair(user_id, subject_id):
    return isinstance(user_id, ObjectId) and isinstance(subject_id, ObjectId)


def collect_candidates(database) -> set[tuple[ObjectId, ObjectId]]:
    candidates: set[tuple[ObjectId, ObjectId]] = set()
    for record in database.documents.find(
        {"archived_at": None}, {"uploaded_by_user_id": 1, "subject_id": 1}
    ):
        pair = (record.get("uploaded_by_user_id"), record.get("subject_id"))
        if _valid_pair(*pair):
            candidates.add(pair)
    for record in database.questions.find(
        {"lifecycle_status": "ACTIVE"}, {"created_by_user_id": 1, "subject_id": 1}
    ):
        pair = (record.get("created_by_user_id"), record.get("subject_id"))
        if _valid_pair(*pair):
            candidates.add(pair)
    for record in database.exams.find({}, {"created_by_user_id": 1, "subject_id": 1}):
        pair = (record.get("created_by_user_id"), record.get("subject_id"))
        if _valid_pair(*pair):
            candidates.add(pair)
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    database = get_rag_db()
    candidates = collect_candidates(database)
    print(f"candidate memberships: {len(candidates)}")
    if not args.apply:
        print("dry-run only; pass --apply after reviewing subject ownership")
        return
    now = datetime.now(timezone.utc)
    changed = 0
    for user_id, subject_id in sorted(candidates, key=lambda pair: (str(pair[1]), str(pair[0]))):
        result = database.subject_memberships.update_one(
            {"user_id": user_id, "subject_id": subject_id, "origin": "BACKFILL"},
            {
                "$setOnInsert": {
                    "schema_version": SCHEMA_VERSION,
                    "roles": ["TEACHER"],
                    "capabilities": [],
                    "status": "ACTIVE",
                    "external_course_id": None,
                    "updated_at": now,
                    "created_by_user_id": None,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        changed += int(bool(result.upserted_id or result.modified_count))
    print(f"memberships changed: {changed}")


if __name__ == "__main__":
    main()
