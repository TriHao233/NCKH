import hashlib
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database
from modules.catalog.schemas import (
    AiModelPayload,
    ChapterPayload,
    EvaluationPolicyPayload,
    LearningOutcomePayload,
    PromptTemplatePayload,
    SubjectPayload,
)
from modules.questions.repository import json_safe, object_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _subject_response(record: dict) -> dict:
    return json_safe(
        {
            "id": record["_id"],
            "subject_code": record["subject_code"],
            "subject_name": record["subject_name"],
            "description": record.get("description", ""),
            "chapters": record.get("chapters") or [],
            "learning_outcomes": record.get("learning_outcomes") or [],
            "is_active": record.get("is_active", True),
        }
    )


class CatalogService:
    def __init__(self, database):
        self.db = database

    def list_subjects(self) -> list[dict]:
        records = self.db.subjects.find().sort("subject_code", 1)
        return [_subject_response(record) for record in records]

    def upsert_subject(self, payload: SubjectPayload) -> dict:
        now = utc_now()
        record = self.db.subjects.find_one_and_update(
            {"subject_code": payload.subject_code},
            {
                "$set": {
                    "schema_version": SCHEMA_VERSION,
                    "subject_name": payload.subject_name,
                    "description": payload.description,
                    "is_active": payload.is_active,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": ObjectId(),
                    "chapters": [],
                    "learning_outcomes": [],
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return _subject_response(record)

    def add_chapter(self, subject_id: str, payload: ChapterPayload) -> dict:
        now = utc_now()
        chapter = {
            "_id": ObjectId(),
            "chapter_code": payload.chapter_code,
            "chapter_name": payload.chapter_name,
            "sequence_no": payload.sequence_no,
            "is_active": True,
            "created_at": now,
        }
        record = self.db.subjects.find_one_and_update(
            {"_id": object_id(subject_id, "subject_id")},
            {"$push": {"chapters": chapter}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not record:
            raise LookupError("Không tìm thấy học phần")
        return _subject_response(record)

    def add_learning_outcome(self, subject_id: str, payload: LearningOutcomePayload) -> dict:
        now = utc_now()
        outcome = {
            "_id": ObjectId(),
            "clo_code": payload.clo_code,
            "description": payload.description,
            "target_weight": payload.target_weight,
            "is_active": True,
            "created_at": now,
        }
        record = self.db.subjects.find_one_and_update(
            {"_id": object_id(subject_id, "subject_id")},
            {"$push": {"learning_outcomes": outcome}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not record:
            raise LookupError("Không tìm thấy học phần")
        return _subject_response(record)

    def list_ai_models(self) -> list[dict]:
        return [json_safe(item) for item in self.db.ai_models.find().sort("priority", 1)]

    def upsert_ai_model(self, payload: AiModelPayload) -> dict:
        now = utc_now()
        record = self.db.ai_models.find_one_and_update(
            {"model_code": payload.model_code},
            {
                "$set": {
                    "schema_version": SCHEMA_VERSION,
                    **payload.model_dump(),
                    "updated_at": now,
                },
                "$setOnInsert": {"_id": ObjectId(), "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return json_safe(record)

    def list_prompt_templates(self) -> list[dict]:
        cursor = self.db.prompt_templates.find().sort([("template_key", 1), ("version", -1)])
        return [json_safe(item) for item in cursor]

    def save_prompt_template(self, payload: PromptTemplatePayload) -> dict:
        now = utc_now()
        latest = self.db.prompt_templates.find_one(
            {"template_key": payload.template_key},
            sort=[("version", -1)],
        )
        version = int(latest.get("version", 0)) + 1 if latest and payload.create_new_version else int((latest or {}).get("version", 1))
        if payload.is_active:
            self.db.prompt_templates.update_many(
                {"template_key": payload.template_key},
                {"$set": {"is_active": False, "updated_at": now}},
            )
        body_hash = hashlib.sha256(payload.prompt_body.encode("utf-8")).hexdigest()
        record = self.db.prompt_templates.find_one_and_update(
            {"template_key": payload.template_key, "version": version},
            {
                "$set": {
                    "schema_version": SCHEMA_VERSION,
                    "template_key": payload.template_key,
                    "version": version,
                    "kind": payload.kind,
                    "name": payload.name,
                    "prompt_body": payload.prompt_body,
                    "content_hash": body_hash,
                    "is_active": payload.is_active,
                    "updated_at": now,
                },
                "$setOnInsert": {"_id": ObjectId(), "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return json_safe(record)

    def list_evaluation_policies(self) -> list[dict]:
        cursor = self.db.evaluation_policies.find().sort([("policy_name", 1), ("version", -1)])
        return [json_safe(item) for item in cursor]

    def save_evaluation_policy(self, payload: EvaluationPolicyPayload) -> dict:
        now = utc_now()
        latest = self.db.evaluation_policies.find_one(
            {"policy_name": payload.policy_name},
            sort=[("version", -1)],
        )
        version = int(latest.get("version", 0)) + 1 if latest and payload.create_new_version else int((latest or {}).get("version", 1))
        if payload.is_active:
            self.db.evaluation_policies.update_many(
                {"policy_name": payload.policy_name},
                {"$set": {"is_active": False}},
            )
        weights_hash = hashlib.sha256(str(sorted(payload.weights.items())).encode()).hexdigest()
        record = self.db.evaluation_policies.find_one_and_update(
            {"policy_name": payload.policy_name, "version": version},
            {
                "$set": {
                    "schema_version": SCHEMA_VERSION,
                    "policy_name": payload.policy_name,
                    "version": version,
                    "weights": payload.weights,
                    "weights_hash": weights_hash,
                    "thresholds": payload.thresholds,
                    "is_active": payload.is_active,
                    "updated_at": now,
                },
                "$setOnInsert": {"_id": ObjectId(), "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return json_safe(record)

    def overview(self) -> dict[str, Any]:
        return {
            "subjects": self.list_subjects(),
            "ai_models": self.list_ai_models(),
            "prompt_templates": self.list_prompt_templates(),
            "evaluation_policies": self.list_evaluation_policies(),
        }


def get_catalog_service() -> CatalogService:
    return CatalogService(get_database())
