from __future__ import annotations

import hashlib
import json

from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database
from modules.questions.repository import (
    MongoQuestionRepository,
    MongoQuestionReferenceRepository,
    QuestionRepository,
    QuestionReferenceRepository,
    json_safe,
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
    def __init__(
        self,
        repository: QuestionRepository,
        references: QuestionReferenceRepository,
    ):
        self.repository = repository
        self.references = references

    def _sources(
        self,
        chunk_ids: list[str],
        expected_document_id: ObjectId | None = None,
    ) -> tuple[list[dict], ObjectId | None]:
        unique_chunk_ids = list(dict.fromkeys(chunk_ids))
        if not unique_chunk_ids:
            return [], expected_document_id
        sources = []
        resolved_document_id = expected_document_id
        for citation_order, chunk_id in enumerate(unique_chunk_ids, start=1):
            chunk_oid = object_id(chunk_id, "chunk_id")
            chunk = self.references.find_chunk(chunk_oid)
            if not chunk:
                raise ValueError(f"Chunk không tồn tại: {chunk_id}")
            chunk_document_id = chunk.get("document_id")
            if resolved_document_id is None:
                resolved_document_id = chunk_document_id
            elif chunk_document_id != resolved_document_id:
                raise ValueError("Các chunk nguồn phải thuộc cùng tài liệu")
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
        return sources, resolved_document_id

    def _document(self, document_id: str | ObjectId | None) -> dict | None:
        if document_id is None:
            return None
        document_oid = object_id(document_id, "document_id")
        document = self.references.find_document(document_oid)
        if not document:
            raise ValueError("Tài liệu nguồn không tồn tại hoặc đã lưu trữ")
        return document

    def _validate_subject(self, subject_id: str | ObjectId | None) -> dict | None:
        if subject_id is None:
            return None
        subject_oid = object_id(subject_id, "subject_id")
        subject = self.references.find_subject(subject_oid)
        if not subject:
            raise ValueError("Học phần không tồn tại hoặc đã ngừng hoạt động")
        return subject

    def _validate_classification_refs(
        self,
        subject_id: str | ObjectId | None,
        chapter_id: str | ObjectId | None,
    ) -> None:
        subject = self._validate_subject(subject_id)
        if chapter_id is None:
            return
        if subject is None:
            raise ValueError("Chương phải thuộc một học phần")
        chapter_oid = object_id(chapter_id, "chapter_id")
        chapter_ids = {
            object_id(chapter.get("_id") or chapter.get("id"), "chapter_id")
            for chapter in subject.get("chapters", [])
            if chapter.get("_id") or chapter.get("id")
        }
        if chapter_oid not in chapter_ids:
            raise ValueError("Chương không thuộc học phần đã chọn")

    def _clo_snapshots(
        self,
        subject_id: str | ObjectId | None,
        clo_ids: list[str] | None,
    ) -> list[dict]:
        if not clo_ids:
            return []
        subject = self._validate_subject(subject_id)
        if subject is None:
            raise ValueError("CLO phải thuộc một học phần")
        requested = {object_id(clo_id, "clo_id") for clo_id in clo_ids}
        snapshots = []
        for outcome in subject.get("learning_outcomes", []):
            outcome_id = outcome.get("_id") or outcome.get("id")
            if not outcome_id:
                continue
            outcome_oid = object_id(outcome_id, "clo_id")
            if outcome_oid not in requested:
                continue
            snapshots.append(
                {
                    "id": outcome_oid,
                    "code": outcome.get("clo_code") or outcome.get("code"),
                    "description": outcome.get("description", ""),
                    "target_weight": outcome.get("target_weight", 1.0),
                }
            )
        if len(snapshots) != len(requested):
            raise ValueError("Một hoặc nhiều CLO không thuộc học phần đã chọn")
        return snapshots

    @staticmethod
    def _validate_active_sources(sources: list[dict], document: dict | None) -> None:
        if not sources or not document:
            return
        active_chunk_set_id = (document.get("current_processing") or {}).get(
            "chunk_set_id"
        )
        if not active_chunk_set_id:
            raise ValueError("Tài liệu chưa có chunk set hiện hành")
        if any(
            source.get("chunk_set_id") != active_chunk_set_id
            for source in sources
        ):
            raise ValueError("Chunk nguồn không thuộc phiên xử lý hiện hành của tài liệu")

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
        document = self._document(payload.document_id)
        expected_document_id = document["_id"] if document else None
        sources, resolved_document_id = self._sources(
            source_chunk_ids,
            expected_document_id,
        )
        if resolved_document_id and document is None:
            document = self._document(resolved_document_id)
        self._validate_active_sources(sources, document)
        document_subject_id = document.get("subject_id") if document else None
        document_chapter_id = document.get("chapter_id") if document else None
        if (
            payload.subject_id
            and document_subject_id
            and object_id(payload.subject_id, "subject_id") != document_subject_id
        ):
            raise ValueError("Học phần câu hỏi không khớp với tài liệu nguồn")
        if (
            payload.chapter_id
            and document_chapter_id
            and object_id(payload.chapter_id, "chapter_id") != document_chapter_id
        ):
            raise ValueError("Chương câu hỏi không khớp với tài liệu nguồn")
        subject_id = document_subject_id or payload.subject_id
        chapter_id = document_chapter_id or payload.chapter_id
        self._validate_classification_refs(subject_id, chapter_id)
        classification = self._classification(
            question_type=payload.question_type,
            bloom_level=payload.bloom_level,
            subject_id=subject_id,
            chapter_id=chapter_id,
        )
        clos = self._clo_snapshots(subject_id, payload.clo_ids)
        content_hash = stable_hash(
            {
                "content": payload.content,
                "question_data": payload.question_data,
                "classification": classification,
                "clos": clos,
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
            "document_id": resolved_document_id,
            "created_by_user_id": created_by_user_id,
            "generated_by_model_id": None,
            "classification": classification,
            "clos": clos,
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

    def versions(self, question_id: str) -> list[dict] | None:
        versions = self.repository.list_versions(question_id)
        if not versions:
            return None
        return [
            json_safe(
                {
                    "id": version["_id"],
                    "version": version["version"],
                    "origin": version["origin"],
                    "generation_run_id": version.get("generation_run_id"),
                    "document_id": version.get("document_id"),
                    "created_by_user_id": version.get("created_by_user_id"),
                    "generated_by_model_id": version.get("generated_by_model_id"),
                    "classification": version["classification"],
                    "clos": version.get("clos") or [],
                    "content": version["content"],
                    "question_data": version["question_data"],
                    "sources": version.get("sources") or [],
                    "keywords": version.get("keywords") or [],
                    "content_hash": version["content_hash"],
                    "change_note": version.get("change_note", ""),
                    "created_at": version["created_at"],
                }
            )
            for version in versions
        ]

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
            next_subject_id = (
                payload.subject_id
                if payload.subject_id is not None
                else classification["subject"].get("id")
            )
            next_chapter_id = (
                payload.chapter_id
                if payload.chapter_id is not None
                else classification["chapter"].get("id")
            )
            current_document = self._document(current.get("document_id"))
            if current_document:
                document_subject_id = current_document.get("subject_id")
                document_chapter_id = current_document.get("chapter_id")
                if (
                    document_subject_id
                    and object_id(next_subject_id, "subject_id")
                    != document_subject_id
                ):
                    raise ValueError(
                        "Học phần câu hỏi không khớp với tài liệu nguồn"
                    )
                if (
                    document_chapter_id
                    and object_id(next_chapter_id, "chapter_id")
                    != document_chapter_id
                ):
                    raise ValueError(
                        "Chương câu hỏi không khớp với tài liệu nguồn"
                    )
            self._validate_classification_refs(next_subject_id, next_chapter_id)
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
        if payload.clo_ids is not None:
            clos = self._clo_snapshots(
                classification["subject"].get("id"),
                payload.clo_ids,
            )
        elif payload.subject_id is not None:
            clos = []
        else:
            clos = current.get("clos", [])
        current_document_id = current.get("document_id")
        resolved_document_id = current_document_id
        if payload.source_chunk_ids is not None:
            sources, resolved_document_id = self._sources(
                payload.source_chunk_ids,
                current_document_id,
            )
        elif payload.chunk_id is not None:
            sources, resolved_document_id = self._sources(
                [payload.chunk_id],
                current_document_id,
            )
        else:
            sources = current["sources"]
        if current_document_id is None and resolved_document_id is not None:
            source_document = self._document(resolved_document_id)
            source_subject_id = source_document.get("subject_id")
            source_chapter_id = source_document.get("chapter_id")
            current_subject_id = classification["subject"].get("id")
            current_chapter_id = classification["chapter"].get("id")
            if (
                current_subject_id
                and source_subject_id
                and current_subject_id != source_subject_id
            ):
                raise ValueError("Học phần câu hỏi không khớp với tài liệu nguồn")
            if (
                current_chapter_id
                and source_chapter_id
                and current_chapter_id != source_chapter_id
            ):
                raise ValueError("Chương câu hỏi không khớp với tài liệu nguồn")
            next_subject_id = source_subject_id or current_subject_id
            next_chapter_id = source_chapter_id or current_chapter_id
            self._validate_classification_refs(next_subject_id, next_chapter_id)
            classification = self._classification(
                question_type=classification["assessment_type"],
                bloom_level=classification["bloom"]["level"],
                subject_id=next_subject_id,
                chapter_id=next_chapter_id,
            )
        if payload.source_chunk_ids is not None or payload.chunk_id is not None:
            document = self._document(resolved_document_id)
            self._validate_active_sources(sources, document)
        content_hash = stable_hash(
            {
                "content": content,
                "question_data": question_data,
                "classification": classification,
                "clos": clos,
                "sources": sources,
            }
        )
        updated = self.repository.create_version(
            question_id,
            payload.expected_version,
            {
                "origin": "MANUAL",
                "created_by_user_id": created_by_user_id,
                "document_id": resolved_document_id,
                "classification": classification,
                "clos": clos,
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
    return QuestionService(
        MongoQuestionRepository(database),
        MongoQuestionReferenceRepository(database),
    )
