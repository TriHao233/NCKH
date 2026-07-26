"""Backfill document/question ownership fields for V2 access control."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import SCHEMA_VERSION
from core.database import get_rag_db, ping_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fill missing uploaded_by_user_id/created_by_user_id fields so "
            "Teacher ownership checks can work on legacy/demo data."
        )
    )
    owner = parser.add_mutually_exclusive_group()
    owner.add_argument("--owner-email", help="Fallback owner email.")
    owner.add_argument("--owner-id", help="Fallback owner ObjectId.")
    owner.add_argument("--owner-firebase-uid", help="Fallback owner Firebase UID.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    return parser.parse_args()


def needs_owner_query(field: str) -> dict:
    return {"$or": [{field: {"$exists": False}}, {field: None}]}


def resolve_owner(args: argparse.Namespace) -> dict:
    db = get_rag_db()
    query = None
    if args.owner_email:
        query = {"email": args.owner_email.lower()}
    elif args.owner_id:
        query = {"_id": ObjectId(args.owner_id)}
    elif args.owner_firebase_uid:
        query = {"firebase_uid": args.owner_firebase_uid}
    else:
        teachers = list(db.users.find({"role": "Teacher", "is_active": True}))
        if len(teachers) == 1:
            return teachers[0]
        emails = ", ".join(user.get("email", str(user["_id"])) for user in teachers) or "none"
        raise SystemExit(
            "Fallback owner is ambiguous. Pass --owner-email/--owner-id/--owner-firebase-uid. "
            f"Active Teacher users: {emails}"
        )
    user = db.users.find_one({**query, "is_active": True})
    if not user:
        raise SystemExit(f"Owner user not found or inactive: {query}")
    return user


def document_owner(db, document_id):
    if not document_id:
        return None
    document = db.documents.find_one({"_id": document_id}, {"uploaded_by_user_id": 1})
    return document.get("uploaded_by_user_id") if document else None


def question_owner_from_current_version(db, question: dict):
    current_version_id = question.get("current_version_id")
    if not current_version_id:
        return None
    version = db.question_versions.find_one(
        {"_id": current_version_id},
        {"created_by_user_id": 1, "document_id": 1},
    )
    if not version:
        return None
    return version.get("created_by_user_id") or document_owner(db, version.get("document_id"))


def backfill_documents(db, fallback_owner_id: ObjectId, apply: bool) -> int:
    query = {
        "schema_version": SCHEMA_VERSION,
        **needs_owner_query("uploaded_by_user_id"),
    }
    count = db.documents.count_documents(query)
    if apply and count:
        db.documents.update_many(
            query,
            {
                "$set": {
                    "uploaded_by_user_id": fallback_owner_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
    return count


def backfill_questions(db, fallback_owner_id: ObjectId, apply: bool) -> int:
    query = {
        "schema_version": SCHEMA_VERSION,
        **needs_owner_query("created_by_user_id"),
    }
    questions = list(db.questions.find(query, {"current_version_id": 1}))
    if apply:
        now = datetime.now(timezone.utc)
        for question in questions:
            owner_id = question_owner_from_current_version(db, question) or fallback_owner_id
            db.questions.update_one(
                {"_id": question["_id"]},
                {"$set": {"created_by_user_id": owner_id, "updated_at": now}},
            )
    return len(questions)


def backfill_question_versions(db, fallback_owner_id: ObjectId, apply: bool) -> int:
    query = {
        "schema_version": SCHEMA_VERSION,
        **needs_owner_query("created_by_user_id"),
    }
    versions = list(db.question_versions.find(query, {"document_id": 1, "question_id": 1}))
    if apply:
        for version in versions:
            question = db.questions.find_one(
                {"_id": version.get("question_id")},
                {"created_by_user_id": 1},
            )
            owner_id = (
                document_owner(db, version.get("document_id"))
                or (question or {}).get("created_by_user_id")
                or fallback_owner_id
            )
            db.question_versions.update_one(
                {"_id": version["_id"]},
                {"$set": {"created_by_user_id": owner_id}},
            )
    return len(versions)


def main() -> int:
    args = parse_args()
    ping_database()
    owner = resolve_owner(args)
    db = get_rag_db()
    owner_id = owner["_id"]
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Backfill ownership mode={mode}")
    print(f"Fallback owner={owner.get('email')} ({owner_id}) role={owner.get('role')}")
    print(f"documents={backfill_documents(db, owner_id, args.apply)}")
    print(f"questions={backfill_questions(db, owner_id, args.apply)}")
    print(f"question_versions={backfill_question_versions(db, owner_id, args.apply)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
