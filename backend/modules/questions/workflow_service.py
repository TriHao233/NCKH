import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.bootstrap import SCHEMA_VERSION
from core.config import settings
from core.database import get_database, mongo_transaction
from core.dependencies import CurrentUser
from modules.admin.moodle_service import MoodleTargetService
from modules.generation.llm.factory import get_llm_service
from modules.generation.prompt_builder import PromptBuilder
from modules.questions.repository import MongoQuestionRepository, json_safe, object_id, serialize_question, utc_now
from modules.questions.workflow_schemas import (
    AutoEvaluationRequest,
    EvaluationCreateRequest,
    EvaluationScores,
    MoodlePublicationRequest,
    ReviewAssignmentRequest,
    ReviewCreateRequest,
)

DEFAULT_WEIGHTS = {
    "faithfulness": 0.35,
    "contextual_relevancy": 0.20,
    "answer_relevancy": 0.15,
    "bloom_alignment": 0.15,
    "clo_alignment": 0.15,
}
DEFAULT_THRESHOLDS = {"yellow_min": 0.60, "green_min": 0.80, "pass_min": 0.80}
EVALUATION_PROMPT_KEY = "evaluation:question_quality"
EVALUATION_PROMPT_PATH = "evaluation/question_quality.txt"
DEFAULT_EVALUATOR_MODEL_CODE = settings.evaluation_model_provider
EVALUATION_ACTIVE_STATUSES = {"QUEUED", "PROCESSING"}
EVALUATION_RETRYABLE_STATUSES = {"NOT_STARTED", "FAILED", "ERROR", "STALE"}
EVALUATION_SOURCE_LIMIT = 3
EVALUATION_SOURCE_EXCERPT_CHARS = 700
evaluation_semaphore = asyncio.Semaphore(1)


def _empty_review_assignment(now=None, reason: str | None = None) -> dict:
    return {
        "status": "UNASSIGNED",
        "reviewer_user_id": None,
        "assigned_by_user_id": None,
        "assigned_at": None,
        "claimed_at": None,
        "lock_expires_at": None,
        "last_released_at": now,
        "release_reason": reason,
    }


