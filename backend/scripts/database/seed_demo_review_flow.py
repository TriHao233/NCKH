"""Seed one ready-to-review question for the Reviewer demo flow."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import SCHEMA_VERSION, bootstrap_database
from core.database import get_rag_db, ping_database


DEFAULT_TEACHER_EMAIL = "vpqcuong@gmail.com"
DEMO_REVIEWER_EMAIL = "reviewer@qbankctu.edu.vn"
DEMO_SUBJECT_CODE = "CTDL"
DEMO_CLO_CODE = "CLO-DEMO-CTDL-01"
DEMO_DOCUMENT_FILENAME = "demo-reviewer-flow.pdf"
DEMO_QUESTION_CODE = "Q-DEMO-REVIEW-001"

DEMO_CONTEXT = (
    "Bảng băm lưu trữ phần tử bằng cách ánh xạ khóa vào vị trí trong bảng. "
    "Khi hệ số tải (load factor) tăng cao, xác suất va chạm giữa các khóa "
    "cũng tăng, làm thao tác tìm kiếm và chèn kém hiệu quả hơn. Một cách xử "
    "lý phổ biến là mở rộng bảng và tái băm các khóa để giảm hệ số tải."
)

DEMO_CONTENT = (
    "Trong bảng băm, khi hệ số tải tăng cao thì hiện tượng nào thường xảy ra "
    "và cách xử lý phù hợp là gì?"
)

DEMO_OPTIONS = {
    "A": "Số va chạm tăng; cần mở rộng bảng và tái băm để giảm hệ số tải.",
    "B": "Số va chạm giảm; cần thu nhỏ bảng để tiết kiệm bộ nhớ.",
    "C": "Độ phức tạp tìm kiếm luôn giữ O(1) tuyệt đối nên không cần xử lý.",
    "D": "Các khóa tự động được sắp xếp tăng dần trong từng bucket.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or refresh one pending question so reviewer/reviewer can run "
            "AI evaluation and review actions immediately."
        )
    )
    parser.add_argument(
        "--teacher-email",
        default=DEFAULT_TEACHER_EMAIL,
        help="Teacher owner email for the demo document/question.",
    )
    return parser.parse_args()


def stable_hash(payload: dict) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def find_teacher(db, email: str) -> dict:
    teacher = db.users.find_one(
        {"email": email.lower(), "role": "Teacher", "is_active": True}
    )
    if teacher:
        return teacher

    teacher = db.users.find_one(
        {"role": "Teacher", "is_active": True},
        sort=[("updated_at", -1)],
    )
    if teacher:
        print(
            "Teacher owner fallback: "
            f"{teacher.get('email')} ({teacher.get('_id')}); requested={email}"
        )
        return teacher

    raise SystemExit(
        "No active Teacher user found. Login/register a Teacher first or pass "
        "--teacher-email."
    )


def ensure_demo_clo(db, subject: dict, now: datetime) -> dict:
    for clo in subject.get("learning_outcomes") or []:
        if clo.get("clo_code") == DEMO_CLO_CODE or clo.get("code") == DEMO_CLO_CODE:
            return clo

    clo = {
        "_id": ObjectId(),
        "clo_code": DEMO_CLO_CODE,
        "description": "Giải thích tác động của hệ số tải lên hiệu năng bảng băm.",
        "target_weight": 1.0,
        "is_active": True,
    }
    db.subjects.update_one(
        {"_id": subject["_id"]},
        {
            "$push": {"learning_outcomes": clo},
            "$set": {"updated_at": now},
        },
    )
    return clo


def ensure_subject(db, now: datetime) -> tuple[dict, dict]:
    subject = db.subjects.find_one({"subject_code": DEMO_SUBJECT_CODE})
    if not subject:
        raise SystemExit(
            f"Subject {DEMO_SUBJECT_CODE} was not bootstrapped. "
            "Run bootstrap_database/verify_v2 first."
        )
    clo = ensure_demo_clo(db, subject, now)
    subject = db.subjects.find_one({"_id": subject["_id"]})
    return subject, clo


def ensure_document_pipeline(db, teacher: dict, subject: dict, now: datetime) -> tuple[dict, dict]:
    existing_document = db.documents.find_one(
        {
            "original_filename": DEMO_DOCUMENT_FILENAME,
            "uploaded_by_user_id": teacher["_id"],
        }
    )
    document_id = existing_document["_id"] if existing_document else ObjectId()

    existing_chunk_set_id = ((existing_document or {}).get("current_processing") or {}).get(
        "chunk_set_id"
    )
    existing_chunk_set = db.chunk_sets.find_one(
        {"document_id": document_id, "document_version": 1}
    )
    chunk_set_id = existing_chunk_set_id or (existing_chunk_set or {}).get("_id") or ObjectId()

    existing_chunk = db.document_chunks.find_one(
        {"chunk_set_id": chunk_set_id, "chunk_no": 1}
    )
    chunk_id = (existing_chunk or {}).get("_id") or ObjectId()
    context_hash = stable_hash({"content": DEMO_CONTEXT})

    document_fields = {
        "schema_version": SCHEMA_VERSION,
        "subject_id": subject["_id"],
        "chapter_id": None,
        "uploaded_by_user_id": teacher["_id"],
        "title": "Demo Reviewer Flow - Cấu trúc dữ liệu",
        "original_filename": DEMO_DOCUMENT_FILENAME,
        "status": "READY",
        "current_version": 1,
        "page_count": 1,
        "artifacts": [
            {
                "kind": "source_pdf",
                "path": "demo://reviewer-flow/demo-reviewer-flow.pdf",
                "mime_type": "application/pdf",
                "sha256": context_hash,
            }
        ],
        "current_processing": {
            "ocr_job_id": None,
            "chunk_job_id": None,
            "chunk_set_id": chunk_set_id,
            "ocr_status": "completed",
            "chunk_status": "completed",
        },
        "pipeline_summary": {
            "ocr_pages": 1,
            "chunks": 1,
            "vectorized_chunks": 0,
            "demo_seed": True,
        },
        "updated_at": now,
    }
    if existing_document:
        db.documents.update_one({"_id": document_id}, {"$set": document_fields})
    else:
        db.documents.insert_one(
            {
                "_id": document_id,
                **document_fields,
                "created_at": now,
            }
        )

    db.document_pages.update_one(
        {
            "document_id": document_id,
            "document_version": 1,
            "page_number": 1,
        },
        {
            "$set": {
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "document_version": 1,
                "page_number": 1,
                "text": DEMO_CONTEXT,
                "ocr_confidence": 0.99,
                "layout_blocks": [],
                "updated_at": now,
            },
            "$setOnInsert": {"_id": ObjectId(), "created_at": now},
        },
        upsert=True,
    )

    db.chunk_sets.update_one(
        {"_id": chunk_set_id},
        {
            "$set": {
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "document_version": 1,
                "chunking_strategy": "demo-fixed",
                "params": {"max_chars": len(DEMO_CONTEXT)},
                "chunk_count": 1,
                "content_hash": context_hash,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    chunk_fields = {
        "schema_version": SCHEMA_VERSION,
        "chunk_set_id": chunk_set_id,
        "document_id": document_id,
        "document_version": 1,
        "chunk_no": 1,
        "heading_path": ["Cấu trúc dữ liệu", "Bảng băm"],
        "page_start": 1,
        "page_end": 1,
        "content": DEMO_CONTEXT,
        "content_hash": context_hash,
        "tokens_estimate": max(1, len(DEMO_CONTEXT.split())),
        "quality_flags": [],
        "updated_at": now,
    }
    if existing_chunk:
        db.document_chunks.update_one({"_id": chunk_id}, {"$set": chunk_fields})
    else:
        db.document_chunks.insert_one(
            {
                "_id": chunk_id,
                **chunk_fields,
                "created_at": now,
            }
        )

    document = db.documents.find_one({"_id": document_id})
    chunk = db.document_chunks.find_one({"_id": chunk_id})
    return document, chunk


def ensure_demo_question(
    db,
    teacher: dict,
    subject: dict,
    clo: dict,
    document: dict,
    chunk: dict,
    now: datetime,
) -> tuple[dict, dict]:
    existing_question = db.questions.find_one({"question_code": DEMO_QUESTION_CODE})
    question_id = existing_question["_id"] if existing_question else ObjectId()

    existing_version = db.question_versions.find_one(
        {"question_id": question_id, "version": 1}
    )
    version_id = (
        (existing_question or {}).get("current_version_id")
        or (existing_version or {}).get("_id")
        or ObjectId()
    )

    classification = {
        "subject": {
            "id": subject["_id"],
            "code": subject.get("subject_code"),
            "name": subject.get("subject_name"),
        },
        "chapter": {"id": None},
        "assessment_type": "TRAC_NGHIEM",
        "bloom": {"level": 2, "code": "UNDERSTAND", "name": "Hiểu"},
    }
    clos = [
        {
            "id": clo["_id"],
            "code": clo.get("clo_code") or clo.get("code"),
            "description": clo.get("description", ""),
            "target_weight": clo.get("target_weight", 1.0),
        }
    ]
    sources = [
        {
            "source_type": "CHUNK",
            "chunk_id": chunk["_id"],
            "chunk_set_id": chunk["chunk_set_id"],
            "chunk_content_hash": chunk.get("content_hash"),
            "citation_order": 1,
            "is_primary": True,
            "scores": {"seed": 1.0},
            "context_excerpt": DEMO_CONTEXT,
        }
    ]
    question_data = {
        "options": DEMO_OPTIONS,
        "correct_answer": "A",
        "explanation": (
            "Hệ số tải cao làm tăng xác suất va chạm, vì vậy cần mở rộng bảng "
            "và tái băm để phân bố lại khóa."
        ),
    }
    content_hash = stable_hash(
        {
            "content": DEMO_CONTENT,
            "question_data": question_data,
            "classification": classification,
            "clos": clos,
            "sources": sources,
        }
    )

    question_fields = {
        "schema_version": SCHEMA_VERSION,
        "question_code": DEMO_QUESTION_CODE,
        "created_by_user_id": teacher["_id"],
        "current_version": 1,
        "current_version_id": version_id,
        "approved_version_id": None,
        "lifecycle_status": "ACTIVE",
        "evaluation_status": "NOT_STARTED",
        "review_status": "PENDING",
        "publication_status": "NOT_PUBLISHED",
        "quality_summary": {},
        "latest_review_id": None,
        "updated_at": now,
        "archived_at": None,
    }
    if existing_question:
        db.questions.update_one({"_id": question_id}, {"$set": question_fields})
    else:
        db.questions.insert_one(
            {
                "_id": question_id,
                **question_fields,
                "created_at": now,
            }
        )

    version_fields = {
        "schema_version": SCHEMA_VERSION,
        "question_id": question_id,
        "version": 1,
        "origin": "AI",
        "generation_run_id": None,
        "document_id": document["_id"],
        "created_by_user_id": teacher["_id"],
        "generated_by_model_id": None,
        "classification": classification,
        "clos": clos,
        "content": DEMO_CONTENT,
        "question_data": question_data,
        "sources": sources,
        "keywords": ["bảng băm", "hệ số tải", "va chạm", "tái băm"],
        "content_hash": content_hash,
        "change_note": "Demo reviewer seed",
        "created_at": now,
    }
    if existing_version:
        db.question_versions.update_one({"_id": existing_version["_id"]}, {"$set": version_fields})
        if existing_version["_id"] != version_id:
            db.questions.update_one(
                {"_id": question_id},
                {"$set": {"current_version_id": existing_version["_id"]}},
            )
            version_id = existing_version["_id"]
    else:
        db.question_versions.insert_one({"_id": version_id, **version_fields})

    question = db.questions.find_one({"_id": question_id})
    version = db.question_versions.find_one({"_id": version_id})
    return question, version


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)

    ping_database()
    bootstrap_database()
    db = get_rag_db()

    reviewer = db.users.find_one({"email": DEMO_REVIEWER_EMAIL, "role": "Reviewer"})
    if not reviewer:
        print(
            "Warning: reviewer demo account was not found in app DB. "
            "Run scripts/database/seed_demo_users.py if reviewer login is needed."
        )

    teacher = find_teacher(db, args.teacher_email)
    subject, clo = ensure_subject(db, now)
    document, chunk = ensure_document_pipeline(db, teacher, subject, now)
    question, version = ensure_demo_question(
        db,
        teacher,
        subject,
        clo,
        document,
        chunk,
        now,
    )

    print("Seeded reviewer demo flow")
    print(f"teacher={teacher.get('email')} ({teacher.get('_id')})")
    print(f"reviewer={DEMO_REVIEWER_EMAIL} present={bool(reviewer)}")
    print(f"document_id={document.get('_id')} status={document.get('status')}")
    print(
        f"question={question.get('question_code')} ({question.get('_id')}) "
        f"review={question.get('review_status')} evaluation={question.get('evaluation_status')} "
        f"version={version.get('version')}"
    )
    print("Reviewer can login with reviewer/reviewer, open /kiem-duyet, then run AI evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
