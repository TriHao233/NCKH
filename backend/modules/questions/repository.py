from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.bootstrap import SCHEMA_VERSION
from core.database import mongo_transaction


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def object_id(value: str | ObjectId, field_name: str = "id") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except Exception as exc:
        raise ValueError(f"{field_name} không hợp lệ") from exc


def json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def serialize_question(question: dict, version: dict) -> dict:
    return json_safe(
        {
            "id": question["_id"],
            "question_code": question["question_code"],
            "current_version": question["current_version"],
            "current_version_id": question["current_version_id"],
            "approved_version_id": question.get("approved_version_id"),
            "document_id": version.get("document_id"),
            "lifecycle_status": question["lifecycle_status"],
            "evaluation_status": question["evaluation_status"],
            "review_status": question["review_status"],
            "publication_status": question["publication_status"],
            "content": version["content"],
            "question_data": version["question_data"],
            "classification": version["classification"],
            "clos": version.get("clos") or [],
            "sources": version.get("sources") or [],
            "content_hash": version["content_hash"],
            "quality_summary": question.get("quality_summary") or {},
            "review_assignment": question.get("review_assignment") or {"status": "UNASSIGNED"},
            "shared_with_user_ids": question.get("shared_with_user_ids") or [],
            "shared_scope": question.get("shared_scope") or "PRIVATE",
            "secondary_review": question.get("secondary_review") or {},
            "latest_review_id": question.get("latest_review_id"),
            "created_at": question["created_at"],
            "updated_at": question["updated_at"],
        }
    )


class QuestionRepository(Protocol):
    def find_pair(self, question_id: str | ObjectId) -> tuple[dict, dict] | None: ...

    def list(
        self,
        page: int,
        page_size: int,
        review_status: str | None,
        search: str | None,
        *,
        question_type: str | None = None,
        bloom_level: int | None = None,
        document_id: str | None = None,
        subject_id: str | None = None,
        chapter_id: str | None = None,
        clo_id: str | None = None,
        difficulty: str | None = None,
        quality_color: str | None = None,
        min_score: float | None = None,
        publication_status: str | None = None,
        evaluation_status: str | None = None,
        assignment_status: str | None = None,
        assigned_reviewer_user_id: ObjectId | None = None,
        creator_user_id: ObjectId | None = None,
        owner_user_id: ObjectId | None = None,
        visible_to_user_id: ObjectId | None = None,
        approved_current_only: bool = False,
        waiting_since: datetime | None = None,
        overdue_at: datetime | None = None,
    ) -> tuple[list[tuple[dict, dict]], int]: ...

    def create(self, aggregate: dict, version: dict) -> tuple[dict, dict]: ...

    def create_version(
        self,
        question_id: str | ObjectId,
        expected_version: int,
        version: dict,
    ) -> tuple[dict, dict] | None: ...

    def update_review_status(
        self,
        question_id: str | ObjectId,
        allowed_statuses: set[str],
        review_status: str,
    ) -> tuple[dict, dict] | None: ...

    def archive(self, question_id: str | ObjectId) -> bool: ...

    def list_versions(self, question_id: str | ObjectId) -> list[dict]: ...

    def update_sharing(self, question_id: str | ObjectId, fields: dict) -> tuple[dict, dict] | None: ...


class QuestionReferenceRepository(Protocol):
    def find_chunk(self, chunk_id: ObjectId) -> dict | None: ...

    def find_document(self, document_id: ObjectId) -> dict | None: ...

    def find_pages(
        self,
        document_id: ObjectId,
        ocr_job_id: ObjectId | None,
        page_numbers: list[int],
    ) -> list[dict]: ...

    def find_subject(self, subject_id: ObjectId) -> dict | None: ...


class MongoQuestionReferenceRepository:
    def __init__(self, database: Database):
        self.db = database

    def find_chunk(self, chunk_id: ObjectId) -> dict | None:
        return self.db.document_chunks.find_one({"_id": chunk_id})

    def find_document(self, document_id: ObjectId) -> dict | None:
        return self.db.documents.find_one(
            {
                "_id": document_id,
                "schema_version": SCHEMA_VERSION,
                "archived_at": None,
            }
        )

    def find_pages(
        self,
        document_id: ObjectId,
        ocr_job_id: ObjectId | None,
        page_numbers: list[int],
    ) -> list[dict]:
        if not page_numbers:
            return []
        query: dict = {
            "document_id": document_id,
            "page_number": {"$in": sorted(set(page_numbers))},
        }
        if ocr_job_id is not None:
            query["ocr_job_id"] = ocr_job_id
        return list(self.db.document_pages.find(query).sort("page_number", 1))

    def find_subject(self, subject_id: ObjectId) -> dict | None:
        return self.db.subjects.find_one({"_id": subject_id, "is_active": True})


