import hashlib
from datetime import datetime, timezone
from typing import Callable

from bson.errors import InvalidId
from bson.objectid import ObjectId
from pymongo import ReturnDocument

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


def _model_snapshot(database, provider: str, fallback: dict | None = None) -> dict:
    model = database.ai_models.find_one({"model_code": provider, "is_active": True})
    if not model:
        return fallback or {"provider": provider}
    return {
        "id": model["_id"],
        "model_code": model["model_code"],
        "model_name": model.get("model_name"),
        "runtime": model.get("runtime"),
        "revision": model.get("revision"),
        "capabilities": model.get("capabilities") or [],
        "is_local": model.get("is_local", True),
        "config": model.get("config") or {},
    }


def create_generation_run(
    *,
    document_id: str,
    requested_by_user_id,
    request_snapshot: dict,
    model_snapshot: dict,
    rendered_prompt: str,
    context_text: str,
    retrieval_results: list[dict],
    chunk_set_id: str,
    vector_collection_id: str,
) -> str:
    document_oid = object_id(document_id, "document_id")
    db = get_database()
    provider = model_snapshot.get("provider") or model_snapshot.get("model_code") or ""
    if provider:
        model_snapshot = _model_snapshot(db, provider, model_snapshot)
    document = db.documents.find_one({"_id": document_oid, "archived_at": None})
    if not document:
        raise ValueError("Không tìm thấy tài liệu")
    chunk_set_oid = object_id(chunk_set_id, "chunk_set_id")
    vector_collection_oid = object_id(
        vector_collection_id,
        "vector_collection_id",
    )
    if not db.chunk_sets.find_one(
        {
            "_id": chunk_set_oid,
            "document_id": document_oid,
            "status": "COMPLETED",
        },
        {"_id": 1},
    ):
        raise ValueError("Chunk set truy xuất không hợp lệ")
    if not db.vector_collections.find_one(
        {"_id": vector_collection_oid, "is_active": True},
        {"_id": 1},
    ):
        raise ValueError("Vector collection truy xuất không hợp lệ")
    if any(
        result.get("chunk_set_id") != chunk_set_id
        for result in retrieval_results
    ):
        raise ValueError("Kết quả retrieval không cùng chunk set")
    now = utc_now()
    record = {
        "_id": ObjectId(),
        "schema_version": SCHEMA_VERSION,
        "requested_by_user_id": requested_by_user_id,
        "document_id": document_oid,
        "document_version": document.get("current_version", 1),
        "chunk_set_id": chunk_set_oid,
        "vector_collection_id": vector_collection_oid,
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
    db.generation_runs.insert_one(record)
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
    should_continue: Callable[[], bool] | None = None,
) -> list[dict]:
    service = get_question_service()
    run_oid = object_id(generation_run_id, "generation_run_id")
    saved_questions = []
    for question in questions:
        if should_continue is not None and not should_continue():
            raise RuntimeError("GENERATION_JOB_CANCELLED")
        saved_question = service.create(
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
            initial_review_status="DRAFT",
        )
        saved_questions.append(
            {
                **question,
                "question_id": saved_question["id"],
                "question_code": saved_question["question_code"],
                "current_version": saved_question["current_version"],
                "current_version_id": saved_question["current_version_id"],
                "review_status": saved_question["review_status"],
            }
        )
    return saved_questions


def create_generation_job(request: dict, requested_by_user_id=None) -> str:
    """Tạo job sinh câu hỏi với trạng thái queued (dùng cho polling ở FE)."""
    db = get_database()
    now = utc_now()
    doc = {
        "request": request,
        "requested_by_user_id": requested_by_user_id,
        "status": "queued",
        "result": None,
        "metrics": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    result = db["generation_jobs"].insert_one(doc)
    return str(result.inserted_id)


def update_generation_job(
    job_id: str,
    status: str,
    result: dict | None = None,
    metrics: dict | None = None,
    error_message: str | None = None,
    expected_status: str | list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict | None:
    """Cập nhật job bằng compare-and-set để không ghi đè trạng thái kết thúc."""
    db = get_database()
    update_data: dict = {
        "status": status,
        "updated_at": utc_now(),
    }
    if result is not None:
        update_data["result"] = result
    if metrics is not None:
        update_data["metrics"] = metrics
    if error_message is not None:
        update_data["error_message"] = error_message

    try:
        query: dict = {"_id": ObjectId(job_id)}
    except InvalidId:
        return None
    if expected_status is not None:
        if isinstance(expected_status, str):
            query["status"] = expected_status
        else:
            query["status"] = {"$in": list(expected_status)}
    return db["generation_jobs"].find_one_and_update(
        query,
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
    )


def generation_job_has_status(job_id: str, status: str) -> bool:
    """Kiểm tra trạng thái hiện tại mà không làm biến đổi tài liệu job."""
    try:
        job_oid = ObjectId(job_id)
    except InvalidId:
        return False
    return get_database()["generation_jobs"].find_one(
        {"_id": job_oid, "status": status},
        {"_id": 1},
    ) is not None


def get_generation_job(job_id: str) -> dict | None:
    """Lấy thông tin job sinh câu hỏi theo job_id."""
    db = get_database()
    try:
        doc = db["generation_jobs"].find_one({"_id": ObjectId(job_id)})
    except InvalidId:
        return None

    if not doc:
        return None

    doc["job_id"] = str(doc.pop("_id"))
    return doc
