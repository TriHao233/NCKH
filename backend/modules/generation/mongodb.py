import hashlib
from datetime import datetime, timezone

from bson.errors import InvalidId
from bson.objectid import ObjectId

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database
from modules.documents.repository import object_id
from modules.questions.schemas import QuestionCreateRequest, QuestionDifficulty
from modules.questions.service import get_question_service

BLOOM_TO_LEVEL = {
    "1_nho": 1,
    "2_hieu": 2,
    "3_van_dung": 3,
    "4_phan_tich": 4,
    "5_danh_gia": 5,
    "6_sang_tao": 6,
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
            "parser_version": "question-json-v2",
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
    validation_errors: list[dict] | None = None,
    post_processing: dict | None = None,
) -> None:
    now = utc_now()
    fields = {
        "status": status.upper(),
        "raw_model_response": raw_model_response,
        "generated_count": generated_count,
        "execution.latency_ms": latency_ms,
        "error": {"message": error_message, "at": now} if error_message else None,
        "finished_at": now,
    }
    if validation_errors is not None:
        fields["validation_errors"] = validation_errors
    if post_processing is not None:
        fields["post_processing"] = post_processing
    get_database().generation_runs.update_one(
        {"_id": object_id(generation_run_id, "generation_run_id")},
        {"$set": fields},
    )


def get_existing_question_texts(document_id: str, *, limit: int = 2000) -> list[str]:
    """Load current active question text for post-generation deduplication only."""
    document_oid = object_id(document_id, "document_id")
    pipeline = [
        {
            "$match": {
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
                "current_version_id": {"$exists": True},
            }
        },
        {
            "$lookup": {
                "from": "question_versions",
                "localField": "current_version_id",
                "foreignField": "_id",
                "as": "current_version",
            }
        },
        {"$unwind": "$current_version"},
        {"$match": {"current_version.document_id": document_oid}},
        {"$project": {"_id": 0, "content": "$current_version.content"}},
        {"$limit": max(1, limit)},
    ]
    return [
        str(item.get("content") or "").strip()
        for item in get_database().questions.aggregate(pipeline)
        if str(item.get("content") or "").strip()
    ]


def save_generated_questions(
    document_id: str,
    questions: list,
    *,
    generation_run_id: str,
    requested_by_user_id,
    source_chunk_ids: list[str],
) -> list[dict]:
    service = get_question_service()
    run_oid = object_id(generation_run_id, "generation_run_id")
    saved_questions = []
    allowed_difficulties = {item.value for item in QuestionDifficulty}
    for question in questions:
        difficulty = question.get("difficulty")
        if difficulty not in allowed_difficulties:
            difficulty = None
        saved_question = service.create(
            QuestionCreateRequest(
                content=question["question"],
                question_type=question["question_type"],
                bloom_level=BLOOM_TO_LEVEL.get(question["bloom_level"]),
                difficulty=difficulty,
                question_data={
                    "options": question.get("options"),
                    "correct_answer": question.get("correct_answer"),
                    "explanation": question.get("explanation"),
                    "model_source_context": question.get("source_context"),
                    "source_keywords": question.get("source_keywords") or [],
                    "false_mutation": question.get("false_mutation"),
                    "post_processing": {
                        "status": "ACCEPTED",
                        "validator_version": "question-post-v2",
                    },
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
):
    """Cập nhật trạng thái job sinh câu hỏi."""
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

    db["generation_jobs"].update_one({"_id": ObjectId(job_id)}, {"$set": update_data})


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