class MongoQuestionRepository:
    def __init__(self, database: Database):
        self.db = database

    def find_pair(self, question_id: str | ObjectId) -> tuple[dict, dict] | None:
        question = self.db.questions.find_one(
            {
                "_id": object_id(question_id, "question_id"),
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
            }
        )
        if not question:
            return None
        version = self.db.question_versions.find_one({"_id": question["current_version_id"]})
        if not version:
            raise RuntimeError("Question aggregate bị thiếu current version")
        return question, version

    def list(
        self,
        page: int,
        page_size: int,
        review_status: str | None,
        search: str | None,
        *,
        question_type: str | None = None,
        bloom_level: int | None = None,
        document_id: str | None = None,
        subject_id: str | None = None,
        chapter_id: str | None = None,
        clo_id: str | None = None,
        difficulty: str | None = None,
        quality_color: str | None = None,
        min_score: float | None = None,
        publication_status: str | None = None,
        evaluation_status: str | None = None,
        assignment_status: str | None = None,
        assigned_reviewer_user_id: ObjectId | None = None,
        creator_user_id: ObjectId | None = None,
        owner_user_id: ObjectId | None = None,
        visible_to_user_id: ObjectId | None = None,
        approved_current_only: bool = False,
        waiting_since: datetime | None = None,
        overdue_at: datetime | None = None,
    ) -> tuple[list[tuple[dict, dict]], int]:
        match: dict = {"schema_version": SCHEMA_VERSION, "lifecycle_status": "ACTIVE"}
        if review_status:
            match["review_status"] = review_status
        if publication_status:
            match["publication_status"] = publication_status
        if evaluation_status:
            match["evaluation_status"] = evaluation_status
        if assignment_status:
            match["review_assignment.status"] = assignment_status
        if assigned_reviewer_user_id is not None:
            match["review_assignment.reviewer_user_id"] = assigned_reviewer_user_id
        if quality_color:
            match["quality_summary.color"] = quality_color.upper()
        if min_score is not None:
            match["quality_summary.overall_score"] = {"$gte": float(min_score)}
        if waiting_since is not None:
            match["updated_at"] = {"$lte": waiting_since}
        if overdue_at is not None:
            match["review_assignment.lock_expires_at"] = {"$lte": overdue_at}
        pipeline: list[dict] = [
            {"$match": match},
            {
                "$lookup": {
                    "from": "question_versions",
                    "localField": "current_version_id",
                    "foreignField": "_id",
                    "as": "version",
                }
            },
            {"$unwind": "$version"},
        ]
        if approved_current_only:
            pipeline.append(
                {
                    "$match": {
                        "$expr": {"$eq": ["$approved_version_id", "$current_version_id"]}
                    }
                }
            )
        if owner_user_id is not None:
            pipeline.append(
                {
                    "$match": {
                        "$or": [
                            {"created_by_user_id": owner_user_id},
                            {"version.created_by_user_id": owner_user_id},
                        ]
                    }
                }
            )
        if visible_to_user_id is not None:
            pipeline.append(
                {
                    "$match": {
                        "$or": [
                            {"created_by_user_id": visible_to_user_id},
                            {"version.created_by_user_id": visible_to_user_id},
                            {"shared_with_user_ids": visible_to_user_id},
                            {"shared_scope": "SUBJECT"},
                        ]
                    }
                }
            )
        if creator_user_id is not None:
            pipeline.append(
                {
                    "$match": {
                        "$or": [
                            {"created_by_user_id": creator_user_id},
                            {"version.created_by_user_id": creator_user_id},
                        ]
                    }
                }
            )
        version_match: dict = {}
        if question_type:
            version_match["version.classification.assessment_type"] = question_type.upper()
        if bloom_level is not None:
            version_match["version.classification.bloom.level"] = int(bloom_level)
        if document_id:
            version_match["version.document_id"] = object_id(document_id, "document_id")
        if subject_id:
            version_match["version.classification.subject.id"] = object_id(subject_id, "subject_id")
        if chapter_id:
            version_match["version.classification.chapter.id"] = object_id(chapter_id, "chapter_id")
        if clo_id:
            version_match["version.clos.id"] = object_id(clo_id, "clo_id")
        if difficulty:
            version_match["version.classification.difficulty"] = difficulty
        if version_match:
            pipeline.append({"$match": version_match})
        if search:
            pipeline.append(
                {
                    "$match": {
                        "$or": [
                            {"question_code": {"$regex": search, "$options": "i"}},
                            {"version.content": {"$regex": search, "$options": "i"}},
                        ]
                    }
                }
            )
        pipeline.extend(
            [
                {"$sort": {"updated_at": -1}},
                {
                    "$facet": {
                        "items": [
                            {"$skip": (page - 1) * page_size},
                            {"$limit": page_size},
                        ],
                        "count": [{"$count": "total"}],
                    }
                },
            ]
        )
        result = list(self.db.questions.aggregate(pipeline))[0]
        total = result["count"][0]["total"] if result["count"] else 0
        return [(item, item["version"]) for item in result["items"]], total

    def create(self, aggregate: dict, version: dict) -> tuple[dict, dict]:
        with mongo_transaction() as session:
            self.db.questions.insert_one(aggregate, session=session)
            self.db.question_versions.insert_one(version, session=session)
        return aggregate, version

    def create_version(
        self,
        question_id: str | ObjectId,
        expected_version: int,
        version: dict,
    ) -> tuple[dict, dict] | None:
        pair = self.find_pair(question_id)
        if not pair:
            return None
        question, current = pair
        if question["current_version"] != expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        new_version = deepcopy(current)
        new_version.update(version)
        new_version["_id"] = ObjectId()
        new_version["question_id"] = question["_id"]
        new_version["version"] = expected_version + 1
        now = utc_now()
        next_review_status = (
            question["review_status"]
            if question["review_status"] in {"DRAFT", "NEEDS_REVISION"}
            else "PENDING"
        )
        with mongo_transaction() as session:
            self.db.question_versions.insert_one(new_version, session=session)
            result = self.db.questions.update_one(
                {
                    "_id": question["_id"],
                    "current_version": expected_version,
                    "lifecycle_status": "ACTIVE",
                },
                {
                    "$set": {
                        "current_version": expected_version + 1,
                        "current_version_id": new_version["_id"],
                        "evaluation_status": "NOT_STARTED",
                        "review_status": next_review_status,
                        "publication_status": (
                            "STALE"
                            if question["publication_status"] == "PUBLISHED"
                            else question["publication_status"]
                        ),
                        "review_assignment": {
                            "status": "UNASSIGNED",
                            "reviewer_user_id": None,
                            "assigned_by_user_id": None,
                            "assigned_at": None,
                            "claimed_at": None,
                            "lock_expires_at": None,
                            "last_released_at": None,
                            "release_reason": None,
                        },
                        "quality_summary": {},
                        "updated_at": now,
                    }
                },
                session=session,
            )
            if not result.modified_count:
                raise RuntimeError("VERSION_CONFLICT")
        updated = self.db.questions.find_one({"_id": question["_id"]})
        return updated, new_version

    def update_review_status(
        self,
        question_id: str | ObjectId,
        allowed_statuses: set[str],
        review_status: str,
    ) -> tuple[dict, dict] | None:
        question_oid = object_id(question_id, "question_id")
        now = utc_now()
        result = self.db.questions.update_one(
            {
                "_id": question_oid,
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
                "review_status": {"$in": list(allowed_statuses)},
            },
            {
                "$set": {
                    "review_status": review_status,
                    "review_assignment": {
                        "status": "UNASSIGNED",
                        "reviewer_user_id": None,
                        "assigned_by_user_id": None,
                        "assigned_at": None,
                        "claimed_at": None,
                        "lock_expires_at": None,
                        "last_released_at": None,
                        "release_reason": None,
                    },
                    "updated_at": now,
                }
            },
        )
        if not result.matched_count:
            return None
        return self.find_pair(question_oid)

    def archive(self, question_id: str | ObjectId) -> bool:
        now = utc_now()
        result = self.db.questions.update_one(
            {
                "_id": object_id(question_id, "question_id"),
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
            },
            {
                "$set": {
                    "lifecycle_status": "ARCHIVED",
                    "archived_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.matched_count == 1

    def list_versions(self, question_id: str | ObjectId) -> list[dict]:
        question_oid = object_id(question_id, "question_id")
        if not self.db.questions.find_one(
            {"_id": question_oid, "schema_version": SCHEMA_VERSION},
            {"_id": 1},
        ):
            return []
        return list(
            self.db.question_versions.find({"question_id": question_oid}).sort(
                "version",
                -1,
            )
        )

    def update_sharing(self, question_id: str | ObjectId, fields: dict) -> tuple[dict, dict] | None:
        normalized = dict(fields)
        if "shared_with_user_ids" in normalized:
            normalized["shared_with_user_ids"] = [
                object_id(user_id, "shared_with_user_id")
                for user_id in normalized.get("shared_with_user_ids") or []
            ]
        normalized["updated_at"] = utc_now()
        question = self.db.questions.find_one_and_update(
            {
                "_id": object_id(question_id, "question_id"),
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
            },
            {"$set": normalized},
            return_document=ReturnDocument.AFTER,
        )
        if not question:
            return None
        version = self.db.question_versions.find_one({"_id": question["current_version_id"]})
        if not version:
            raise RuntimeError("Question aggregate bị thiếu current version")
        return question, version
