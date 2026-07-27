import asyncio
import hashlib
import time
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from core.bootstrap import SCHEMA_VERSION
from core.config import settings
from core.database import get_database
from modules.catalog.schemas import (
    AiModelActivationPayload,
    AiModelHealthCheckPayload,
    AiModelPayload,
    ChapterPayload,
    ChapterUpdatePayload,
    EvaluationPolicyActivationPayload,
    EvaluationPolicyPayload,
    LearningOutcomePayload,
    LearningOutcomeUpdatePayload,
    PromptTemplateActivationPayload,
    PromptTemplatePayload,
    PromptTemplateTestPayload,
    SubjectPayload,
    SubjectUpdatePayload,
)
from modules.generation.llm.factory import get_llm_service
from modules.generation.prompt_builder import PromptBuilder
from modules.questions.repository import json_safe, object_id


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


FALLBACK_EVALUATION_POLICY = {
    "policy_name": "Default fallback",
    "version": 1,
    "weights": {
        "faithfulness": 0.35,
        "contextual_relevancy": 0.20,
        "answer_relevancy": 0.15,
        "bloom_alignment": 0.15,
        "clo_alignment": 0.15,
    },
    "thresholds": {"yellow_min": 0.60, "green_min": 0.80, "pass_min": 0.80},
    "is_active": True,
}


def _subdoc_id(item: dict) -> ObjectId | str | None:
    return item.get("_id") or item.get("id")


def _with_child_usage(item: dict, usage_counts: dict[str, dict]) -> dict:
    item_id = _subdoc_id(item)
    return {
        **item,
        "id": item_id,
        "usage_counts": usage_counts.get(str(item_id), {}),
    }


def _subject_response(record: dict, usage_counts: dict[str, Any] | None = None) -> dict:
    usage_counts = usage_counts or {}
    chapters = sorted(
        record.get("chapters") or [],
        key=lambda item: (item.get("sequence_no") or 0, item.get("chapter_code") or ""),
    )
    learning_outcomes = record.get("learning_outcomes") or []
    return json_safe(
        {
            "id": record["_id"],
            "subject_code": record["subject_code"],
            "subject_name": record["subject_name"],
            "description": record.get("description", ""),
            "chapters": [
                _with_child_usage(chapter, usage_counts.get("chapters", {}))
                for chapter in chapters
            ],
            "learning_outcomes": [
                _with_child_usage(outcome, usage_counts.get("learning_outcomes", {}))
                for outcome in learning_outcomes
            ],
            "is_active": record.get("is_active", True),
            "usage_counts": usage_counts.get("subject", {}),
        }
    )


