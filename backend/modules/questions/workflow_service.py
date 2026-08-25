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
from core.dependencies import CurrentUser, has_permission
from modules.admin.moodle_service import MoodleTargetService
from modules.generation.llm.factory import get_llm_service
from modules.generation.prompt_builder import PromptBuilder
from modules.notifications.service import (
    NotificationService,
    safe_notify_review_assigned,
    safe_notify_review_decision,
)
from modules.questions.repository import MongoQuestionRepository, json_safe, object_id, serialize_question, utc_now
from modules.questions.workflow_schemas import (
    AutoEvaluationRequest,
    EvaluationCreateRequest,
    EvaluationScores,
    MoodlePublicationRequest,
    QuestionCommentCreateRequest,
    ReviewAssignmentRequest,
    ReviewCreateRequest,
    SecondaryReviewRequest,
)

DEFAULT_WEIGHTS = {
    "faithfulness": 0.35,
    "contextual_relevancy": 0.20,
    "answer_relevancy": 0.15,
    "bloom_alignment": 0.15,
    "clo_alignment": 0.15,
}
DEFAULT_THRESHOLDS = {"yellow_min": 0.50, "green_min": 0.75, "pass_min": 0.65}
EVALUATION_PROMPT_KEY = "evaluation:question_quality"
EVALUATION_PROMPT_PATH = "evaluation/question_quality.txt"
EVALUATION_SCORING_PROMPT_KEY = "evaluation:scoring_policy"
EVALUATION_SCORING_PROMPT_PATH = "evaluation/scoring_policy.txt"
EVALUATION_OUTPUT_PROMPT_KEY = "evaluation:output_contract"
EVALUATION_OUTPUT_PROMPT_PATH = "evaluation/output_contract.txt"
DIFFICULTY_RULE_PROMPT_KEY = "quy_dinh_do_kho"
DIFFICULTY_RULE_PROMPT_PATH = "quy_dinh_do_kho.txt"
EVALUATION_TYPE_PROMPT_PREFIX = "evaluation:question_type"
EVALUATION_TYPE_PROMPT_DIR = "evaluation/question_type"
DEFAULT_EVALUATOR_MODEL_CODE = settings.evaluation_model_provider
EVALUATION_ACTIVE_STATUSES = {"QUEUED", "PROCESSING"}
EVALUATION_RETRYABLE_STATUSES = {"NOT_STARTED", "FAILED", "ERROR", "STALE"}
EVALUATION_SOURCE_LIMIT = 3
MOODLE_MOCK_STATUS_DETAIL = "SIMULATED_LOCAL_RECORD"
MOODLE_MOCK_MESSAGE = (
    "Mô phỏng Moodle: hệ thống chỉ ghi nhận publication cục bộ kèm payload "
    "export GIFT/XML, chưa gửi dữ liệu sang Moodle thật."
)
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
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
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

    @staticmethod
    def _can_review_all(current_user: CurrentUser) -> bool:
        return current_user.role in {"Admin", "Reviewer"} or has_permission(current_user, "reviews.manage")

    @staticmethod
    def _can_manage_all(current_user: CurrentUser) -> bool:
        return current_user.role == "Admin" or has_permission(current_user, "questions.manage_all")

    @staticmethod
    def _is_shared_question(question: dict, current_user: CurrentUser) -> bool:
        shared_with = set(question.get("shared_with_user_ids") or [])
        return current_user.id in shared_with or question.get("shared_scope") == "SUBJECT"

    def _ensure_read_access(
        self,
        question: dict,
        version: dict,
        current_user: CurrentUser | None,
    ) -> None:
        if not current_user or self._can_manage_all(current_user) or self._can_review_all(current_user):
            return
        if not self._owns_question(question, version, current_user.id) and not self._is_shared_question(question, current_user):
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

    @staticmethod
    def _normalized_question_type(question_type: str | None) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(question_type or "").strip().lower()).strip("_")
        return normalized or "general"

    def _evaluation_prompt_template(self, question_type: str | None) -> tuple[str, list[dict]]:
        normalized_type = self._normalized_question_type(question_type)
        specs = [
            (EVALUATION_PROMPT_KEY, EVALUATION_PROMPT_PATH),
            (EVALUATION_SCORING_PROMPT_KEY, EVALUATION_SCORING_PROMPT_PATH),
            (DIFFICULTY_RULE_PROMPT_KEY, DIFFICULTY_RULE_PROMPT_PATH),
            (
                f"{EVALUATION_TYPE_PROMPT_PREFIX}:{normalized_type}",
                f"{EVALUATION_TYPE_PROMPT_DIR}/{normalized_type}.txt",
            ),
            (EVALUATION_OUTPUT_PROMPT_KEY, EVALUATION_OUTPUT_PROMPT_PATH),
        ]
        parts = []
        loaded = []
        for key, path in specs:
            try:
                body = PromptBuilder._load_template(key, path)
            except FileNotFoundError:
                if key != f"{EVALUATION_TYPE_PROMPT_PREFIX}:{normalized_type}":
                    raise
                fallback_key = f"{EVALUATION_TYPE_PROMPT_PREFIX}:general"
                fallback_path = f"{EVALUATION_TYPE_PROMPT_DIR}/general.txt"
                body = PromptBuilder._load_template(fallback_key, fallback_path)
                key, path = fallback_key, fallback_path
            parts.append(body)
            loaded.append(
                {
                    "template_key": key,
                    "template_path": path,
                    "template_hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                }
            )
        return "\n\n".join(parts), loaded

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
            "current_difficulty": classification.get("difficulty"),
            "clos": clos,
            "source_chunks": source_chunks,
        }
        policy_payload = {
            "name": policy.get("policy_name") or policy.get("name"),
            "version": policy.get("version"),
            "weights": policy.get("weights") or DEFAULT_WEIGHTS,
            "thresholds": policy.get("thresholds") or DEFAULT_THRESHOLDS,
        }
        template, prompt_parts = self._evaluation_prompt_template(payload["question_type"])
        prompt = template.format(
            evaluation_policy=json.dumps(policy_payload, ensure_ascii=False, default=str),
            question_payload=json.dumps(payload, ensure_ascii=False, default=str),
        )
        prompt_snapshot = {
            "template_key": EVALUATION_PROMPT_KEY,
            "template_path": EVALUATION_PROMPT_PATH,
            "template_hash": hashlib.sha256(template.encode("utf-8")).hexdigest(),
            "template_parts": prompt_parts,
            "question_type_prompt": self._normalized_question_type(payload["question_type"]),
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
        assessed = str(evidence.get("assessed_difficulty") or "").strip().lower().replace("-", "_")
        assessed = assessed.replace(" ", "_")
        evidence["assessed_difficulty"] = assessed if assessed in {"de", "trung_binh", "kho"} else None
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
        if payload.reviewer_user_id:
            safe_notify_review_assigned(
                database=self.db,
                question=updated,
                version=version,
                reviewer_user_id=assignment["reviewer_user_id"],
                actor_user_id=current_user.id,
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
        secondary = question.get("secondary_review") or {}
        awaiting_secondary = (
            payload.decision == "APPROVED"
            and secondary.get("status") == "AWAITING_SECONDARY"
        )
        if awaiting_secondary and secondary.get("primary_reviewer_user_id") == current_user.id:
            raise ValueError("Reviewer duyệt lần đầu không được tự duyệt lần hai")
        request_secondary = (
            payload.decision == "APPROVED"
            and payload.secondary_required
            and not awaiting_secondary
        )
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
            "review_stage": "SECONDARY" if awaiting_secondary else "PRIMARY",
            "secondary_required": bool(request_secondary or awaiting_secondary),
            "secondary_reason": payload.secondary_reason or secondary.get("reason") or "",
            "supersedes_review_id": question.get("latest_review_id"),
            "previous_status": question["review_status"],
            "resulting_status": "PENDING" if request_secondary else payload.decision,
            "reviewed_at": now,
        }
        question_fields = {
            "latest_review_id": review["_id"],
            "updated_at": now,
            "review_assignment": _empty_review_assignment(
                now,
                f"review_{payload.decision.lower()}",
            ),
        }
        if request_secondary:
            question_fields["review_status"] = "PENDING"
            question_fields["secondary_review"] = {
                "required": True,
                "status": "AWAITING_SECONDARY",
                "reason": payload.secondary_reason or review_note,
                "primary_review_id": review["_id"],
                "primary_reviewer_user_id": current_user.id,
                "secondary_review_id": None,
                "secondary_reviewer_user_id": None,
                "requested_at": now,
                "completed_at": None,
            }
        else:
            question_fields["review_status"] = payload.decision
        if payload.decision == "APPROVED" and not request_secondary:
            question_fields["approved_version_id"] = version["_id"]
            if awaiting_secondary:
                question_fields["secondary_review"] = {
                    **secondary,
                    "required": True,
                    "status": "COMPLETED",
                    "secondary_review_id": review["_id"],
                    "secondary_reviewer_user_id": current_user.id,
                    "completed_at": now,
                }
        elif question.get("approved_version_id") == version["_id"]:
            question_fields["approved_version_id"] = None
        if payload.decision != "APPROVED":
            question_fields["secondary_review"] = {
                **secondary,
                "status": "CANCELLED" if secondary else "NOT_REQUIRED",
                "completed_at": now if secondary else None,
            }
        audit_action = (
            "QUESTION_SECONDARY_REVIEW_REQUESTED"
            if request_secondary
            else f"QUESTION_{payload.decision}"
        )
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
            "action": audit_action,
            "changes": [
                {
                    "path": "review_status",
                    "old_value": question["review_status"],
                    "new_value": question_fields["review_status"],
                }
            ],
            "before_hash": version["content_hash"],
            "after_hash": version["content_hash"],
            "metadata": {
                "review_id": review["_id"],
                "correlation_id": str(review["_id"]),
                "review_assignment": json_safe(question.get("review_assignment") or {}),
                "review_form": review_form,
                "secondary_review": json_safe(question_fields.get("secondary_review") or secondary or {}),
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
        if not request_secondary:
            safe_notify_review_decision(
                database=self.db,
                question=question,
                version=version,
                review=review,
                actor_user_id=current_user.id,
            )
        return json_safe(review)

    def list_comments(self, question_id: str, current_user: CurrentUser) -> dict:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        comments = list(
            self.db.question_comments.find({"question_id": question["_id"]})
            .sort("created_at", 1)
        )
        return {"items": [json_safe(comment) for comment in comments]}

    def add_comment(
        self,
        question_id: str,
        payload: QuestionCommentCreateRequest,
        current_user: CurrentUser,
    ) -> dict:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        mention_ids = [
            object_id(user_id, "mention_user_id")
            for user_id in dict.fromkeys(payload.mention_user_ids)
        ]
        mentioned_users = list(
            self.db.users.find(
                {"_id": {"$in": mention_ids}, "is_active": True},
                {"_id": 1, "role": 1},
            )
        ) if mention_ids else []
        if len(mentioned_users) != len(mention_ids):
            raise ValueError("Một hoặc nhiều người được mention không hợp lệ")
        now = utc_now()
        comment = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "question_id": question["_id"],
            "question_version_id": version["_id"],
            "question_version": version["version"],
            "author_user_id": current_user.id,
            "author_role": current_user.role,
            "body": payload.body.strip(),
            "mention_user_ids": mention_ids,
            "created_at": now,
            "updated_at": now,
        }
        self.db.question_comments.insert_one(comment)
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
                "action": "QUESTION_COMMENT_ADDED",
                "changes": [],
                "before_hash": version["content_hash"],
                "after_hash": version["content_hash"],
                "metadata": {"comment_id": comment["_id"], "mentions": json_safe(mention_ids)},
                "created_at": now,
            }
        )
        NotificationService(self.db).create_many(
            [
                {
                    "recipient_user_id": user["_id"],
                    "actor_user_id": current_user.id,
                    "type": "QUESTION_MENTION",
                    "title": f"{question.get('question_code', 'Câu hỏi')} có mention mới",
                    "body": comment["body"][:200],
                    "link": (
                        f"/kiem-duyet?questionId={question['_id']}"
                        if user.get("role") in {"Reviewer", "Admin"}
                        else f"/quan-ly?questionId={question['_id']}"
                    ),
                    "entity": {
                        "type": "QUESTION",
                        "id": str(question["_id"]),
                        "version_id": str(version["_id"]),
                        "comment_id": str(comment["_id"]),
                    },
                }
                for user in mentioned_users
                if user["_id"] != current_user.id
            ]
        )
        return json_safe(comment)

    def set_secondary_review(
        self,
        question_id: str,
        payload: SecondaryReviewRequest,
        current_user: CurrentUser,
    ) -> dict:
        question, version = self._pair(question_id)
        if question["review_status"] not in {"PENDING", "APPROVED"}:
            raise ValueError("Chỉ cấu hình duyệt lần hai cho câu đang chờ hoặc đã duyệt")
        reviewer = None
        if payload.reviewer_user_id:
            reviewer = self._find_assignable_reviewer(payload.reviewer_user_id)
        now = utc_now()
        secondary = (
            {
                "required": True,
                "status": "AWAITING_SECONDARY",
                "reason": payload.reason,
                "primary_review_id": question.get("latest_review_id"),
                "primary_reviewer_user_id": None,
                "secondary_review_id": None,
                "secondary_reviewer_user_id": reviewer["_id"] if reviewer else None,
                "requested_at": now,
                "completed_at": None,
            }
            if payload.required
            else {
                "required": False,
                "status": "NOT_REQUIRED",
                "reason": payload.reason,
                "requested_at": now,
                "completed_at": now,
            }
        )
        fields = {"secondary_review": secondary, "updated_at": now}
        if payload.required:
            fields["review_status"] = "PENDING"
            fields["approved_version_id"] = None
            fields["review_assignment"] = (
                {
                    "status": "ASSIGNED",
                    "reviewer_user_id": reviewer["_id"],
                    "assigned_by_user_id": current_user.id,
                    "assigned_at": now,
                    "claimed_at": None,
                    "lock_expires_at": self._lock_expires_at(now),
                    "last_released_at": None,
                    "release_reason": payload.reason or None,
                }
                if reviewer
                else _empty_review_assignment(now, payload.reason or "secondary_review")
            )
        updated = self.db.questions.find_one_and_update(
            {
                "_id": question["_id"],
                "current_version_id": version["_id"],
                "lifecycle_status": "ACTIVE",
            },
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise RuntimeError("VERSION_CONFLICT")
        self._assignment_audit(
            action="QUESTION_SECONDARY_REVIEW_SET",
            question=updated,
            version=version,
            current_user=current_user,
            before=question.get("secondary_review") or {},
            after=secondary,
            metadata={"reason": payload.reason},
        )
        if reviewer:
            safe_notify_review_assigned(
                database=self.db,
                question=updated,
                version=version,
                reviewer_user_id=reviewer["_id"],
                actor_user_id=current_user.id,
            )
        return serialize_question(updated, version)

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

    def publish_to_moodle(
        self,
        question_id: str,
        payload: MoodlePublicationRequest,
        user_id,
        publisher_role: str | None = None,
    ) -> dict:
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
        allowed_roles = (target_config or {}).get("allowed_roles") or ["Admin", "Reviewer"]
        if target_config and publisher_role and publisher_role not in allowed_roles:
            raise PermissionError("Role hiện tại không được phép publish tới Moodle target này")

        moodle_site_id = (target_config or {}).get("site_key") or payload.moodle_site_id
        course_id = payload.course_id
        category_id = payload.category_id
        if target_config:
            if payload.course_id == "ctdl-demo":
                course_id = target_config.get("default_course_id") or course_id
            if payload.category_id == "qbank-demo":
                category_id = target_config.get("default_category_id") or category_id
        configured_mode = (target_config or {}).get("mode", "MOCK" if payload.mock else "REST_API")
        publication_mode = "MOCK" if payload.mock else configured_mode
        target = {
            "target_id": target_config.get("_id") if target_config else None,
            "moodle_site_id": moodle_site_id,
            "site_name": (target_config or {}).get("site_name"),
            "mode": publication_mode,
            "configured_mode": configured_mode,
            "course_id": course_id,
            "category_id": category_id,
            "allowed_roles": allowed_roles,
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
            "publication_mode": publication_mode,
            "external_sync": False,
            "status_detail": MOODLE_MOCK_STATUS_DETAIL,
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
                "publication_mode": publication_mode,
                "external_sync": False,
                "target": json_safe(target),
            },
            "response_payload": {
                "mock": payload.mock,
                "publication_mode": publication_mode,
                "external_sync": False,
                "status_detail": MOODLE_MOCK_STATUS_DETAIL,
                "message": MOODLE_MOCK_MESSAGE,
                "export_formats": list(exports.keys()),
            },
            "error": None,
            "created_at": now,
            "updated_at": now,
            "published_at": now,
        }
        with mongo_transaction() as session:
            existing = self.db.moodle_publications.find_one(
                {"idempotency_key": idempotency_key},
                session=session,
            )
            if existing and existing.get("status") == "FAILED":
                publication["_id"] = existing["_id"]
                publication["created_at"] = existing.get("created_at") or now
                publication["attempt_no"] = int(existing.get("attempt_no") or 1) + 1
                update_fields = {key: value for key, value in publication.items() if key != "_id"}
                self.db.moodle_publications.update_one(
                    {"_id": existing["_id"], "status": "FAILED"},
                    {"$set": update_fields},
                    session=session,
                )
                saved = self.db.moodle_publications.find_one(
                    {"_id": existing["_id"]},
                    session=session,
                )
            elif existing:
                saved = existing
            else:
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
            if (saved or publication).get("status") == "PUBLISHED":
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

    def review_dashboard(self, current_user: CurrentUser) -> dict:
        now = utc_now()
        since_7d = now - timedelta(days=7)
        since_30d = now - timedelta(days=30)
        is_admin = current_user.role == "Admin"
        pending_base = {
            "schema_version": SCHEMA_VERSION,
            "lifecycle_status": "ACTIVE",
            "review_status": "PENDING",
        }

        def pending_count(extra: dict | None = None) -> int:
            if not extra:
                return self.db.questions.count_documents(pending_base)
            return self.db.questions.count_documents({"$and": [pending_base, extra]})

        workload = {
            "pending": pending_count(),
            "unassigned": pending_count(
                {
                    "$or": [
                        {"review_assignment.status": {"$exists": False}},
                        {"review_assignment.status": "UNASSIGNED"},
                    ]
                }
            ),
            "assigned": pending_count({"review_assignment.status": "ASSIGNED"}),
            "in_review": pending_count({"review_assignment.status": "IN_REVIEW"}),
            "lock_expired": pending_count(
                {
                    "review_assignment.status": "IN_REVIEW",
                    "review_assignment.lock_expires_at": {"$lte": now},
                }
            ),
            "mine": pending_count(
                {
                    "review_assignment.status": {"$in": ["ASSIGNED", "IN_REVIEW"]},
                    "review_assignment.reviewer_user_id": current_user.id,
                }
            ),
        }

        review_match: dict = {"reviewed_at": {"$gte": since_30d}}
        if not is_admin:
            review_match["reviewer_user_id"] = current_user.id
        reviews = list(
            self.db.question_reviews.find(review_match).sort("reviewed_at", -1).limit(500)
        )
        decision_counts = {"APPROVED": 0, "NEEDS_REVISION": 0, "REJECTED": 0}
        override_count = 0
        revision_issues = 0
        reviews_last_7d = 0
        for review in reviews:
            decision = review.get("decision")
            if decision in decision_counts:
                decision_counts[decision] += 1
            if (review.get("override") or {}).get("applied"):
                override_count += 1
            revision_issues += len(review.get("revision_issues") or [])
            reviewed_at = _as_aware_utc(review.get("reviewed_at"))
            if reviewed_at and reviewed_at >= since_7d:
                reviews_last_7d += 1

        version_ids = [
            review.get("question_version_id")
            for review in reviews
            if review.get("question_version_id")
        ]
        evaluation_map: dict[ObjectId, dict] = {}
        if version_ids and hasattr(self.db, "question_evaluations"):
            evaluations = list(
                self.db.question_evaluations.find(
                    {"question_version_id": {"$in": version_ids}},
                ).sort("created_at", -1)
            )
            for evaluation in evaluations:
                version_id = evaluation.get("question_version_id")
                if version_id not in evaluation_map:
                    evaluation_map[version_id] = evaluation
        calibration_sample = 0
        calibration_agreements = 0
        calibration_disagreements = 0
        ai_failed_but_approved = 0
        ai_passed_but_not_approved = 0
        for review in reviews:
            evaluation = evaluation_map.get(review.get("question_version_id"))
            if not evaluation:
                continue
            calibration_sample += 1
            ai_positive = bool(evaluation.get("passed"))
            human_positive = review.get("decision") == "APPROVED"
            if ai_positive == human_positive:
                calibration_agreements += 1
            else:
                calibration_disagreements += 1
                if human_positive:
                    ai_failed_but_approved += 1
                else:
                    ai_passed_but_not_approved += 1

        audit_match: dict = {
            "action": {"$in": ["QUESTION_APPROVED", "QUESTION_REJECTED", "QUESTION_NEEDS_REVISION"]},
            "created_at": {"$gte": since_30d},
        }
        if not is_admin:
            audit_match["actor.user_id"] = current_user.id
        durations: list[float] = []
        for audit in self.db.audit_logs.find(audit_match, {"metadata.review_assignment": 1, "created_at": 1}):
            assignment = ((audit.get("metadata") or {}).get("review_assignment") or {})
            start = _as_aware_utc(assignment.get("claimed_at") or assignment.get("assigned_at"))
            end = _as_aware_utc(audit.get("created_at"))
            if start and end and end >= start:
                durations.append((end - start).total_seconds() / 3600)
        average_review_hours = (
            round(sum(durations) / len(durations), 2)
            if durations
            else None
        )

        versions = list(
            self.db.question_versions.find(
                {"_id": {"$in": version_ids}},
                {"classification.subject": 1},
            )
        ) if version_ids else []
        subject_counts: dict[str, int] = {}
        for version in versions:
            subject = ((version.get("classification") or {}).get("subject") or {})
            subject_id = subject.get("id") if isinstance(subject, dict) else None
            key = str(subject_id) if subject_id else "unknown"
            subject_counts[key] = subject_counts.get(key, 0) + 1
        subject_oids = [
            ObjectId(subject_id)
            for subject_id in subject_counts
            if subject_id != "unknown" and ObjectId.is_valid(subject_id)
        ]
        subject_records = list(
            self.db.subjects.find(
                {"_id": {"$in": subject_oids}},
                {"subject_code": 1, "subject_name": 1},
            )
        ) if subject_oids else []
        subject_labels = {
            str(record["_id"]): (
                record.get("subject_code")
                or record.get("subject_name")
                or str(record["_id"])
            )
            for record in subject_records
        }
        subjects = [
            {
                "subject_id": None if subject_id == "unknown" else subject_id,
                "label": subject_labels.get(subject_id, "Chưa gắn môn"),
                "reviewed": count,
            }
            for subject_id, count in sorted(subject_counts.items(), key=lambda item: item[1], reverse=True)[:6]
        ]

        total_reviews = len(reviews)
        approved = decision_counts["APPROVED"]
        performance = {
            "reviews_7d": reviews_last_7d,
            "reviews_30d": total_reviews,
            "approval_rate": round(approved / total_reviews, 3) if total_reviews else None,
            "override_count": override_count,
            "revision_issues": revision_issues,
            "average_review_hours": average_review_hours,
            "duration_sample_size": len(durations),
        }
        calibration = {
            "sample_size": calibration_sample,
            "agreement_rate": (
                round(calibration_agreements / calibration_sample, 3)
                if calibration_sample
                else None
            ),
            "agreements": calibration_agreements,
            "disagreements": calibration_disagreements,
            "ai_failed_but_approved": ai_failed_but_approved,
            "ai_passed_but_not_approved": ai_passed_but_not_approved,
        }
        return json_safe(
            {
                "workload": workload,
                "performance": performance,
                "calibration": calibration,
                "decisions": decision_counts,
                "subjects": subjects,
                "generated_at": now,
                "scope": "all_reviewers" if is_admin else "current_reviewer",
            }
        )


def get_workflow_service() -> QuestionWorkflowService:
    return QuestionWorkflowService(get_database())


async def process_evaluation_job_background(job_id: str) -> None:
    async with evaluation_semaphore:
        await get_workflow_service().process_evaluation_job(job_id)