def _as_aware_utc(value):
    if not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class QuestionWorkflowService:
    def __init__(self, database):
        self.db = database
        self.questions = MongoQuestionRepository(database)

    def _pair(self, question_id: str) -> tuple[dict, dict]:
        pair = self.questions.find_pair(question_id)
        if not pair:
            raise LookupError("Không tìm thấy câu hỏi")
        return pair

    def _owns_question(self, question: dict, version: dict, user_id: ObjectId) -> bool:
        if question.get("created_by_user_id") == user_id:
            return True
        if version.get("created_by_user_id") == user_id:
            return True
        document_id = version.get("document_id")
        if document_id:
            document = self.db.documents.find_one(
                {
                    "_id": document_id,
                    "schema_version": SCHEMA_VERSION,
                    "archived_at": None,
                },
                {"uploaded_by_user_id": 1},
            )
            if document and document.get("uploaded_by_user_id") == user_id:
                return True
        return False

    def _ensure_read_access(
        self,
        question: dict,
        version: dict,
        current_user: CurrentUser | None,
    ) -> None:
        if not current_user or current_user.role in {"Admin", "Reviewer"}:
            return
        if not self._owns_question(question, version, current_user.id):
            raise PermissionError("Bạn không có quyền truy cập câu hỏi này")

    def _policy(self) -> dict:
        return self.db.evaluation_policies.find_one(
            {"is_active": True},
            sort=[("version", -1)],
        ) or {
            "_id": None,
            "policy_name": "Default fallback",
            "version": 1,
            "weights": DEFAULT_WEIGHTS,
            "thresholds": DEFAULT_THRESHOLDS,
        }

    def _model_snapshot(self, model_code: str) -> dict:
        model = self.db.ai_models.find_one({"model_code": model_code, "is_active": True})
        if not model:
            return {
                "id": None,
                "model_code": model_code,
                "model_name": model_code,
                "config": {},
            }
        return {
            "id": model["_id"],
            "model_code": model["model_code"],
            "model_name": model.get("model_name"),
            "runtime": model.get("runtime"),
            "revision": model.get("revision"),
            "capabilities": model.get("capabilities") or [],
            "config": model.get("config") or {},
        }

    @staticmethod
    def _tokens(text: str) -> set[str]:
        normalized = (text or "").lower()
        return {
            token
            for token in re.findall(r"[\wÀ-ỹ]+", normalized, flags=re.UNICODE)
            if len(token) >= 3
        }

    @classmethod
    def _overlap_score(cls, text: str, context: str) -> float:
        text_tokens = cls._tokens(text)
        if not text_tokens:
            return 0.0
        context_tokens = cls._tokens(context)
        if not context_tokens:
            return 0.0
        return len(text_tokens & context_tokens) / len(text_tokens)

    @staticmethod
    def _clamp(score: float) -> float:
        return round(max(0.0, min(1.0, score)), 4)

    @staticmethod
    def _clean_json(text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
        cleaned = re.sub(r"```json|```", "", cleaned).strip()
        match = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
        return match.group(1) if match else cleaned

    @staticmethod
    def _compact_text(text: str, limit: int) -> str:
        compacted = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(compacted) <= limit:
            return compacted
        return compacted[: max(0, limit - 3)].rstrip() + "..."

    @classmethod
    def _compact_sources(
        cls,
        version: dict,
        *,
        max_sources: int = EVALUATION_SOURCE_LIMIT,
        excerpt_chars: int = EVALUATION_SOURCE_EXCERPT_CHARS,
    ) -> list[dict]:
        sources = sorted(
            version.get("sources") or [],
            key=lambda source: source.get("citation_order") or 999,
        )
        compacted = []
        for index, source in enumerate(sources[:max_sources], start=1):
            excerpt = cls._compact_text(source.get("context_excerpt") or "", excerpt_chars)
            compacted.append(
                {
                    "label": f"S{index}",
                    "chunk_id": source.get("chunk_id"),
                    "content_hash": source.get("chunk_content_hash"),
                    "citation_order": source.get("citation_order") or index,
                    "is_primary": bool(source.get("is_primary")),
                    "excerpt": excerpt,
                    "excerpt_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                }
            )
        return compacted

    @staticmethod
    def _source_context(version: dict) -> str:
        return "\n\n".join(
            f"[{source['label']}] {source['excerpt']}"
            for source in QuestionWorkflowService._compact_sources(version)
            if source.get("excerpt")
        )

    def _evaluation_prompt_template(self) -> str:
        return PromptBuilder._load_template(
            EVALUATION_PROMPT_KEY,
            EVALUATION_PROMPT_PATH,
        )

    def _build_evaluation_prompt(
        self,
        question: dict,
        version: dict,
        policy: dict | None = None,
    ) -> tuple[str, dict, list[dict]]:
        question_data = version.get("question_data") or {}
        classification = version.get("classification") or {}
        source_chunks = self._compact_sources(version)
        policy = policy or self._policy()
        clos = [
            {
                "code": clo.get("code") or clo.get("clo_code"),
                "description": self._compact_text(clo.get("description") or "", 300),
            }
            for clo in (version.get("clos") or [])
        ]
        payload = {
            "question_code": question.get("question_code"),
            "question_id": question.get("_id"),
            "question_version_id": version.get("_id"),
            "document_id": version.get("document_id"),
            "question_type": classification.get("assessment_type"),
            "question": version.get("content"),
            "options": question_data.get("options"),
            "correct_answer": question_data.get("correct_answer"),
            "explanation": question_data.get("explanation"),
            "requested_bloom": classification.get("bloom"),
            "clos": clos,
            "source_chunks": source_chunks,
        }
        policy_payload = {
            "name": policy.get("policy_name") or policy.get("name"),
            "version": policy.get("version"),
            "weights": policy.get("weights") or DEFAULT_WEIGHTS,
            "thresholds": policy.get("thresholds") or DEFAULT_THRESHOLDS,
        }
        template = self._evaluation_prompt_template()
        prompt = template.format(
            evaluation_policy=json.dumps(policy_payload, ensure_ascii=False, default=str),
            question_payload=json.dumps(payload, ensure_ascii=False, default=str),
        )
        prompt_snapshot = {
            "template_key": EVALUATION_PROMPT_KEY,
            "template_path": EVALUATION_PROMPT_PATH,
            "template_hash": hashlib.sha256(template.encode("utf-8")).hexdigest(),
            "rendered_prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "rendered_prompt_chars": len(prompt),
            "source_limit": EVALUATION_SOURCE_LIMIT,
            "source_excerpt_chars": EVALUATION_SOURCE_EXCERPT_CHARS,
        }
        return prompt, prompt_snapshot, source_chunks

    def _evaluation_prompt(self, question: dict, version: dict, policy: dict | None = None) -> str:
        prompt, _, _ = self._build_evaluation_prompt(question, version, policy)
        return prompt

    @classmethod
    def _parse_llm_evaluation(cls, raw_response: str) -> tuple[EvaluationScores, dict, dict]:
        parsed = json.loads(cls._clean_json(raw_response))
        raw_scores = parsed.get("scores") or {}
        scores = EvaluationScores(
            faithfulness=cls._clamp(float(raw_scores.get("faithfulness", 0))),
            contextual_relevancy=cls._clamp(float(raw_scores.get("contextual_relevancy", 0))),
            answer_relevancy=cls._clamp(float(raw_scores.get("answer_relevancy", 0))),
            bloom_alignment=cls._clamp(float(raw_scores.get("bloom_alignment", 0))),
            clo_alignment=cls._clamp(float(raw_scores.get("clo_alignment", 0))),
        )
        feedback = parsed.get("feedback") if isinstance(parsed.get("feedback"), dict) else {}
        evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), dict) else {}
        return scores, feedback, evidence

    def _auto_scores(self, question: dict, version: dict) -> tuple[EvaluationScores, dict, dict]:
        question_data = version.get("question_data") or {}
        sources = version.get("sources") or []
        source_context = self._source_context(version)
        content = version.get("content") or ""
        answer = str(question_data.get("correct_answer") or "")
        explanation = str(question_data.get("explanation") or "")
        answer_block = " ".join([content, answer, explanation]).strip()

        question_overlap = self._overlap_score(content, source_context)
        answer_overlap = self._overlap_score(answer_block, source_context)
        has_answer = bool(answer.strip())
        has_explanation = bool(explanation.strip())
        has_context = bool(source_context.strip())
        has_bloom = bool((version.get("classification") or {}).get("bloom", {}).get("level"))
        has_clo = bool(version.get("clos") or [])

        scores = EvaluationScores(
            faithfulness=self._clamp(0.50 + 0.50 * answer_overlap if has_context else 0.45),
            contextual_relevancy=self._clamp(0.45 + 0.45 * question_overlap + min(len(sources), 3) * 0.03 if has_context else 0.35),
            answer_relevancy=self._clamp(0.50 + (0.25 if has_answer else 0.0) + (0.20 if has_explanation else 0.0) + 0.05 * min(len(answer), 40) / 40),
            bloom_alignment=0.86 if has_bloom else 0.50,
            clo_alignment=0.86 if has_clo else 0.62,
        )
        feedback = {
            "summary": (
                "Đánh giá tự động bằng heuristic nội bộ phục vụ demo P0; "
                "cần thay bằng local evaluator model ở bản production."
            ),
            "missing": [
                label
                for label, missing in (
                    ("Không có source context", not has_context),
                    ("Thiếu đáp án đúng", not has_answer),
                    ("Thiếu giải thích", not has_explanation),
                    ("Chưa gắn CLO", not has_clo),
                )
                if missing
            ],
        }
        evidence = {
            "source_count": len(sources),
            "question_context_overlap": round(question_overlap, 4),
            "answer_context_overlap": round(answer_overlap, 4),
            "source_excerpt": source_context[:1200],
            "checks": {
                "has_context": has_context,
                "has_answer": has_answer,
                "has_explanation": has_explanation,
                "has_bloom": has_bloom,
                "has_clo": has_clo,
            },
        }
        return scores, feedback, evidence

    def evaluate(self, question_id: str, payload: EvaluationCreateRequest, user_id) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        policy = payload.policy_snapshot or self._policy()
        scores = payload.scores.model_dump()
        overall = round(
            sum(scores[key] * policy["weights"][key] for key in DEFAULT_WEIGHTS),
            4,
        )
        thresholds = policy["thresholds"]
        color = (
            "GREEN"
            if overall >= thresholds["green_min"]
            else "YELLOW"
            if overall >= thresholds["yellow_min"]
            else "RED"
        )
        passed = overall >= thresholds["pass_min"]
        now = utc_now()
        evaluation_job_id = (
            object_id(payload.evaluation_job_id, "evaluation_job_id")
            if payload.evaluation_job_id
            else None
        )
        evaluation = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "question_id": question["_id"],
            "question_version_id": version["_id"],
            "question_version": version["version"],
            "question_snapshot_hash": version["content_hash"],
            "generation_run_id": version.get("generation_run_id"),
            "evaluator_model": self._model_snapshot(payload.evaluator_model_code),
            "requested_by_user_id": user_id,
            "policy": {
                "id": policy.get("_id") or policy.get("id"),
                "name": policy.get("policy_name") or policy.get("name"),
                "version": policy["version"],
                "weights": policy["weights"],
                "thresholds": thresholds,
            },
            "scores": {**scores, "overall": overall},
            "color": color,
            "passed": passed,
            "feedback": payload.feedback,
            "evidence": payload.evidence,
            "raw_model_response": payload.raw_model_response,
            "prompt_snapshot": payload.prompt_snapshot,
            "duration_ms": payload.duration_ms,
            "evaluation_job_id": evaluation_job_id,
            "trigger": payload.trigger,
            "parser_version": "evaluation-json-v1",
            "created_at": now,
        }
        audit = {
            "schema_version": SCHEMA_VERSION,
            "actor": {
                "type": "USER",
                "user_id": user_id,
                "model_id": evaluation["evaluator_model"].get("id"),
                "service_name": "question_evaluation",
            },
            "entity": {
                "type": "QUESTION",
                "id": question["_id"],
                "version_id": version["_id"],
            },
            "action": "QUESTION_EVALUATED",
            "changes": [
                {
                    "path": "quality_summary",
                    "old_value": question.get("quality_summary") or {},
                    "new_value": {
                        "latest_evaluation_id": evaluation["_id"],
                        "overall_score": overall,
                        "color": color,
                    },
                }
            ],
            "before_hash": version["content_hash"],
            "after_hash": version["content_hash"],
            "metadata": {
                "evaluation_id": evaluation["_id"],
                "correlation_id": str(evaluation["_id"]),
            },
            "created_at": now,
        }
        with mongo_transaction() as session:
            self.db.question_evaluations.insert_one(evaluation, session=session)
            result = self.db.questions.update_one(
                {
                    "_id": question["_id"],
                    "current_version_id": version["_id"],
                    "lifecycle_status": "ACTIVE",
                },
                {
                    "$set": {
                        "evaluation_status": "PASSED" if passed else "FAILED",
                        "quality_summary": {
                            "latest_evaluation_id": evaluation["_id"],
                            "latest_evaluation_job_id": evaluation_job_id,
                            "evaluated_version_id": version["_id"],
                            "overall_score": overall,
                            "color": color,
                            "evaluated_at": now,
                            "evaluator_model_code": evaluation["evaluator_model"].get("model_code"),
                        },
                        "updated_at": now,
                    }
                },
                session=session,
            )
            if not result.matched_count:
                raise RuntimeError("VERSION_CONFLICT")
            self.db.audit_logs.insert_one(audit, session=session)
        return json_safe(evaluation)

    async def auto_evaluate(self, question_id: str, payload: AutoEvaluationRequest, user_id) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        raw_model_response = None
        evaluator_code = payload.evaluator_model_code.strip()
        prompt_snapshot: dict = {}
        policy_snapshot: dict = {}
        duration_ms = None
        if evaluator_code.lower() in {"local-heuristic-evaluator-v1", "heuristic"}:
            scores, feedback, evidence = self._auto_scores(question, version)
            evidence["mode"] = "heuristic"
            evaluator_code = "local-heuristic-evaluator-v1"
        else:
            try:
                llm = get_llm_service(evaluator_code)
                policy = self._policy()
                policy_snapshot = self._policy_snapshot(policy)
                prompt, prompt_snapshot, _ = self._build_evaluation_prompt(question, version, policy)
                started = time.perf_counter()
                raw_model_response = await llm.generate_text(prompt)
                duration_ms = int((time.perf_counter() - started) * 1000)
                scores, feedback, evidence = self._parse_llm_evaluation(raw_model_response)
                evidence["mode"] = "local_llm"
            except Exception as exc:
                if not payload.fallback_to_heuristic:
                    raise ValueError(f"Local evaluator failed: {exc}") from exc
                scores, feedback, evidence = self._auto_scores(question, version)
                evaluator_code = "local-heuristic-evaluator-v1"
                feedback = {
                    **feedback,
                    "summary": (
                        "Local evaluator không chạy hoặc trả JSON không hợp lệ; "
                        "đã fallback sang heuristic nội bộ."
                    ),
                }
                evidence = {
                    **evidence,
                    "mode": "heuristic_fallback",
                    "fallback_reason": str(exc),
                    "raw_model_response": raw_model_response,
                }
        return self.evaluate(
            question_id,
            EvaluationCreateRequest(
                expected_version=payload.expected_version,
                scores=scores,
                feedback=feedback,
                evidence=evidence,
                evaluator_model_code=evaluator_code,
                raw_model_response=raw_model_response,
                policy_snapshot=policy_snapshot,
                prompt_snapshot=prompt_snapshot,
                duration_ms=duration_ms,
                trigger="DIRECT_AUTO_EVALUATION",
            ),
            user_id,
        )

    @staticmethod
    def _policy_snapshot(policy: dict) -> dict:
        return {
            "id": policy.get("_id"),
            "name": policy.get("policy_name"),
            "version": policy.get("version"),
            "weights": policy.get("weights") or DEFAULT_WEIGHTS,
            "thresholds": policy.get("thresholds") or DEFAULT_THRESHOLDS,
        }

    @staticmethod
    def _evaluation_dedupe_key(version: dict, evaluator_model_code: str) -> str:
        material = "|".join(
            [
                str(version.get("_id")),
                str(version.get("content_hash") or ""),
                evaluator_model_code.strip().lower(),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def enqueue_auto_evaluation(
        self,
        question_id: str,
        *,
        expected_version: int,
        requested_by_user_id,
        evaluator_model_code: str = DEFAULT_EVALUATOR_MODEL_CODE,
        trigger: str = "REVIEWER_REQUEST",
    ) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != expected_version:
            raise RuntimeError("VERSION_CONFLICT")

        evaluator_model_code = evaluator_model_code.strip() or DEFAULT_EVALUATOR_MODEL_CODE
        if question.get("evaluation_status") == "PASSED":
            raise ValueError("Câu hỏi đã có kết quả AI đạt cho phiên bản hiện tại")

        dedupe_key = self._evaluation_dedupe_key(version, evaluator_model_code)
        active_job = self.db.evaluation_jobs.find_one(
            {"dedupe_key": dedupe_key, "status": {"$in": list(EVALUATION_ACTIVE_STATUSES)}}
        )
        if active_job:
            return json_safe(active_job)

        policy = self._policy()
        _, prompt_snapshot, source_chunks = self._build_evaluation_prompt(question, version, policy)
        now = utc_now()
        attempt_no = (
            self.db.evaluation_jobs.count_documents(
                {
                    "question_version_id": version["_id"],
                    "evaluator_model_code": evaluator_model_code,
                }
            )
            + 1
        )
        job = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "question_id": question["_id"],
            "question_version_id": version["_id"],
            "question_version": version["version"],
            "question_snapshot_hash": version.get("content_hash"),
            "dedupe_key": dedupe_key,
            "status": "QUEUED",
            "trigger": trigger,
            "requested_by_user_id": requested_by_user_id,
            "evaluator_model_code": evaluator_model_code,
            "policy_snapshot": self._policy_snapshot(policy),
            "prompt_snapshot": prompt_snapshot,
            "source_snapshot": [
                {
                    "label": source.get("label"),
                    "chunk_id": source.get("chunk_id"),
                    "content_hash": source.get("content_hash"),
                    "citation_order": source.get("citation_order"),
                    "excerpt_hash": source.get("excerpt_hash"),
                }
                for source in source_chunks
            ],
            "attempt_no": attempt_no,
            "max_attempts": 1,
            "result": None,
            "error": None,
            "queued_at": now,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "updated_at": now,
        }

        try:
            with mongo_transaction() as session:
                self.db.evaluation_jobs.insert_one(job, session=session)
                result = self.db.questions.update_one(
                    {
                        "_id": question["_id"],
                        "current_version_id": version["_id"],
                        "lifecycle_status": "ACTIVE",
                        "evaluation_status": {"$in": list(EVALUATION_RETRYABLE_STATUSES)},
                    },
                    {
                        "$set": {
                            "evaluation_status": "QUEUED",
                            "quality_summary": {
                                "latest_evaluation_job_id": job["_id"],
                                "evaluated_version_id": version["_id"],
                                "evaluation_queued_at": now,
                                "evaluator_model_code": evaluator_model_code,
                            },
                            "updated_at": now,
                        }
                    },
                    session=session,
                )
                if not result.matched_count:
                    self.db.evaluation_jobs.update_one(
                        {"_id": job["_id"]},
                        {
                            "$set": {
                                "status": "STALE",
                                "error": {
                                    "message": "Phiên bản câu hỏi đã đổi trước khi enqueue evaluation",
                                    "at": utc_now(),
                                },
                                "updated_at": utc_now(),
                            }
                        },
                        session=session,
                    )
                    raise RuntimeError("VERSION_CONFLICT")
        except DuplicateKeyError:
            active_job = self.db.evaluation_jobs.find_one(
                {"dedupe_key": dedupe_key, "status": {"$in": list(EVALUATION_ACTIVE_STATUSES)}}
            )
            if active_job:
                return json_safe(active_job)
            raise
        return json_safe(job)

    def _mark_evaluation_job_error(
        self,
        job: dict,
        message: str,
        *,
        status: str = "ERROR",
        raw_model_response: str | None = None,
        duration_ms: int | None = None,
    ) -> dict:
        now = utc_now()
        error = {
            "message": message,
            "raw_model_response_excerpt": (raw_model_response or "")[:1200] or None,
            "at": now,
        }
        with mongo_transaction() as session:
            self.db.evaluation_jobs.update_one(
                {"_id": job["_id"], "status": {"$in": ["QUEUED", "PROCESSING"]}},
                {
                    "$set": {
                        "status": status,
                        "error": error,
                        "finished_at": now,
                        "duration_ms": duration_ms,
                        "updated_at": now,
                    }
                },
                session=session,
            )
            if status != "STALE":
                self.db.questions.update_one(
                    {
                        "_id": job["question_id"],
                        "current_version_id": job["question_version_id"],
                        "lifecycle_status": "ACTIVE",
                    },
                    {
                        "$set": {
                            "evaluation_status": "ERROR",
                            "quality_summary": {
                                "latest_evaluation_job_id": job["_id"],
                                "evaluated_version_id": job["question_version_id"],
                                "evaluator_model_code": job.get("evaluator_model_code"),
                                "error": error,
                            },
                            "updated_at": now,
                        }
                    },
                    session=session,
                )
        return json_safe({**job, "status": status, "error": error, "finished_at": now})

    async def process_evaluation_job(self, job_id: str) -> dict | None:
        job_oid = object_id(job_id, "evaluation_job_id")
        now = utc_now()
        job = self.db.evaluation_jobs.find_one_and_update(
            {"_id": job_oid, "status": "QUEUED"},
            {"$set": {"status": "PROCESSING", "started_at": now, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not job:
            return None

        question = self.db.questions.find_one(
            {
                "_id": job["question_id"],
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
            }
        )
        version = self.db.question_versions.find_one({"_id": job["question_version_id"]})
        if not question or not version or question.get("current_version_id") != job["question_version_id"]:
            return self._mark_evaluation_job_error(
                job,
                "Phiên bản câu hỏi đã thay đổi trước khi AI đánh giá",
                status="STALE",
            )

        self.db.questions.update_one(
            {
                "_id": question["_id"],
                "current_version_id": version["_id"],
                "evaluation_status": "QUEUED",
            },
            {
                "$set": {
                    "evaluation_status": "PROCESSING",
                    "quality_summary.latest_evaluation_job_id": job["_id"],
                    "quality_summary.evaluation_started_at": now,
                    "updated_at": now,
                }
            },
        )

        raw_model_response = None
        started = time.perf_counter()
        try:
            prompt, prompt_snapshot, _ = self._build_evaluation_prompt(
                question,
                version,
                job.get("policy_snapshot") or self._policy(),
            )
            llm = get_llm_service(job.get("evaluator_model_code") or DEFAULT_EVALUATOR_MODEL_CODE)
            raw_model_response = await llm.generate_text(prompt)
            duration_ms = int((time.perf_counter() - started) * 1000)
            scores, feedback, evidence = self._parse_llm_evaluation(raw_model_response)
            evidence = {
                **evidence,
                "mode": "local_llm",
                "evaluation_job_id": str(job["_id"]),
                "source_snapshot": json_safe(job.get("source_snapshot") or []),
            }
            evaluation = self.evaluate(
                str(question["_id"]),
                EvaluationCreateRequest(
                    expected_version=version["version"],
                    scores=scores,
                    feedback=feedback,
                    evidence=evidence,
                    evaluator_model_code=job.get("evaluator_model_code") or DEFAULT_EVALUATOR_MODEL_CODE,
                    raw_model_response=raw_model_response,
                    policy_snapshot=job.get("policy_snapshot") or {},
                    prompt_snapshot=prompt_snapshot,
                    duration_ms=duration_ms,
                    evaluation_job_id=str(job["_id"]),
                    trigger=job.get("trigger"),
                ),
                job.get("requested_by_user_id"),
            )
            finished_at = utc_now()
            self.db.evaluation_jobs.update_one(
                {"_id": job["_id"], "status": "PROCESSING"},
                {
                    "$set": {
                        "status": "COMPLETED",
                        "result": {
                            "evaluation_id": object_id(evaluation.get("_id"), "evaluation_id"),
                            "passed": evaluation.get("passed"),
                            "overall_score": (evaluation.get("scores") or {}).get("overall"),
                            "color": evaluation.get("color"),
                        },
                        "duration_ms": duration_ms,
                        "finished_at": finished_at,
                        "updated_at": finished_at,
                    }
                },
            )
            return evaluation
        except RuntimeError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            if str(exc) == "VERSION_CONFLICT":
                return self._mark_evaluation_job_error(
                    job,
                    "Phiên bản câu hỏi đã thay đổi trong lúc AI đánh giá",
                    status="STALE",
                    raw_model_response=raw_model_response,
                    duration_ms=duration_ms,
                )
            return self._mark_evaluation_job_error(
                job,
                str(exc),
                raw_model_response=raw_model_response,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return self._mark_evaluation_job_error(
                job,
                str(exc),
                raw_model_response=raw_model_response,
                duration_ms=duration_ms,
            )

    def _lock_expires_at(self, now) -> object:
        return now + timedelta(minutes=max(1, settings.review_lock_timeout_minutes))

    def _assignment_available_filter(self, current_user: CurrentUser, now) -> list[dict]:
        if current_user.role == "Admin":
            return []
        return [
            {"review_assignment": {"$exists": False}},
            {"review_assignment.status": "UNASSIGNED"},
            {"review_assignment.reviewer_user_id": current_user.id},
            {"review_assignment.lock_expires_at": None},
            {"review_assignment.lock_expires_at": {"$lte": now}},
        ]

    def _ensure_review_lock(self, question: dict, current_user: CurrentUser, now) -> None:
        if current_user.role == "Admin":
            return
        assignment = question.get("review_assignment") or {}
        if assignment.get("status") != "IN_REVIEW":
            raise PermissionError("Bạn cần claim câu hỏi trước khi kiểm duyệt")
        if assignment.get("reviewer_user_id") != current_user.id:
            raise PermissionError("Câu hỏi đang được Reviewer khác xử lý")
        lock_expires_at = _as_aware_utc(assignment.get("lock_expires_at"))
        if lock_expires_at and lock_expires_at <= _as_aware_utc(now):
            raise ValueError("Review lock đã hết hạn; vui lòng claim lại")

    def _find_assignable_reviewer(self, reviewer_user_id: str) -> dict:
        reviewer_oid = object_id(reviewer_user_id, "reviewer_user_id")
        reviewer = self.db.users.find_one(
            {
                "_id": reviewer_oid,
                "role": {"$in": ["Reviewer", "Admin"]},
                "is_active": True,
            },
            {"_id": 1, "display_name": 1, "email": 1, "role": 1},
        )
        if not reviewer:
            raise ValueError("Reviewer không tồn tại hoặc không còn hoạt động")
        return reviewer

    def _assignment_audit(
        self,
        *,
        action: str,
        question: dict,
        version: dict,
        current_user: CurrentUser,
        before: dict | None = None,
        after: dict | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.db.audit_logs.insert_one(
            {
                "schema_version": SCHEMA_VERSION,
                "actor": {
                    "type": "USER",
                    "user_id": current_user.id,
                    "model_id": None,
                    "service_name": None,
                },
                "entity": {
                    "type": "QUESTION",
                    "id": question["_id"],
                    "version_id": version["_id"],
                },
                "action": action,
                "changes": [
                    {
                        "path": "review_assignment",
                        "old_value": before or {},
                        "new_value": after or {},
                    }
                ],
                "before_hash": version["content_hash"],
                "after_hash": version["content_hash"],
                "metadata": metadata or {},
                "created_at": utc_now(),
            }
        )

    def claim_review(self, question_id: str, current_user: CurrentUser) -> dict:
        pair = self._pair(question_id)
        question, version = pair
        if question["review_status"] != "PENDING":
            raise ValueError("Chỉ câu hỏi đang chờ duyệt mới có thể claim")
        now = utc_now()
        previous_assignment = question.get("review_assignment") or {}
        assignment = {
            "status": "IN_REVIEW",
            "reviewer_user_id": current_user.id,
            "assigned_by_user_id": previous_assignment.get("assigned_by_user_id")
            or current_user.id,
            "assigned_at": previous_assignment.get("assigned_at") or now,
            "claimed_at": now,
            "lock_expires_at": self._lock_expires_at(now),
            "last_released_at": None,
            "release_reason": None,
        }
        query = {
            "_id": question["_id"],
            "current_version_id": version["_id"],
            "lifecycle_status": "ACTIVE",
            "review_status": "PENDING",
        }
        available_filter = self._assignment_available_filter(current_user, now)
        if available_filter:
            query["$or"] = available_filter
        updated = self.db.questions.find_one_and_update(
            query,
            {"$set": {"review_assignment": assignment, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise PermissionError("Câu hỏi đang được Reviewer khác xử lý")
        self._assignment_audit(
            action="QUESTION_REVIEW_CLAIMED",
            question=updated,
            version=version,
            current_user=current_user,
            before=question.get("review_assignment"),
            after=assignment,
        )
        return serialize_question(updated, version)

    def release_review(self, question_id: str, current_user: CurrentUser) -> dict:
        pair = self._pair(question_id)
        question, version = pair
        now = utc_now()
        query = {
            "_id": question["_id"],
            "current_version_id": version["_id"],
            "lifecycle_status": "ACTIVE",
            "review_status": "PENDING",
        }
        if current_user.role != "Admin":
            query["review_assignment.reviewer_user_id"] = current_user.id
        assignment = _empty_review_assignment(now, "released")
        updated = self.db.questions.find_one_and_update(
            query,
            {"$set": {"review_assignment": assignment, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise PermissionError("Bạn không thể release assignment này")
        self._assignment_audit(
            action="QUESTION_REVIEW_RELEASED",
            question=updated,
            version=version,
            current_user=current_user,
            before=question.get("review_assignment"),
            after=assignment,
        )
        return serialize_question(updated, version)

    def assign_review(
        self,
        question_id: str,
        payload: ReviewAssignmentRequest,
        current_user: CurrentUser,
    ) -> dict:
        pair = self._pair(question_id)
        question, version = pair
        if question["review_status"] != "PENDING":
            raise ValueError("Chỉ câu hỏi đang chờ duyệt mới có thể phân công")
        now = utc_now()
        if payload.reviewer_user_id:
            reviewer = self._find_assignable_reviewer(payload.reviewer_user_id)
            assignment = {
                "status": "ASSIGNED",
                "reviewer_user_id": reviewer["_id"],
                "assigned_by_user_id": current_user.id,
                "assigned_at": now,
                "claimed_at": None,
                "lock_expires_at": self._lock_expires_at(now),
                "last_released_at": None,
                "release_reason": payload.note or None,
            }
            action = "QUESTION_REVIEW_ASSIGNED"
        else:
            assignment = _empty_review_assignment(now, payload.note or "unassigned")
            action = "QUESTION_REVIEW_UNASSIGNED"
        updated = self.db.questions.find_one_and_update(
            {
                "_id": question["_id"],
                "current_version_id": version["_id"],
                "lifecycle_status": "ACTIVE",
                "review_status": "PENDING",
            },
            {"$set": {"review_assignment": assignment, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise RuntimeError("VERSION_CONFLICT")
        self._assignment_audit(
            action=action,
            question=updated,
            version=version,
            current_user=current_user,
            before=question.get("review_assignment"),
            after=assignment,
            metadata={"note": payload.note},
        )
        return serialize_question(updated, version)

    def review(self, question_id: str, payload: ReviewCreateRequest, current_user: CurrentUser) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        if (
            payload.decision == "APPROVED"
            and question["evaluation_status"] != "PASSED"
            and not payload.override.applied
        ):
            raise ValueError(
                "Chỉ có thể duyệt phiên bản đã vượt đánh giá, hoặc phải ghi rõ override"
            )
        now = utc_now()
        self._ensure_review_lock(question, current_user, now)
        review_form = payload.review_form.model_dump()
        review_note = payload.note or payload.review_form.overall_note
        review = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "question_id": question["_id"],
            "question_version_id": version["_id"],
            "question_version": version["version"],
            "reviewer_user_id": current_user.id,
            "decision": payload.decision,
            "note": review_note,
            "override": payload.override.model_dump(),
            "review_form": review_form,
            "revision_issues": review_form.get("revision_issues", []),
            "supersedes_review_id": question.get("latest_review_id"),
            "previous_status": question["review_status"],
            "resulting_status": payload.decision,
            "reviewed_at": now,
        }
        question_fields = {
            "review_status": payload.decision,
            "latest_review_id": review["_id"],
            "updated_at": now,
            "review_assignment": _empty_review_assignment(
                now,
                f"review_{payload.decision.lower()}",
            ),
        }
        if payload.decision == "APPROVED":
            question_fields["approved_version_id"] = version["_id"]
        elif question.get("approved_version_id") == version["_id"]:
            question_fields["approved_version_id"] = None
        audit = {
            "schema_version": SCHEMA_VERSION,
            "actor": {
                "type": "USER",
                "user_id": current_user.id,
                "model_id": None,
                "service_name": None,
            },
            "entity": {
                "type": "QUESTION",
                "id": question["_id"],
                "version_id": version["_id"],
            },
            "action": f"QUESTION_{payload.decision}",
            "changes": [
                {
                    "path": "review_status",
                    "old_value": question["review_status"],
                    "new_value": payload.decision,
                }
            ],
            "before_hash": version["content_hash"],
            "after_hash": version["content_hash"],
            "metadata": {
                "review_id": review["_id"],
                "correlation_id": str(review["_id"]),
                "review_assignment": json_safe(question.get("review_assignment") or {}),
                "review_form": review_form,
            },
            "created_at": now,
        }
        with mongo_transaction() as session:
            self.db.question_reviews.insert_one(review, session=session)
            result = self.db.questions.update_one(
                {
                    "_id": question["_id"],
                    "current_version_id": version["_id"],
                    "lifecycle_status": "ACTIVE",
                    "latest_review_id": question.get("latest_review_id"),
                },
                {"$set": question_fields},
                session=session,
            )
            if not result.matched_count:
                raise RuntimeError("VERSION_CONFLICT")
            self.db.audit_logs.insert_one(audit, session=session)
        return json_safe(review)

    @staticmethod
    def _question_type(version: dict) -> str:
        classification = version.get("classification") or {}
        return str(classification.get("assessment_type") or "").lower()

    @staticmethod
    def _option_text(options, key: str) -> str:
        if isinstance(options, dict):
            return str(options.get(key) or options.get(str(key)) or key)
        return str(key)

    @staticmethod
    def _answer_keys(correct_answer: str) -> list[str]:
        return [
            item.strip().upper()
            for item in str(correct_answer or "").split(",")
            if item.strip()
        ]

    @staticmethod
    def _gift_escape(value) -> str:
        text = str(value or "")
        for source, replacement in (
            ("\\", "\\\\"),
            ("~", "\\~"),
            ("=", "\\="),
            ("#", "\\#"),
            ("{", "\\{"),
            ("}", "\\}"),
            (":", "\\:"),
        ):
            text = text.replace(source, replacement)
        return text

    @staticmethod
    def _xml_text(value) -> str:
        return escape(str(value or ""), quote=False)

    @classmethod
    def _moodle_gift(cls, question: dict, version: dict) -> str:
        question_data = version.get("question_data") or {}
        options = question_data.get("options")
        correct_answer = question_data.get("correct_answer")
        explanation = question_data.get("explanation")
        qtype = cls._question_type(version)
        code = cls._gift_escape(question.get("question_code"))
        content = cls._gift_escape(version.get("content"))
        feedback = f" # {cls._gift_escape(explanation)}" if explanation else ""

        if qtype == "dung_sai":
            value = "TRUE" if str(correct_answer).strip().upper() in {"A", "TRUE", "ĐÚNG", "DUNG"} else "FALSE"
            return f"::{code}:: {content} {{{value}{feedback}}}\n"

        if qtype == "dien_khuyet":
            answer = cls._gift_escape(correct_answer)
            if "_____" in content:
                content = content.replace("_____", f"{{={answer}{feedback}}}", 1)
                return f"::{code}:: {content}\n"
            return f"::{code}:: {content} {{={answer}{feedback}}}\n"

        if qtype == "ghep_cot" and isinstance(options, dict):
            pairs = re.findall(r"([A-Za-z0-9]+)\s*-\s*([A-Za-z0-9]+)", str(correct_answer or ""))
            answers = [
                f"={cls._gift_escape(cls._option_text(options, left))} -> {cls._gift_escape(cls._option_text(options, right))}"
                for left, right in pairs
            ]
            if answers:
                return f"::{code}:: {content} {{{' '.join(answers)}{feedback}}}\n"

        if isinstance(options, dict):
            correct_keys = set(cls._answer_keys(correct_answer))
            multiple = qtype == "nhieu_lua_chon" and len(correct_keys) > 1
            correct_fraction = round(100 / len(correct_keys)) if multiple else 100
            wrong_fraction = -100 if multiple else None
            answers = []
            for key, value in options.items():
                key_upper = str(key).strip().upper()
                text = cls._gift_escape(value)
                if key_upper in correct_keys:
                    prefix = f"~%{correct_fraction}%" if multiple else "="
                elif multiple:
                    prefix = f"~%{wrong_fraction}%"
                else:
                    prefix = "~"
                answers.append(f"{prefix}{text}")
            return f"::{code}:: {content} {{{' '.join(answers)}{feedback}}}\n"

        return f"::{code}:: {content} {{={cls._gift_escape(correct_answer)}{feedback}}}\n"

    @classmethod
    def _moodle_xml_question(cls, question: dict, version: dict) -> str:
        question_data = version.get("question_data") or {}
        options = question_data.get("options")
        correct_answer = question_data.get("correct_answer")
        explanation = cls._xml_text(question_data.get("explanation"))
        qtype = cls._question_type(version)
        code = cls._xml_text(question.get("question_code"))
        content = cls._xml_text(version.get("content"))

        def answer_node(text, fraction):
            return (
                f'    <answer fraction="{fraction}">\n'
                f"      <text>{cls._xml_text(text)}</text>\n"
                f"      <feedback><text>{explanation}</text></feedback>\n"
                f"    </answer>"
            )

        if qtype == "dung_sai":
            is_true = str(correct_answer).strip().upper() in {"A", "TRUE", "ĐÚNG", "DUNG"}
            return f"""  <question type="truefalse">
    <name><text>{code}</text></name>
    <questiontext format="html"><text>{content}</text></questiontext>
{answer_node("true", 100 if is_true else 0)}
{answer_node("false", 0 if is_true else 100)}
  </question>"""

        if qtype == "dien_khuyet":
            return f"""  <question type="shortanswer">
    <name><text>{code}</text></name>
    <questiontext format="html"><text>{content}</text></questiontext>
    <usecase>0</usecase>
{answer_node(correct_answer, 100)}
  </question>"""

        if qtype == "ghep_cot" and isinstance(options, dict):
            pairs = re.findall(r"([A-Za-z0-9]+)\s*-\s*([A-Za-z0-9]+)", str(correct_answer or ""))
            subquestions = "\n".join(
                f"""    <subquestion format="html">
      <text>{cls._xml_text(cls._option_text(options, left))}</text>
      <answer><text>{cls._xml_text(cls._option_text(options, right))}</text></answer>
    </subquestion>"""
                for left, right in pairs
            )
            if subquestions:
                return f"""  <question type="matching">
    <name><text>{code}</text></name>
    <questiontext format="html"><text>{content}</text></questiontext>
{subquestions}
  </question>"""

        if isinstance(options, dict):
            correct_keys = set(cls._answer_keys(correct_answer))
            multiple = qtype == "nhieu_lua_chon" and len(correct_keys) > 1
            correct_fraction = round(100 / len(correct_keys), 4) if multiple else 100
            answers = "\n".join(
                answer_node(value, correct_fraction if str(key).strip().upper() in correct_keys else 0)
                for key, value in options.items()
            )
            single = "false" if multiple else "true"
            return f"""  <question type="multichoice">
    <name><text>{code}</text></name>
    <questiontext format="html"><text>{content}</text></questiontext>
    <single>{single}</single>
    <shuffleanswers>true</shuffleanswers>
{answers}
  </question>"""

        return f"""  <question type="shortanswer">
    <name><text>{code}</text></name>
    <questiontext format="html"><text>{content}</text></questiontext>
    <usecase>0</usecase>
{answer_node(correct_answer, 100)}
  </question>"""

    @classmethod
    def _moodle_xml(cls, question: dict, version: dict) -> str:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<quiz>
{cls._moodle_xml_question(question, version)}
</quiz>
"""

    @classmethod
    def _moodle_exports(cls, question: dict, version: dict, export_format: str = "BOTH") -> dict:
        export_format = (export_format or "BOTH").upper()
        exports = {}
        if export_format in {"GIFT", "BOTH"}:
            exports["gift"] = cls._moodle_gift(question, version)
        if export_format in {"XML", "BOTH"}:
            exports["xml"] = cls._moodle_xml(question, version)
        return exports

    def export_moodle(
        self,
        question_id: str,
        export_format: str = "gift",
        current_user: CurrentUser | None = None,
    ) -> dict:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        if question["review_status"] != "APPROVED" or question.get("approved_version_id") != version["_id"]:
            raise ValueError("Chỉ câu hỏi đã được duyệt ở phiên bản hiện tại mới được export Moodle")
        normalized = export_format.lower()
        if normalized not in {"gift", "xml"}:
            raise ValueError("Định dạng export Moodle phải là gift hoặc xml")
        exports = self._moodle_exports(question, version, normalized.upper())
        content = exports[normalized]
        return {
            "filename": f"{question['question_code']}.{normalized}",
            "content": content,
            "media_type": "application/xml" if normalized == "xml" else "text/plain",
        }

    def publish_to_moodle(self, question_id: str, payload: MoodlePublicationRequest, user_id) -> dict:
        if not payload.mock:
            raise ValueError("Tích hợp Moodle thật chưa được cấu hình; hãy dùng export GIFT/XML")
        if settings.app_env == "production" and not settings.demo_mode:
            raise ValueError("Mô phỏng Moodle bị tắt trong production; hãy dùng export GIFT/XML")
        question, version = self._pair(question_id)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        if question["review_status"] != "APPROVED" or question.get("approved_version_id") != version["_id"]:
            raise ValueError("Chỉ câu hỏi đã được duyệt ở phiên bản hiện tại mới được xuất Moodle")

        target_service = MoodleTargetService(self.db)
        target_config = target_service.find_target(payload.target_id or payload.moodle_site_id)
        if payload.target_id and not target_config:
            raise LookupError("Không tìm thấy Moodle target")
        if target_config and not target_config.get("is_active", True):
            raise ValueError("Moodle target đang bị khóa")

        moodle_site_id = (target_config or {}).get("site_key") or payload.moodle_site_id
        course_id = payload.course_id
        category_id = payload.category_id
        if target_config:
            if payload.course_id == "ctdl-demo":
                course_id = target_config.get("default_course_id") or course_id
            if payload.category_id == "qbank-demo":
                category_id = target_config.get("default_category_id") or category_id
        target = {
            "target_id": target_config.get("_id") if target_config else None,
            "moodle_site_id": moodle_site_id,
            "site_name": (target_config or {}).get("site_name"),
            "mode": (target_config or {}).get("mode", "MOCK" if payload.mock else "REST_API"),
            "course_id": course_id,
            "category_id": category_id,
        }
        published_content_hash = version["content_hash"]
        idempotency_material = "|".join(
            [
                moodle_site_id,
                course_id,
                category_id,
                str(version["_id"]),
                published_content_hash,
            ]
        )
        idempotency_key = hashlib.sha256(idempotency_material.encode("utf-8")).hexdigest()
        now = utc_now()
        exports = self._moodle_exports(question, version, payload.export_format)
        publication = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "question_id": question["_id"],
            "question_version_id": version["_id"],
            "question_version": version["version"],
            "publisher_user_id": user_id,
            "target": target,
            "published_content_hash": published_content_hash,
            "idempotency_key": idempotency_key,
            "status": "PUBLISHED",
            "attempt_no": 1,
            "moodle_question_ref_id": f"mock-{moodle_site_id}-{str(version['_id'])}",
            "request_payload": {
                "question_code": question["question_code"],
                "content": version["content"],
                "question_data": version.get("question_data") or {},
                "classification": version.get("classification") or {},
                "export_format": payload.export_format,
                "exports": exports,
                "mock": payload.mock,
                "target": json_safe(target),
            },
            "response_payload": {
                "mock": payload.mock,
                "message": "Simulated Moodle publication recorded locally with export payload",
                "export_formats": list(exports.keys()),
            },
            "error": None,
            "created_at": now,
            "updated_at": now,
            "published_at": now,
        }
        with mongo_transaction() as session:
            self.db.moodle_publications.update_one(
                {"idempotency_key": idempotency_key},
                {"$setOnInsert": publication},
                upsert=True,
                session=session,
            )
            saved = self.db.moodle_publications.find_one(
                {"idempotency_key": idempotency_key},
                session=session,
            )
            self.db.questions.update_one(
                {
                    "_id": question["_id"],
                    "current_version_id": version["_id"],
                    "review_status": "APPROVED",
                },
                {
                    "$set": {
                        "publication_status": "PUBLISHED",
                        "updated_at": now,
                    }
                },
                session=session,
            )
        return json_safe(saved or publication)

    def history(
        self,
        question_id: str,
        kind: str,
        current_user: CurrentUser | None = None,
    ) -> list[dict]:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        if kind == "evaluations":
            cursor = self.db.question_evaluations.find(
                {"question_id": question["_id"]}
            ).sort("created_at", -1)
        elif kind == "publications":
            cursor = self.db.moodle_publications.find(
                {"question_id": question["_id"]}
            ).sort("created_at", -1)
        else:
            cursor = self.db.question_reviews.find(
                {"question_id": question["_id"]}
            ).sort("reviewed_at", -1)
        return [json_safe(item) for item in cursor]


def get_workflow_service() -> QuestionWorkflowService:
    return QuestionWorkflowService(get_database())


async def process_evaluation_job_background(job_id: str) -> None:
    async with evaluation_semaphore:
        await get_workflow_service().process_evaluation_job(job_id)
