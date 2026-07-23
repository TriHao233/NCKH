import hashlib
import json

from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database
from modules.questions.repository import (
    MongoQuestionRepository,
    QuestionRepository,
    object_id,
    serialize_question,
    utc_now,
)
from modules.questions.schemas import QuestionCreateRequest, QuestionUpdateRequest

BLOOM_LEVELS = {
    1: ("REMEMBER", "Nhớ"),
    2: ("UNDERSTAND", "Hiểu"),
    3: ("APPLY", "Vận dụng"),
    4: ("ANALYZE", "Phân tích"),
    5: ("EVALUATE", "Đánh giá"),
    6: ("CREATE", "Sáng tạo"),
}


def stable_hash(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class QuestionService:
    def __init__(self, repository: QuestionRepository, database):
        self.repository = repository
        self.db = database

    def _sources(self, chunk_ids: list[str]) -> list[dict]:
        unique_chunk_ids = list(dict.fromkeys(chunk_ids))
        if not unique_chunk_ids:
            return []
        sources = []
        for citation_order, chunk_id in enumerate(unique_chunk_ids, start=1):
            chunk_oid = object_id(chunk_id, "chunk_id")
            chunk = self.db.document_chunks.find_one({"_id": chunk_oid})
            if not chunk:
                raise ValueError(f"Chunk không tồn tại: {chunk_id}")
            sources.append({
                "source_type": "CHUNK",
                "chunk_id": chunk_oid,
                "chunk_set_id": chunk["chunk_set_id"],
                "chunk_content_hash": chunk.get("content_hash"),
                "citation_order": citation_order,
                "is_primary": citation_order == 1,
                "scores": {},
                "context_excerpt": chunk.get("content", "")[:2000],
            })
        return sources

    @staticmethod
    def _classification(
        *,
        question_type: str,
        bloom_level: int | None,
        subject_id: str | None,
        chapter_id: str | None,
    ) -> dict:
        bloom_code, bloom_name = BLOOM_LEVELS.get(bloom_level, ("", ""))
        return {
            "subject": {"id": object_id(subject_id, "subject_id") if subject_id else None},
            "chapter": {"id": object_id(chapter_id, "chapter_id") if chapter_id else None},
            "assessment_type": question_type.upper(),
            "bloom": {
                "level": bloom_level,
                "code": bloom_code,
                "name": bloom_name,
            },
        }

    def create(
        self,
        payload: QuestionCreateRequest,
        created_by_user_id,
        *,
        origin: str = "MANUAL",
        generation_run_id: ObjectId | None = None,
    ) -> dict:
        now = utc_now()
        question_id = ObjectId()
        version_id = ObjectId()
        source_chunk_ids = payload.source_chunk_ids or (
            [payload.chunk_id] if payload.chunk_id else []
        )
        sources = self._sources(source_chunk_ids)
        classification = self._classification(
            question_type=payload.question_type,
            bloom_level=payload.bloom_level,
            subject_id=payload.subject_id,
            chapter_id=payload.chapter_id,
        )
        content_hash = stable_hash(
            {
                "content": payload.content,
                "question_data": payload.question_data,
                "classification": classification,
                "sources": sources,
            }
        )
        aggregate = {
            "_id": question_id,
            "schema_version": SCHEMA_VERSION,
            "question_code": f"Q-{str(question_id).upper()}",
            "current_version": 1,
            "current_version_id": version_id,
            "approved_version_id": None,
            "lifecycle_status": "ACTIVE",
            "evaluation_status": "NOT_STARTED",
            "review_status": "PENDING",
            "publication_status": "NOT_PUBLISHED",
            "quality_summary": {},
            "latest_review_id": None,
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
        }
        version = {
            "_id": version_id,
            "schema_version": SCHEMA_VERSION,
            "question_id": question_id,
            "version": 1,
            "origin": origin,
            "generation_run_id": generation_run_id,
            "document_id": object_id(payload.document_id, "document_id") if payload.document_id else None,
            "created_by_user_id": created_by_user_id,
            "generated_by_model_id": None,
            "classification": classification,
            "clos": [],
            "content": payload.content,
            "question_data": payload.question_data,
            "sources": sources,
            "keywords": [],
            "content_hash": content_hash,
            "change_note": "Initial version",
            "created_at": now,
        }
        question, current = self.repository.create(aggregate, version)
        return serialize_question(question, current)

    def get(self, question_id: str) -> dict | None:
        pair = self.repository.find_pair(question_id)
        return serialize_question(*pair) if pair else None

    def list(
        self,
        page: int,
        page_size: int,
        review_status: str | None,
        search: str | None,
    ) -> dict:
        pairs, total = self.repository.list(page, page_size, review_status, search)
        return {
            "items": [serialize_question(question, version) for question, version in pairs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update(
        self,
        question_id: str,
        payload: QuestionUpdateRequest,
        created_by_user_id,
    ) -> dict | None:
        pair = self.repository.find_pair(question_id)
        if not pair:
            return None
        _, current = pair
        classification = current["classification"]
        if any(
            value is not None
            for value in (payload.question_type, payload.bloom_level, payload.subject_id, payload.chapter_id)
        ):
            classification = self._classification(
                question_type=payload.question_type or classification["assessment_type"],
                bloom_level=(
                    payload.bloom_level
                    if payload.bloom_level is not None
                    else classification["bloom"]["level"]
                ),
                subject_id=(
                    payload.subject_id
                    if payload.subject_id is not None
                    else classification["subject"].get("id")
                ),
                chapter_id=(
                    payload.chapter_id
                    if payload.chapter_id is not None
                    else classification["chapter"].get("id")
                ),
            )
        content = payload.content or current["content"]
        question_data = (
            payload.question_data
            if payload.question_data is not None
            else current["question_data"]
        )
        if payload.source_chunk_ids is not None:
            sources = self._sources(payload.source_chunk_ids)
        elif payload.chunk_id is not None:
            sources = self._sources([payload.chunk_id])
        else:
            sources = current["sources"]
        content_hash = stable_hash(
            {
                "content": content,
                "question_data": question_data,
                "classification": classification,
                "sources": sources,
            }
        )
        updated = self.repository.create_version(
            question_id,
            payload.expected_version,
            {
                "origin": "MANUAL",
                "created_by_user_id": created_by_user_id,
                "classification": classification,
                "content": content,
                "question_data": question_data,
                "sources": sources,
                "content_hash": content_hash,
                "change_note": payload.change_note,
                "created_at": utc_now(),
            },
        )
        return serialize_question(*updated) if updated else None

    def archive(self, question_id: str) -> bool:
        return self.repository.archive(question_id)


def get_question_service() -> QuestionService:
    database = get_database()
    return QuestionService(MongoQuestionRepository(database), database)
