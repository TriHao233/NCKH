import hashlib
from datetime import datetime, timezone

from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database
from modules.documents.repository import object_id
from modules.questions.schemas import QuestionCreateRequest
from modules.questions.service import get_question_service

BLOOM_TO_LEVEL = {
    "nho": 1,
    "hieu": 2,
    "van_dung": 3,
    "phan_tich": 4,
    "danh_gia": 5,
    "sang_tao": 6,
}


def utc_now():
    return datetime.now(timezone.utc)


def create_generation_run(
    *,
    document_id: str,
    requested_by_user_id,
    request_snapshot: dict,
    model_snapshot: dict,
    rendered_prompt: str,
    context_text: str,
    retrieval_results: list[dict],
) -> str:
    document_oid = object_id(document_id, "document_id")
    document = get_database().documents.find_one({"_id": document_oid})
    if not document:
        raise ValueError("Không tìm thấy tài liệu")
    now = utc_now()
    record = {
        "_id": ObjectId(),
        "schema_version": SCHEMA_VERSION,
        "requested_by_user_id": requested_by_user_id,
        "document_id": document_oid,
        "document_version": document.get("current_version", 1),
        "chunk_set_id": (document.get("current_processing") or {}).get("chunk_set_id"),
        "subject": {"id": document.get("subject_id")},
        "chapter": {"id": document.get("chapter_id")},
        "request": request_snapshot,
        "model": model_snapshot,
        "prompts": [],
        "rendered_prompt": rendered_prompt,
        "rendered_prompt_hash": hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest(),
        "retrieval": {
            "context_hash": hashlib.sha256(context_text.encode("utf-8")).hexdigest(),
            "context_excerpt": context_text[:4000],
            "results": retrieval_results,
        },
        "execution": {
            "attempt_no": 1,
            "latency_ms": None,
            "parser_version": "question-json-v1",
        },
        "raw_model_response": None,
        "status": "GENERATING",
        "generated_count": 0,
        "validation_errors": [],
        "error": None,
        "created_at": now,
        "started_at": now,
        "finished_at": None,
    }
    get_database().generation_runs.insert_one(record)
    return str(record["_id"])


def finish_generation_run(
    generation_run_id: str,
    *,
    status: str,
    raw_model_response: str | None = None,
    generated_count: int = 0,
    latency_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    now = utc_now()
    get_database().generation_runs.update_one(
        {"_id": object_id(generation_run_id, "generation_run_id")},
        {
            "$set": {
                "status": status.upper(),
                "raw_model_response": raw_model_response,
                "generated_count": generated_count,
                "execution.latency_ms": latency_ms,
                "error": {"message": error_message, "at": now} if error_message else None,
                "finished_at": now,
            }
        },
    )


def save_generated_questions(
    document_id: str,
    questions: list,
    *,
    generation_run_id: str,
    requested_by_user_id,
    source_chunk_ids: list[str],
) -> int:
    service = get_question_service()
    run_oid = object_id(generation_run_id, "generation_run_id")
    for question in questions:
        service.create(
            QuestionCreateRequest(
                content=question["question"],
                question_type=question["question_type"],
                bloom_level=BLOOM_TO_LEVEL.get(question["bloom_level"]),
                question_data={
                    "options": question.get("options"),
                    "correct_answer": question.get("correct_answer"),
                    "explanation": question.get("explanation"),
                    "model_source_context": question.get("source_context"),
                },
                document_id=document_id,
                source_chunk_ids=source_chunk_ids,
            ),
            requested_by_user_id,
            origin="AI",
            generation_run_id=run_oid,
        )
    return len(questions)
