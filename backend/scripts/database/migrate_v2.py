"""Idempotent legacy-to-V2 migration. Dry-run is the default."""

import argparse
import sys
from pathlib import Path

from bson import ObjectId
from pymongo import ReturnDocument

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import SCHEMA_VERSION, bootstrap_database
from core.database import get_auth_db, get_database, get_rag_db, ping_database
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
    auth_db = get_auth_db()
    rag_db = get_rag_db()
    sources = (
        ("NCKH.UserInfo", auth_db["UserInfo"]),
        ("NCKH.users", auth_db["users"]),
        ("rag_database.users", rag_db["users"]),
    )
    scanned = eligible = 0
    for source_name, source in sources:
        for legacy in source.find({}):
            scanned += 1
            uid = legacy.get("firebase_uid") or legacy.get("uid")
            if not uid:
                continue
            if (
                migrated(source_name, legacy["_id"])
                and rag_db.users.find_one({"firebase_uid": uid}, {"_id": 1})
                and auth_db["User"].find_one({"uid": uid}, {"_id": 1})
            ):
                continue
            eligible += 1
            if not apply:
                continue
            now = utc_now()
            role = (
                "Admin"
                if str(legacy.get("role", "")).lower() in {"admin", "quản trị"}
                else "Teacher"
            )
            legacy_email = (
                legacy.get("email") or legacy.get("Email") or f"{uid}@firebase.local"
            ).lower()
            legacy_display_name = (
                legacy.get("display_name") or legacy.get("Full name") or "Teacher"
            )
            legacy_is_active = legacy.get(
                "is_active", legacy.get("status", "active") == "active"
            )
            legacy_profile = legacy.get("profile") or {}
            legacy_school = legacy_profile.get("school") or legacy.get("School", "")
            legacy_address = legacy_profile.get("address") or legacy.get("Địa Chỉ", "")
            legacy_avatar = legacy_profile.get("avatar") or legacy.get("avatar", "")
            legacy_created_at = legacy.get("created_at") or now

            def fallback_to_legacy(field_path: str, legacy_value):
                # Only fill from legacy data when the existing document's field is
                # missing or blank, so a doc created via normal signup/login never
                # gets its already-populated data clobbered by a stale import.
                return {
                    "$cond": [
                        {"$in": [{"$ifNull": [f"${field_path}", ""]}, ["", None]]},
                        legacy_value,
                        f"${field_path}",
                    ]
                }

            target = rag_db.users.find_one_and_update(
                {"firebase_uid": uid},
                [
                    {
                        "$set": {
                            "schema_version": {"$ifNull": ["$schema_version", SCHEMA_VERSION]},
                            "firebase_uid": uid,
                            "email": fallback_to_legacy("email", legacy_email),
                            "display_name": fallback_to_legacy("display_name", legacy_display_name),
                            "role": {"$ifNull": ["$role", role]},
                            "profile": {
                                "$mergeObjects": [
                                    {"school": "", "address": "", "avatar": ""},
                                    {"$ifNull": ["$profile", {}]},
                                    {
                                        "school": fallback_to_legacy("profile.school", legacy_school),
                                        "address": fallback_to_legacy("profile.address", legacy_address),
                                        "avatar": fallback_to_legacy("profile.avatar", legacy_avatar),
                                    },
                                ]
                            },
                            "is_active": {"$ifNull": ["$is_active", legacy_is_active]},
                            "created_at": {"$ifNull": ["$created_at", legacy_created_at]},
                            "updated_at": now,
                        }
                    }
                ],
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            token = legacy.get("token")
            existing_session = auth_db["User"].find_one({"uid": uid})
            normalized_token = (
                token
                if token is not None
                else (existing_session or {}).get("token")
            )
            auth_db["User"].replace_one(
                {"uid": uid},
                {"uid": uid, "token": normalized_token},
                upsert=True,
            )
            record_mapping(source_name, legacy["_id"], "users", target["_id"])
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