class CatalogService:
    def __init__(self, database):
        self.db = database

    def _count(self, collection_name: str, query: dict) -> int:
        collection = getattr(self.db, collection_name, None)
        if collection is None:
            return 0
        return collection.count_documents(query)

    def _count_current_questions(self, version_query: dict) -> int:
        versions = getattr(self.db, "question_versions", None)
        questions = getattr(self.db, "questions", None)
        if versions is None or questions is None:
            return 0
        version_ids = [
            item["_id"]
            for item in versions.find(version_query, {"_id": 1})
        ]
        if not version_ids:
            return 0
        return questions.count_documents(
            {
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
                "current_version_id": {"$in": version_ids},
            }
        )

    def _usage_counts(self, subject: dict) -> dict[str, Any]:
        subject_id = subject["_id"]
        subject_counts = {
            "documents": self._count(
                "documents",
                {"subject_id": subject_id, "archived_at": None},
            ),
            "questions": self._count_current_questions(
                {"classification.subject.id": subject_id}
            ),
            "exams": self._count("exams", {"subject_id": subject_id}),
        }
        chapter_counts = {}
        for chapter in subject.get("chapters") or []:
            chapter_id = _subdoc_id(chapter)
            if not chapter_id:
                continue
            chapter_counts[str(chapter_id)] = {
                "documents": self._count(
                    "documents",
                    {
                        "subject_id": subject_id,
                        "chapter_id": chapter_id,
                        "archived_at": None,
                    },
                ),
                "questions": self._count_current_questions(
                    {"classification.chapter.id": chapter_id}
                ),
                "exams": self._count("exams", {"matrix.chapter_id": chapter_id}),
            }
        outcome_counts = {}
        for outcome in subject.get("learning_outcomes") or []:
            outcome_id = _subdoc_id(outcome)
            if not outcome_id:
                continue
            outcome_counts[str(outcome_id)] = {
                "questions": self._count_current_questions({"clos.id": outcome_id}),
            }
        return {
            "subject": subject_counts,
            "chapters": chapter_counts,
            "learning_outcomes": outcome_counts,
        }

    def _subject_or_404(self, subject_id: str | ObjectId) -> dict:
        subject = self.db.subjects.find_one({"_id": object_id(subject_id, "subject_id")})
        if not subject:
            raise LookupError("Không tìm thấy học phần")
        return subject

    def _find_subject_by_code(self, subject_code: str) -> dict | None:
        normalized = subject_code.strip().lower()
        for subject in self.db.subjects.find():
            if str(subject.get("subject_code", "")).strip().lower() == normalized:
                return subject
        return None

    def _ensure_subject_code_available(
        self,
        subject_code: str,
        *,
        current_subject_id: ObjectId | None = None,
    ) -> str:
        normalized = subject_code.strip()
        duplicate = self._find_subject_by_code(normalized)
        if duplicate and duplicate.get("_id") != current_subject_id:
            raise ValueError("Mã học phần đã tồn tại")
        return normalized

    @staticmethod
    def _ensure_child_code_available(
        subject: dict,
        collection_key: str,
        code_key: str,
        code: str,
        *,
        current_child_id: ObjectId | None = None,
    ) -> str:
        normalized = code.strip()
        for item in subject.get(collection_key) or []:
            item_id = _subdoc_id(item)
            if current_child_id is not None and item_id == current_child_id:
                continue
            if str(item.get(code_key, "")).strip().lower() == normalized.lower():
                raise ValueError("Mã đã tồn tại trong học phần này")
        return normalized

    def list_subjects(self) -> list[dict]:
        records = self.db.subjects.find().sort("subject_code", 1)
        return [
            _subject_response(record, self._usage_counts(record))
            for record in records
        ]

    def upsert_subject(self, payload: SubjectPayload) -> dict:
        now = utc_now()
        subject_code = payload.subject_code.strip()
        existing = self._find_subject_by_code(subject_code)
        record = self.db.subjects.find_one_and_update(
            {"_id": existing["_id"]} if existing else {"subject_code": subject_code},
            {
                "$set": {
                    "schema_version": SCHEMA_VERSION,
                    "subject_code": subject_code,
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
        return _subject_response(record, self._usage_counts(record))

    def update_subject(self, subject_id: str, payload: SubjectUpdatePayload) -> dict:
        subject = self._subject_or_404(subject_id)
        fields = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "subject_code" in fields:
            fields["subject_code"] = self._ensure_subject_code_available(
                fields["subject_code"],
                current_subject_id=subject["_id"],
            )
        if not fields:
            return _subject_response(subject, self._usage_counts(subject))
        fields["updated_at"] = utc_now()
        record = self.db.subjects.find_one_and_update(
            {"_id": subject["_id"]},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return _subject_response(record, self._usage_counts(record))

    def add_chapter(self, subject_id: str, payload: ChapterPayload) -> dict:
        now = utc_now()
        subject = self._subject_or_404(subject_id)
        chapter_code = self._ensure_child_code_available(
            subject,
            "chapters",
            "chapter_code",
            payload.chapter_code,
        )
        chapter = {
            "_id": ObjectId(),
            "chapter_code": chapter_code,
            "chapter_name": payload.chapter_name,
            "sequence_no": payload.sequence_no,
            "is_active": payload.is_active,
            "created_at": now,
            "updated_at": now,
        }
        record = self.db.subjects.find_one_and_update(
            {"_id": subject["_id"]},
            {"$push": {"chapters": chapter}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return _subject_response(record, self._usage_counts(record))

    def update_chapter(
        self,
        subject_id: str,
        chapter_id: str,
        payload: ChapterUpdatePayload,
    ) -> dict:
        subject = self._subject_or_404(subject_id)
        chapter_oid = object_id(chapter_id, "chapter_id")
        if not any(_subdoc_id(item) == chapter_oid for item in subject.get("chapters") or []):
            raise LookupError("Không tìm thấy chương")
        fields = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "chapter_code" in fields:
            fields["chapter_code"] = self._ensure_child_code_available(
                subject,
                "chapters",
                "chapter_code",
                fields["chapter_code"],
                current_child_id=chapter_oid,
            )
        if not fields:
            return _subject_response(subject, self._usage_counts(subject))
        now = utc_now()
        update_fields = {
            f"chapters.$.{key}": value
            for key, value in fields.items()
        }
        update_fields["chapters.$.updated_at"] = now
        update_fields["updated_at"] = now
        record = self.db.subjects.find_one_and_update(
            {"_id": subject["_id"], "chapters._id": chapter_oid},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if not record:
            raise LookupError("Không tìm thấy chương")
        return _subject_response(record, self._usage_counts(record))

    def add_learning_outcome(self, subject_id: str, payload: LearningOutcomePayload) -> dict:
        now = utc_now()
        subject = self._subject_or_404(subject_id)
        clo_code = self._ensure_child_code_available(
            subject,
            "learning_outcomes",
            "clo_code",
            payload.clo_code,
        )
        outcome = {
            "_id": ObjectId(),
            "clo_code": clo_code,
            "description": payload.description,
            "target_weight": payload.target_weight,
            "is_active": payload.is_active,
            "created_at": now,
            "updated_at": now,
        }
        record = self.db.subjects.find_one_and_update(
            {"_id": subject["_id"]},
            {"$push": {"learning_outcomes": outcome}, "$set": {"updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return _subject_response(record, self._usage_counts(record))

    def update_learning_outcome(
        self,
        subject_id: str,
        clo_id: str,
        payload: LearningOutcomeUpdatePayload,
    ) -> dict:
        subject = self._subject_or_404(subject_id)
        clo_oid = object_id(clo_id, "clo_id")
        if not any(
            _subdoc_id(item) == clo_oid
            for item in subject.get("learning_outcomes") or []
        ):
            raise LookupError("Không tìm thấy CLO")
        fields = payload.model_dump(exclude_unset=True, exclude_none=True)
        if "clo_code" in fields:
            fields["clo_code"] = self._ensure_child_code_available(
                subject,
                "learning_outcomes",
                "clo_code",
                fields["clo_code"],
                current_child_id=clo_oid,
            )
        if not fields:
            return _subject_response(subject, self._usage_counts(subject))
        now = utc_now()
        update_fields = {
            f"learning_outcomes.$.{key}": value
            for key, value in fields.items()
        }
        update_fields["learning_outcomes.$.updated_at"] = now
        update_fields["updated_at"] = now
        record = self.db.subjects.find_one_and_update(
            {"_id": subject["_id"], "learning_outcomes._id": clo_oid},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
        if not record:
            raise LookupError("Không tìm thấy CLO")
        return _subject_response(record, self._usage_counts(record))

    def list_ai_models(self) -> list[dict]:
        return [
            json_safe({**item, "factory_status": self._model_factory_status(item["model_code"])})
            for item in self.db.ai_models.find().sort("priority", 1)
        ]

    @staticmethod
    def _model_factory_status(model_code: str) -> dict:
        try:
            provider = get_llm_service(model_code)
            runtime = {
                "provider_class": provider.__class__.__name__,
                "model_name": getattr(provider, "model_name", None),
                "url": getattr(provider, "url", None),
            }
            return {"supported": True, "runtime": runtime}
        except Exception as exc:
            return {"supported": False, "error": str(exc)}

    def _catalog_model(self, model_code: str) -> dict | None:
        return self.db.ai_models.find_one({"model_code": model_code})

    def runtime_config(self) -> dict:
        generation_code = settings.model_provider
        evaluation_code = settings.evaluation_model_provider
        active_prompt_count = self.db.prompt_templates.count_documents({"is_active": True})
        active_policy = self.db.evaluation_policies.find_one(
            {"is_active": True},
            sort=[("version", -1)],
        )
        warnings: list[str] = []
        if settings.prompt_source != "db" and active_prompt_count:
            warnings.append(
                "PROMPT_SOURCE đang là file nên các prompt active trong DB chưa tác động runtime."
            )
        if settings.prompt_source == "db" and not active_prompt_count:
            warnings.append("PROMPT_SOURCE=db nhưng chưa có prompt active trong DB; runtime sẽ fallback file.")
        if not self._catalog_model(generation_code):
            warnings.append(f"Model sinh câu hỏi '{generation_code}' chưa có trong catalog DB.")
        if not self._catalog_model(evaluation_code):
            warnings.append(f"Model đánh giá '{evaluation_code}' chưa có trong catalog DB.")

        return json_safe(
            {
                "app_env": settings.app_env,
                "prompt_source": settings.prompt_source,
                "prompts_dir": settings.prompts_dir,
                "generation_model_provider": generation_code,
                "evaluation_model_provider": evaluation_code,
                "ollama_generate_url": settings.ollama_generate_url,
                "deepseek_model_name": settings.deepseek_model_name,
                "deepseek_timeout_seconds": settings.deepseek_timeout_seconds,
                "gemini_default_model": settings.DEFAULT_MODEL,
                "gemini_api_key_configured": bool(settings.GEMINI_API_KEY),
                "generation_factory": self._model_factory_status(generation_code),
                "evaluation_factory": self._model_factory_status(evaluation_code),
                "generation_catalog_model": self._catalog_model(generation_code),
                "evaluation_catalog_model": self._catalog_model(evaluation_code),
                "active_prompt_count": active_prompt_count,
                "active_evaluation_policy": active_policy or FALLBACK_EVALUATION_POLICY,
                "warnings": warnings,
                "supported_provider_patterns": [
                    "qwen",
                    "gemini",
                    "deepseek",
                    "deepseek-r1",
                    "ollama:<model-name>",
                ],
            }
        )

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
        return json_safe({**record, "factory_status": self._model_factory_status(record["model_code"])})

    def set_ai_model_active(self, payload: AiModelActivationPayload) -> dict:
        now = utc_now()
        record = self.db.ai_models.find_one_and_update(
            {"model_code": payload.model_code},
            {"$set": {"is_active": payload.is_active, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not record:
            raise LookupError("Không tìm thấy model")
        return json_safe({**record, "factory_status": self._model_factory_status(record["model_code"])})

    async def check_ai_model_health(self, payload: AiModelHealthCheckPayload) -> dict:
        started = time.perf_counter()
        factory_status = self._model_factory_status(payload.model_code)
        if not factory_status["supported"]:
            snapshot = {
                "status": "UNSUPPORTED",
                "latency_ms": 0,
                "response_preview": "",
                "error": factory_status.get("error"),
                "checked_at": utc_now(),
            }
            if self._catalog_model(payload.model_code):
                self.db.ai_models.find_one_and_update(
                    {"model_code": payload.model_code},
                    {"$set": {"last_health_check": snapshot, "updated_at": snapshot["checked_at"]}},
                    return_document=ReturnDocument.AFTER,
                )
            return json_safe({
                "model_code": payload.model_code,
                "factory_status": factory_status,
                **snapshot,
            })
        try:
            provider = get_llm_service(payload.model_code)
            response_text = await asyncio.wait_for(
                provider.generate_text(payload.prompt),
                timeout=payload.timeout_seconds,
            )
            status = "OK"
            error = None
        except Exception as exc:
            response_text = ""
            status = "FAILED"
            error = str(exc)
        latency_ms = round((time.perf_counter() - started) * 1000)
        snapshot = {
            "status": status,
            "latency_ms": latency_ms,
            "response_preview": response_text[:500],
            "error": error,
            "checked_at": utc_now(),
        }
        if self._catalog_model(payload.model_code):
            self.db.ai_models.find_one_and_update(
                {"model_code": payload.model_code},
                {"$set": {"last_health_check": snapshot, "updated_at": snapshot["checked_at"]}},
                return_document=ReturnDocument.AFTER,
            )
        return json_safe(
            {
                "model_code": payload.model_code,
                "factory_status": factory_status,
                **snapshot,
            }
        )

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

    def activate_prompt_template(self, payload: PromptTemplateActivationPayload) -> dict:
        now = utc_now()
        query = {"template_key": payload.template_key, "version": payload.version}
        if not self.db.prompt_templates.find_one(query):
            raise LookupError("Không tìm thấy prompt version")
        if payload.is_active:
            self.db.prompt_templates.update_many(
                {"template_key": payload.template_key},
                {"$set": {"is_active": False, "updated_at": now}},
            )
        record = self.db.prompt_templates.find_one_and_update(
            query,
            {"$set": {"is_active": payload.is_active, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return json_safe(record)

    def test_prompt_template(self, payload: PromptTemplateTestPayload) -> dict:
        template_keys = [
            "system",
            "question_rule",
            f"bloom:{payload.bloom_level}",
            f"question_type:{payload.question_type}",
            "output_format",
        ]
        effective_sources = {}
        for key in template_keys:
            active_db = self.db.prompt_templates.find_one(
                {"template_key": key, "is_active": True},
                sort=[("version", -1)],
            )
            effective_sources[key] = (
                "db"
                if settings.prompt_source == "db" and active_db
                else "file"
            )
        try:
            rendered = PromptBuilder().build(
                context=payload.context,
                bloom_level=payload.bloom_level,
                question_type=payload.question_type,
                num_questions=payload.num_questions,
                instruction=payload.instruction,
            )
        except Exception as exc:
            raise ValueError(f"Không build được prompt mẫu: {exc}") from exc
        warnings = []
        if settings.prompt_source != "db":
            warnings.append("Prompt DB chưa có hiệu lực vì PROMPT_SOURCE không phải db.")
        return {
            "prompt_source": settings.prompt_source,
            "effective_sources": effective_sources,
            "rendered_prompt": rendered,
            "length": len(rendered),
            "warnings": warnings,
        }

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

    def activate_evaluation_policy(self, payload: EvaluationPolicyActivationPayload) -> dict:
        now = utc_now()
        query = {"policy_name": payload.policy_name, "version": payload.version}
        if not self.db.evaluation_policies.find_one(query):
            raise LookupError("Không tìm thấy policy version")
        if payload.is_active:
            self.db.evaluation_policies.update_many(
                {"policy_name": payload.policy_name},
                {"$set": {"is_active": False, "updated_at": now}},
            )
        record = self.db.evaluation_policies.find_one_and_update(
            query,
            {"$set": {"is_active": payload.is_active, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return json_safe(record)

    def overview(self) -> dict[str, Any]:
        return {
            "subjects": self.list_subjects(),
            "ai_models": self.list_ai_models(),
            "prompt_templates": self.list_prompt_templates(),
            "evaluation_policies": self.list_evaluation_policies(),
            "runtime_config": self.runtime_config(),
        }


def get_catalog_service() -> CatalogService:
    return CatalogService(get_database())
