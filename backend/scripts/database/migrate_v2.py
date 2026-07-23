"""Idempotent legacy-to-V2 migration. Dry-run is the default."""

import argparse
import sys
from pathlib import Path

from bson import ObjectId
from pymongo import ReturnDocument

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import SCHEMA_VERSION, bootstrap_database
from core.database import get_database, ping_database
from modules.documents.repository import MongoDocumentRepository, utc_now
from modules.questions.schemas import QuestionCreateRequest
from modules.questions.service import get_question_service


def migrated(source_collection: str, source_id) -> bool:
    return get_database().migration_id_map.find_one(
        {
            "source_collection": source_collection,
            "source_id": source_id,
            "status": "COMPLETED",
        }
    ) is not None


def record_mapping(source_collection: str, source_id, target_collection: str, target_id) -> None:
    get_database().migration_id_map.update_one(
        {"source_collection": source_collection, "source_id": source_id},
        {
            "$set": {
                "target_collection": target_collection,
                "target_id": target_id,
                "status": "COMPLETED",
                "updated_at": utc_now(),
            },
            "$setOnInsert": {"created_at": utc_now()},
        },
        upsert=True,
    )


def migrate_users(apply: bool) -> tuple[int, int]:
    db = get_database()
    source = db["UserInfo"]
    scanned = eligible = 0
    for legacy in source.find({}):
        scanned += 1
        if migrated("UserInfo", legacy["_id"]) or not legacy.get("uid"):
            continue
        eligible += 1
        if not apply:
            continue
        role = "Admin" if str(legacy.get("role", "")).lower() in {"admin", "quản trị"} else "Teacher"
        now = utc_now()
        target = db.users.find_one_and_update(
            {"firebase_uid": legacy["uid"]},
            {
                "$setOnInsert": {
                    "schema_version": SCHEMA_VERSION,
                    "firebase_uid": legacy["uid"],
                    "email": (
                        legacy.get("Email") or f"{legacy['uid']}@firebase.local"
                    ).lower(),
                    "display_name": legacy.get("Full name") or "Teacher",
                    "role": role,
                    "profile": {
                        "school": legacy.get("School", ""),
                        "address": legacy.get("Địa Chỉ", ""),
                        "avatar": legacy.get("avatar", ""),
                    },
                    "is_active": legacy.get("status", "active") == "active",
                    "created_at": legacy.get("created_at") or now,
                    "updated_at": now,
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        record_mapping("UserInfo", legacy["_id"], "users", target["_id"])
    return scanned, eligible


def migrate_documents(apply: bool) -> tuple[int, int]:
    db = get_database()
    repository = MongoDocumentRepository(db)
    legacy_documents = list(db.documents.find({"schema_version": {"$ne": SCHEMA_VERSION}}))
    scanned = eligible = 0
    for legacy in legacy_documents:
        scanned += 1
        if migrated("documents", legacy["_id"]):
            continue
        eligible += 1
        if not apply:
            continue
        target = repository.create(
            {
                "title": legacy.get("title") or "Legacy document",
                "original_filename": legacy.get("filename") or "legacy.pdf",
                "subject_id": None,
                "chapter_id": None,
            },
            None,
        )
        job = repository.create_job(str(target["_id"]), "OCR", {"migration": True})
        repository.update_job(str(job["_id"]), "PROCESSING", progress=50)
        pages = list(
            db.pages.find(
                {
                    "document_id": {
                        "$in": [str(legacy["_id"]), legacy["_id"]],
                    }
                }
            ).sort("page_number", 1)
        )
        repository.save_pages(
            str(target["_id"]),
            str(job["_id"]),
            [
                {
                    "page_number": page.get("page_number", 0),
                    "text": page.get("text", ""),
                    "original_text": page.get("original_text") or page.get("text", ""),
                }
                for page in pages
            ],
        )
        repository.update_job(
            str(job["_id"]),
            "COMPLETED",
            progress=100,
            stats={"migration": True, "total_pages": len(pages)},
        )
        record_mapping("documents", legacy["_id"], "documents", target["_id"])
    return scanned, eligible


def migrate_questions(apply: bool) -> tuple[int, int]:
    db = get_database()
    service = get_question_service()
    legacy_questions = list(db.questions.find({"schema_version": {"$ne": SCHEMA_VERSION}}))
    scanned = eligible = 0
    bloom_map = {
        "nho": 1,
        "hieu": 2,
        "van_dung": 3,
        "phan_tich": 4,
        "danh_gia": 5,
        "sang_tao": 6,
    }
    for legacy in legacy_questions:
        scanned += 1
        if migrated("questions", legacy["_id"]):
            continue
        content = legacy.get("question") or legacy.get("content") or ""
        if not content:
            continue
        eligible += 1
        if not apply:
            continue
        response = service.create(
            QuestionCreateRequest(
                content=content,
                question_type=legacy.get("question_type", "trac_nghiem"),
                bloom_level=bloom_map.get(str(legacy.get("bloom_level", "")).lower()),
                question_data={
                    "options": legacy.get("options"),
                    "correct_answer": legacy.get("correct_answer"),
                    "explanation": legacy.get("explanation"),
                    "model_source_context": legacy.get("source_context"),
                },
            ),
            None,
            origin="IMPORT",
        )
        record_mapping(
            "questions",
            legacy["_id"],
            "questions",
            ObjectId(response["id"]),
        )
    return scanned, eligible


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write migration results; without this flag only dry-run.",
    )
    args = parser.parse_args()
    if args.apply:
        bootstrap_database()
    else:
        ping_database()
    print(f"Migration mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    for name, result in (
        ("users", migrate_users(args.apply)),
        ("documents/pages", migrate_documents(args.apply)),
        ("questions", migrate_questions(args.apply)),
    ):
        print(f"{name}: scanned={result[0]}, eligible={result[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
