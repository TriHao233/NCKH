from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Protocol

from bson import ObjectId
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
            "lifecycle_status": question["lifecycle_status"],
            "evaluation_status": question["evaluation_status"],
            "review_status": question["review_status"],
            "publication_status": question["publication_status"],
            "content": version["content"],
            "question_data": version["question_data"],
            "classification": version["classification"],
            "sources": version.get("sources") or [],
            "content_hash": version["content_hash"],
            "quality_summary": question.get("quality_summary") or {},
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
    ) -> tuple[list[tuple[dict, dict]], int]: ...

    def create(self, aggregate: dict, version: dict) -> tuple[dict, dict]: ...

    def create_version(
        self,
        question_id: str | ObjectId,
        expected_version: int,
        version: dict,
    ) -> tuple[dict, dict] | None: ...

    def archive(self, question_id: str | ObjectId) -> bool: ...

    def list_versions(self, question_id: str | ObjectId) -> list[dict]: ...


class QuestionReferenceRepository(Protocol):
    def find_chunk(self, chunk_id: ObjectId) -> dict | None: ...

    def find_document(self, document_id: ObjectId) -> dict | None: ...

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
    ) -> tuple[list[tuple[dict, dict]], int]:
        match: dict = {"schema_version": SCHEMA_VERSION, "lifecycle_status": "ACTIVE"}
        if review_status:
            match["review_status"] = review_status
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
        if search:
            pipeline.append({"$match": {"version.content": {"$regex": search, "$options": "i"}}})
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
                        "review_status": "PENDING",
                        "publication_status": (
                            "STALE"
                            if question["publication_status"] == "PUBLISHED"
                            else question["publication_status"]
                        ),
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
