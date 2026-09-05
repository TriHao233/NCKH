import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from html import escape

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.bootstrap import SCHEMA_VERSION
from core.access_policy import (
    active_subject_ids,
    has_subject_access,
    is_explicitly_shared,
    is_subject_shared_with_member,
    subject_id_from_record,
)
from core.config import settings
from core.database import get_database, mongo_transaction
from core.dependencies import CurrentUser, has_permission
from modules.admin.moodle_service import MoodleTargetService
from modules.generation.llm.factory import get_llm_execution_snapshot, get_llm_service
from modules.generation.llm.model_registry import EVALUATION_CAPABILITY, resolve_model_snapshot
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
    QuestionCommentUpdateRequest,
    ReviewAssignmentRequest,
    ReviewCreateRequest,
    ReviewDraftUpsertRequest,
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
OPTION_CHECK_VERDICTS = {"SUPPORTED", "CONTRADICTED", "NOT_IN_SOURCE", "AMBIGUOUS"}
SINGLE_ANSWER_TYPES = {"TRAC_NGHIEM", "DUNG_SAI"}
MULTIPLE_ANSWER_TYPES = {"NHIEU_LUA_CHON"}
NON_OPTION_ANSWER_TYPES = {"DIEN_KHUYET", "GHEP_COT", "SAP_XEP", "TINH_HUONG"}
NEGATIVE_QUESTION_PATTERN = re.compile(
    r"\b(không\s+(?:phải|đúng|chính\s+xác|phù\s+hợp)|chưa\s+đúng|ngoại\s+trừ|sai)\b"
    r"|\b(?:nào|đâu)\b[^?.]{0,80}\bkhông\b",
    flags=re.IGNORECASE,
)
MOODLE_MOCK_STATUS_DETAIL = "SIMULATED_LOCAL_RECORD"
MOODLE_MOCK_MESSAGE = (
    "Mô phỏng Moodle: hệ thống chỉ ghi nhận publication cục bộ kèm payload "
    "export GIFT/XML, chưa gửi dữ liệu sang Moodle thật."
)
EVALUATION_SOURCE_EXCERPT_CHARS = 700
EVALUATION_RETRY_INSTRUCTION = """
LẦN THỬ LẠI: Phản hồi trước không phải JSON hoàn chỉnh.
- Chỉ trả về đúng một object JSON và phải đóng đủ mọi dấu ngoặc.
- summary, reasoning và answer_diagnostics: tối đa 120 ký tự mỗi trường.
- supporting_excerpt của từng option: tối đa 18 từ, không lặp lại đoạn nguồn dài.
- Không thêm trường ngoài schema OUTPUT.
""".strip()
evaluation_semaphore = asyncio.Semaphore(1)
logger = logging.getLogger(__name__)

REVIEW_CRITERION_KEYS = tuple(DEFAULT_WEIGHTS)
LEGACY_REVIEW_CRITERION_MAP = {
    "source_alignment": "faithfulness",
    "answer_correctness": "answer_relevancy",
    "bloom_clo_alignment": "bloom_alignment",
}


def _limit_evaluation_output(snapshot: dict | None) -> dict | None:
    if not snapshot or str(snapshot.get("runtime") or "").upper() != "OLLAMA":
        return snapshot
    model_code = str(snapshot.get("model_code") or "").strip().lower()
    if model_code != "qwen":
        return snapshot
    parameters = dict(snapshot.get("parameters") or {})
    configured = int(parameters.get("num_predict") or settings.evaluation_num_predict)
    parameters["num_predict"] = min(configured, settings.evaluation_num_predict)
    return {**snapshot, "parameters": parameters}


def _prepare_evaluation_attempt(
    prompt: str,
    prompt_snapshot: dict,
    model_snapshot: dict | None,
    attempt: int,
) -> tuple[str, dict, dict | None]:
    if attempt <= 1:
        return prompt, prompt_snapshot, model_snapshot

    retry_prompt = f"{prompt}\n\n{EVALUATION_RETRY_INSTRUCTION}"
    retry_prompt_snapshot = {
        **prompt_snapshot,
        "rendered_prompt_hash": hashlib.sha256(retry_prompt.encode("utf-8")).hexdigest(),
        "rendered_prompt_chars": len(retry_prompt),
        "retry_attempt": attempt,
        "retry_instruction_applied": True,
    }
    if not model_snapshot or str(model_snapshot.get("runtime") or "").upper() != "OLLAMA":
        return retry_prompt, retry_prompt_snapshot, model_snapshot

    effective_model_snapshot = {**model_snapshot}
    parameters = dict(model_snapshot.get("parameters") or {})
    configured = int(parameters.get("num_predict") or 0)
    parameters["num_predict"] = max(configured, settings.evaluation_num_predict)
    effective_model_snapshot["parameters"] = parameters
    return retry_prompt, retry_prompt_snapshot, effective_model_snapshot


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
        return current_user.role == "Reviewer" or has_permission(current_user, "questions.review")

    @staticmethod
    def _can_manage_all(current_user: CurrentUser) -> bool:
        return current_user.role == "Admin" or has_permission(current_user, "questions.manage_all")

    def _is_shared_question(self, question: dict, version: dict, current_user: CurrentUser) -> bool:
        return is_explicitly_shared(question, current_user.id) or is_subject_shared_with_member(
            self.db, question, current_user.id, version=version
        )

    def _has_review_scope(self, question: dict, version: dict, current_user: CurrentUser) -> bool:
        if not self._can_review_all(current_user):
            return False
        subject_id = subject_id_from_record(question, version)
        # Legacy unclassified records remain reviewable so they can be repaired.
        if subject_id is None:
            return True
        # Lightweight unit-test adapters and legacy service embeddings may not
        # expose the new collection. Real bootstrapped databases always do.
        if getattr(self.db, "subject_memberships", None) is None:
            return True
        return has_subject_access(self.db, current_user.id, subject_id)

    def _ensure_read_access(
        self,
        question: dict,
        version: dict,
        current_user: CurrentUser | None,
    ) -> None:
        if not current_user or self._can_manage_all(current_user) or self._has_review_scope(
            question, version, current_user
        ):
            return
        if not self._owns_question(question, version, current_user.id) and not self._is_shared_question(
            question, version, current_user
        ):
            raise PermissionError("Bạn không có quyền truy cập câu hỏi này")

    def _policy(self) -> dict:
        if self.db is None:
            return {
                "_id": None,
                "policy_name": "Default fallback",
                "version": 1,
                "weights": DEFAULT_WEIGHTS,
                "thresholds": DEFAULT_THRESHOLDS,
            }
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
    def _is_negative_selection_question(question_type: str, question: str) -> bool:
        if question_type == "DUNG_SAI":
            return False
        return bool(NEGATIVE_QUESTION_PATTERN.search(question or ""))

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
        model_source_context = QuestionWorkflowService._compact_text(
            (version.get("question_data") or {}).get("model_source_context") or "",
            1400,
        )
        source_parts = [
            f"[{source['label']}] {source['excerpt']}"
            for source in QuestionWorkflowService._compact_sources(version)
            if source.get("excerpt")
        ]
        if model_source_context:
            source_parts.insert(0, f"[MODEL_CONTEXT] {model_source_context}")
        return "\n\n".join(source_parts)

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
            # This is the verbatim evidence selected by the generation model
            # and persisted with the question version.  Keep the immutable
            # chunk snapshots below as the authoritative source provenance.
            "generation_source_context": self._compact_text(
                question_data.get("model_source_context") or "",
                1400,
            ),
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

        def score_value(key: str, *aliases: str) -> float:
            for candidate in (key, *aliases):
                if candidate in raw_scores:
                    return cls._clamp(float(raw_scores[candidate]))
            raise ValueError(f"AI evaluation thiếu điểm bắt buộc: {key}")

        scores = EvaluationScores(
            faithfulness=score_value("faithfulness"),
            contextual_relevancy=score_value("contextual_relevancy"),
            # Local models occasionally misspell this field. Accept only the
            # observed typo; all other missing scores remain a retryable error.
            answer_relevancy=score_value("answer_relevancy", "answer_relevality"),
            bloom_alignment=score_value("bloom_alignment"),
            clo_alignment=score_value("clo_alignment"),
        )
        feedback = dict(parsed.get("feedback")) if isinstance(parsed.get("feedback"), dict) else {}
        action = str(feedback.get("action") or parsed.get("action") or "").strip().upper()
        severity = str(feedback.get("severity") or parsed.get("severity") or "").strip().upper()
        if action not in {"APPROVE", "NEEDS_REVISION", "REJECT"}:
            raise ValueError("AI evaluation thiếu action hợp lệ")
        if severity not in {"LOW", "MEDIUM", "HIGH"}:
            raise ValueError("AI evaluation thiếu severity hợp lệ")
        summary = str(feedback.get("summary") or "").strip()
        if not summary:
            raise ValueError("AI evaluation thiếu summary")
        feedback["action"] = action
        feedback["severity"] = severity
        feedback["summary"] = summary
        missing = feedback.get("missing")
        feedback["missing"] = missing if isinstance(missing, list) else ([missing] if missing else [])
        evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), dict) else {}
        moodle_readiness = str(evidence.get("moodle_readiness") or "").strip().upper()
        if moodle_readiness not in {"READY", "NEEDS_FIX"}:
            raise ValueError("AI evaluation thiếu moodle_readiness hợp lệ")
        if not str(evidence.get("reasoning") or evidence.get("supporting_excerpt") or "").strip():
            raise ValueError("AI evaluation thiếu minh chứng hoặc lý do chấm điểm")
        evidence["moodle_readiness"] = moodle_readiness
        risks = evidence.get("risks")
        evidence["risks"] = risks if isinstance(risks, list) else ([risks] if risks else [])
        assessed = str(evidence.get("assessed_difficulty") or "").strip().lower().replace("-", "_")
        assessed = assessed.replace(" ", "_")
        evidence["assessed_difficulty"] = assessed if assessed in {"de", "trung_binh", "kho"} else None
        polarity = str(evidence.get("question_polarity") or "").strip().upper()
        evidence["question_polarity"] = polarity if polarity in {"POSITIVE", "NEGATIVE"} else None
        option_checks = evidence.get("option_checks")
        normalized_checks = []
        if isinstance(option_checks, list):
            for check in option_checks:
                if not isinstance(check, dict):
                    continue
                normalized_checks.append(
                    {
                        "key": str(check.get("key") or "").strip().upper(),
                        "verdict": str(check.get("verdict") or "").strip().upper(),
                        "source_label": str(check.get("source_label") or "").strip().upper(),
                        "supporting_excerpt": cls._compact_text(
                            check.get("supporting_excerpt") or "",
                            300,
                        ),
                    }
                )
        evidence["option_checks"] = normalized_checks
        return scores, feedback, evidence

    @staticmethod
    def _question_options(version: dict) -> dict[str, str]:
        options = (version.get("question_data") or {}).get("options")
        if isinstance(options, dict):
            return {
                str(key).strip().upper(): str(value or "").strip()
                for key, value in options.items()
                if str(key).strip() and str(value or "").strip()
            }
        if isinstance(options, list):
            return {
                chr(65 + index): str(value or "").strip()
                for index, value in enumerate(options)
                if index < 26 and str(value or "").strip()
            }
        return {}

    @classmethod
    def _declared_answer_keys(cls, version: dict, options: dict[str, str]) -> set[str]:
        raw_answer = (version.get("question_data") or {}).get("correct_answer")
        values = raw_answer if isinstance(raw_answer, list) else re.split(r"[;,|]", str(raw_answer or ""))
        normalized_options = {
            cls._compact_text(value, 500).casefold(): key
            for key, value in options.items()
        }
        answer_keys = set()
        for value in values:
            normalized = str(value or "").strip()
            key = normalized.upper()
            if key in options:
                answer_keys.add(key)
                continue
            option_key = normalized_options.get(cls._compact_text(normalized, 500).casefold())
            if option_key:
                answer_keys.add(option_key)
        return answer_keys

    @classmethod
    def _apply_answer_guardrail(
        cls,
        scores: EvaluationScores,
        feedback: dict,
        evidence: dict,
        version: dict,
    ) -> tuple[EvaluationScores, dict, dict]:
        options = cls._question_options(version)
        question_type = str(
            (version.get("classification") or {}).get("assessment_type") or ""
        ).strip().upper()
        if question_type in NON_OPTION_ANSWER_TYPES:
            return scores, feedback, {
                **evidence,
                "answer_guardrail": {
                    "applied": False,
                    "reason": "QUESTION_TYPE_NOT_OPTION_BASED",
                    "question_type": question_type,
                },
            }
        if len(options) < 2:
            return scores, feedback, {
                **evidence,
                "answer_guardrail": {"applied": False, "reason": "NO_OPTION_SET"},
            }

        question = str(version.get("content") or "")
        # With true/false items the stem is a proposition; words such as "không"
        # belong to that proposition and do not turn the answer format into a
        # negative-selection MCQ.
        negative = cls._is_negative_selection_question(question_type, question)
        declared_keys = cls._declared_answer_keys(version, options)
        checks = evidence.get("option_checks") if isinstance(evidence.get("option_checks"), list) else []
        checks_by_key = {
            str(check.get("key") or "").strip().upper(): check
            for check in checks
            if isinstance(check, dict) and str(check.get("key") or "").strip()
        }
        if question_type == "DUNG_SAI" and len(options) == 2 and len(checks_by_key) == 1:
            normalized_values = {
                key: re.sub(r"\s+", " ", value).strip().casefold()
                for key, value in options.items()
            }
            truth_key = next(
                (key for key, value in normalized_values.items() if value in {"đúng", "dung", "true"}),
                None,
            )
            false_key = next(
                (key for key, value in normalized_values.items() if value in {"sai", "false"}),
                None,
            )
            checked_key, checked = next(iter(checks_by_key.items()))
            if (
                truth_key
                and false_key
                and checked_key in {truth_key, false_key}
                and checked.get("verdict") in {"SUPPORTED", "CONTRADICTED"}
            ):
                inferred_key = false_key if checked_key == truth_key else truth_key
                inferred = {
                    "key": inferred_key,
                    "verdict": (
                        "CONTRADICTED"
                        if checked.get("verdict") == "SUPPORTED"
                        else "SUPPORTED"
                    ),
                    "source_label": checked.get("source_label") or "",
                    "supporting_excerpt": checked.get("supporting_excerpt") or "",
                    "inferred_from_complement": checked_key,
                }
                checks.append(inferred)
                checks_by_key[inferred_key] = inferred
                evidence = {**evidence, "option_checks": checks}
        issues = []
        reported_polarity = str(evidence.get("question_polarity") or "").strip().upper()
        detected_polarity = "NEGATIVE" if negative else "POSITIVE"
        if reported_polarity and reported_polarity != detected_polarity:
            issues.append(
                f"AI nhận diện sai dạng câu: báo {reported_polarity}, thực tế {detected_polarity}"
            )
        missing_keys = [key for key in options if key not in checks_by_key]
        if missing_keys:
            issues.append(f"AI chưa kiểm tra phương án: {', '.join(missing_keys)}")

        invalid_keys = [
            key
            for key, check in checks_by_key.items()
            if key not in options or check.get("verdict") not in OPTION_CHECK_VERDICTS
        ]
        if invalid_keys:
            issues.append(f"option_checks không hợp lệ: {', '.join(sorted(invalid_keys))}")

        supported = {
            key
            for key, check in checks_by_key.items()
            if key in options and check.get("verdict") == "SUPPORTED"
        }
        unsupported = {
            key
            for key, check in checks_by_key.items()
            if key in options and check.get("verdict") in {"CONTRADICTED", "NOT_IN_SOURCE"}
        }
        ambiguous = {
            key
            for key, check in checks_by_key.items()
            if key in options and check.get("verdict") == "AMBIGUOUS"
        }
        if not declared_keys:
            issues.append("Không xác định được đáp án đã khai báo")

        source_context = cls._source_context(version)
        lexical_support = {
            key: round(cls._overlap_score(text, source_context), 4)
            for key, text in options.items()
        }
        answer_mode = (
            "SINGLE"
            if question_type in SINGLE_ANSWER_TYPES
            else "MULTIPLE"
            if question_type in MULTIPLE_ANSWER_TYPES
            else "SINGLE"
            if len(declared_keys) <= 1
            else "MULTIPLE"
        )
        if negative:
            if len(unsupported) != 1:
                issues.append(
                    "Câu phủ định phải có đúng một phương án không được nguồn hỗ trợ"
                )
            elif declared_keys != unsupported:
                issues.append("Đáp án khai báo không khớp phương án phủ định duy nhất")
            if options and all(score >= 0.8 for score in lexical_support.values()):
                issues.append(
                    "Tất cả phương án đều xuất hiện rõ trong nguồn; không được tự động duyệt câu phủ định"
                )
        else:
            if answer_mode == "SINGLE":
                if not declared_keys.issubset(supported):
                    issues.append("Đáp án khai báo không được option_checks xác nhận")
                if len(supported) != 1:
                    issues.append("Câu một đáp án không có đúng một phương án được xác nhận")
            elif declared_keys and supported != declared_keys:
                issues.append("Tập đáp án khai báo không khớp các phương án được xác nhận")

        if ambiguous:
            issues.append(f"Phương án còn mơ hồ: {', '.join(sorted(ambiguous))}")
        compact_sources = cls._compact_sources(version)
        source_by_label = {
            str(source.get("label") or "").upper(): str(source.get("excerpt") or "")
            for source in compact_sources
        }
        for key in supported:
            check = checks_by_key[key]
            excerpt = str(check.get("supporting_excerpt") or "").strip()
            source_label = str(check.get("source_label") or "").strip().upper()
            if not excerpt:
                issues.append(f"Phương án {key} thiếu trích dẫn nguồn")
            if not source_label or source_label not in source_by_label:
                issues.append(f"Phương án {key} không trỏ tới nguồn S hợp lệ")
            elif excerpt and cls._overlap_score(excerpt, source_by_label[source_label]) < 0.5:
                issues.append(f"Trích dẫn của phương án {key} không khớp nguồn {source_label}")

        guardrail = {
            "applied": bool(issues),
            "question_type": question_type or "UNKNOWN",
            "answer_mode": answer_mode,
            "question_polarity": detected_polarity,
            "reported_question_polarity": reported_polarity or None,
            "declared_answer_keys": sorted(declared_keys),
            "supported_option_keys": sorted(supported),
            "unsupported_option_keys": sorted(unsupported),
            "ambiguous_option_keys": sorted(ambiguous),
            "option_source_overlap": lexical_support,
            "issues": list(dict.fromkeys(issues)),
        }
        if not issues:
            return scores, feedback, {**evidence, "answer_guardrail": guardrail}

        guarded_scores = EvaluationScores(
            **{
                **scores.model_dump(),
                "faithfulness": min(scores.faithfulness, 0.35),
                "answer_relevancy": min(scores.answer_relevancy, 0.30),
            }
        )
        guarded_feedback = {
            **feedback,
            "action": "NEEDS_REVISION",
            "severity": "HIGH",
            "summary": "Guardrail đáp án chặn tự động duyệt: " + guardrail["issues"][0],
            "missing": list(
                dict.fromkeys([*(feedback.get("missing") or []), *guardrail["issues"]])
            ),
        }
        guarded_evidence = {
            **evidence,
            "moodle_readiness": "NEEDS_FIX",
            "risks": list(
                dict.fromkeys(
                    [
                        *(evidence.get("risks") or []),
                        "Đáp án chưa vượt qua kiểm chứng từng phương án",
                    ]
                )
            ),
            "answer_guardrail": guardrail,
        }
        return guarded_scores, guarded_feedback, guarded_evidence

    @classmethod
    def _apply_metadata_guardrail(
        cls,
        scores: EvaluationScores,
        feedback: dict,
        evidence: dict,
        version: dict,
    ) -> tuple[EvaluationScores, dict, dict]:
        classification = version.get("classification") or {}
        bloom = classification.get("bloom") or {}
        clos = version.get("clos") if isinstance(version.get("clos"), list) else []
        missing_fields = []
        issues = []
        score_values = scores.model_dump()

        if not bloom.get("level"):
            missing_fields.append("bloom")
            issues.append("Câu hỏi chưa được gắn mức Bloom")
            score_values["bloom_alignment"] = min(scores.bloom_alignment, 0.35)
        valid_clos = [
            clo
            for clo in clos
            if isinstance(clo, dict)
            and str(clo.get("code") or clo.get("clo_code") or "").strip()
            and str(clo.get("description") or "").strip()
        ]
        if not valid_clos:
            missing_fields.append("clo")
            issues.append("Câu hỏi chưa được gắn chuẩn đầu ra CLO hợp lệ")
            score_values["clo_alignment"] = min(scores.clo_alignment, 0.35)

        guardrail = {
            "applied": bool(issues),
            "missing_fields": missing_fields,
            "issues": issues,
        }
        if not issues:
            return scores, feedback, {**evidence, "metadata_guardrail": guardrail}

        current_action = str(feedback.get("action") or "").strip().upper()
        current_severity = str(feedback.get("severity") or "").strip().upper()
        guarded_feedback = {
            **feedback,
            "action": "REJECT" if current_action == "REJECT" else "NEEDS_REVISION",
            "severity": "HIGH" if current_severity == "HIGH" else "MEDIUM",
            "summary": (
                feedback.get("summary")
                if current_action in {"NEEDS_REVISION", "REJECT"}
                else "Guardrail metadata yêu cầu bổ sung Bloom/CLO trước khi duyệt."
            ),
            "missing": list(
                dict.fromkeys([*(feedback.get("missing") or []), *issues])
            ),
        }
        guarded_evidence = {
            **evidence,
            "risks": list(
                dict.fromkeys(
                    [
                        *(evidence.get("risks") or []),
                        "Thiếu metadata sư phạm bắt buộc để kiểm duyệt nhất quán",
                    ]
                )
            ),
            "metadata_guardrail": guardrail,
        }
        return EvaluationScores(**score_values), guarded_feedback, guarded_evidence

    @classmethod
    def _apply_evaluation_guardrails(
        cls,
        scores: EvaluationScores,
        feedback: dict,
        evidence: dict,
        version: dict,
    ) -> tuple[EvaluationScores, dict, dict]:
        scores, feedback, evidence = cls._apply_answer_guardrail(
            scores,
            feedback,
            evidence,
            version,
        )
        return cls._apply_metadata_guardrail(
            scores,
            feedback,
            evidence,
            version,
        )

    @staticmethod
    def _validate_llm_evaluation_consistency(
        scores: EvaluationScores,
        feedback: dict,
        evidence: dict,
        policy: dict,
    ) -> dict:
        score_values = scores.model_dump()
        weights = policy.get("weights") or DEFAULT_WEIGHTS
        thresholds = policy.get("thresholds") or DEFAULT_THRESHOLDS
        pass_min = thresholds.get("pass_min", DEFAULT_THRESHOLDS["pass_min"])
        overall = round(
            sum(score_values[key] * weights.get(key, DEFAULT_WEIGHTS[key]) for key in DEFAULT_WEIGHTS),
            4,
        )
        action = str(feedback.get("action") or "").strip().upper()
        severity = str(feedback.get("severity") or "").strip().upper()
        moodle_readiness = str(evidence.get("moodle_readiness") or "").strip().upper()
        contradictions = []
        if action == "APPROVE" and overall < pass_min:
            contradictions.append("APPROVE nhưng tổng điểm dưới ngưỡng đạt")
        if action == "APPROVE" and severity == "HIGH":
            contradictions.append("APPROVE nhưng mức độ lỗi là HIGH")
        if action == "APPROVE" and moodle_readiness == "NEEDS_FIX":
            contradictions.append("APPROVE nhưng cấu trúc Moodle vẫn NEEDS_FIX")
        if action == "REJECT" and severity == "LOW":
            contradictions.append("REJECT nhưng mức độ lỗi chỉ là LOW")
        if action == "REJECT" and moodle_readiness == "READY":
            contradictions.append("REJECT nhưng kết quả lại ghi Moodle READY")
        if contradictions:
            raise ValueError("AI evaluation tự mâu thuẫn: " + "; ".join(contradictions))

        values = list(score_values.values())
        score_spread = round(max(values) - min(values), 4)
        return {
            "validated": True,
            "calculated_overall": overall,
            "score_spread": score_spread,
            "uniform_scores": score_spread <= 0.02,
            "weak_criteria": [
                key
                for key, value in score_values.items()
                if value < pass_min
            ],
        }

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
        feedback_action = str(payload.feedback.get("action") or "").strip().upper()
        feedback_severity = str(payload.feedback.get("severity") or "").strip().upper()
        action_requires_review = feedback_action in {"NEEDS_REVISION", "REJECT"}
        severe_issue = feedback_severity == "HIGH"
        passed = (
            overall >= thresholds["pass_min"]
            and not action_requires_review
            and not severe_issue
        )
        if feedback_action == "REJECT" or severe_issue:
            color = "RED"
        elif action_requires_review and color == "GREEN":
            color = "YELLOW"
        evidence = {
            **payload.evidence,
            "decision_guardrail": {
                "score_passed": overall >= thresholds["pass_min"],
                "feedback_action": feedback_action or None,
                "feedback_severity": feedback_severity or None,
                "blocked_pass": action_requires_review or severe_issue,
            },
        }
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
            "evaluator_model": payload.model_snapshot or self._model_snapshot(payload.evaluator_model_code),
            "model_execution": payload.model_execution,
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
            "evidence": evidence,
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
        model_snapshot: dict = {}
        llm = None
        if evaluator_code.lower() in {"local-heuristic-evaluator-v1", "heuristic"}:
            scores, feedback, evidence = self._auto_scores(question, version)
            scores, feedback, evidence = self._apply_evaluation_guardrails(
                scores,
                feedback,
                evidence,
                version,
            )
            evidence["mode"] = "heuristic"
            evaluator_code = "local-heuristic-evaluator-v1"
        else:
            try:
                model_snapshot = resolve_model_snapshot(
                    evaluator_code,
                    capability=EVALUATION_CAPABILITY,
                    database=self.db,
                )
                model_snapshot = _limit_evaluation_output(model_snapshot)
                llm = get_llm_service(evaluator_code, model_snapshot=model_snapshot)
                policy = self._policy()
                policy_snapshot = self._policy_snapshot(policy)
                prompt, prompt_snapshot, _ = self._build_evaluation_prompt(question, version, policy)
                started = time.perf_counter()
                raw_model_response = await llm.generate_text(prompt)
                duration_ms = int((time.perf_counter() - started) * 1000)
                scores, feedback, evidence = self._parse_llm_evaluation(raw_model_response)
                scores, feedback, evidence = self._apply_evaluation_guardrails(
                    scores,
                    feedback,
                    evidence,
                    version,
                )
                evidence = {
                    **evidence,
                    "mode": "local_llm",
                    "consistency": self._validate_llm_evaluation_consistency(
                        scores,
                        feedback,
                        evidence,
                        policy_snapshot,
                    ),
                }
            except Exception as exc:
                if not payload.fallback_to_heuristic:
                    raise ValueError(f"Local evaluator failed: {exc}") from exc
                scores, feedback, evidence = self._auto_scores(question, version)
                scores, feedback, evidence = self._apply_evaluation_guardrails(
                    scores,
                    feedback,
                    evidence,
                    version,
                )
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
                model_snapshot=model_snapshot,
                model_execution=(
                    get_llm_execution_snapshot(llm)
                    if llm is not None and evaluator_code != "local-heuristic-evaluator-v1"
                    else {}
                ),
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

    def _supersede_previous_evaluation_jobs(
        self,
        question_id: ObjectId,
        current_version_id: ObjectId,
        superseding_job_id: ObjectId,
        now,
        *,
        session=None,
    ) -> int:
        error = {
            "message": "Evaluation được thay thế bởi phiên bản câu hỏi mới hơn",
            "stage": "SUPERSEDED",
            "at": now,
        }
        result = self.db.evaluation_jobs.update_many(
            {
                "question_id": question_id,
                "question_version_id": {"$ne": current_version_id},
                "status": {"$in": list(EVALUATION_ACTIVE_STATUSES)},
            },
            {
                "$set": {
                    "status": "STALE",
                    "error": error,
                    "superseded_by_job_id": superseding_job_id,
                    "finished_at": now,
                    "expires_at": now + timedelta(days=settings.job_retention_days),
                    "updated_at": now,
                },
                "$unset": {
                    "locked_by": "",
                    "lease_expires_at": "",
                    "heartbeat_at": "",
                    "next_attempt_at": "",
                },
            },
            session=session,
        )
        return result.modified_count

    def enqueue_auto_evaluation(
        self,
        question_id: str,
        *,
        expected_version: int,
        requested_by_user_id,
        evaluator_model_code: str = DEFAULT_EVALUATOR_MODEL_CODE,
        trigger: str = "REVIEWER_REQUEST",
        model_snapshot: dict | None = None,
        fallback_model_snapshot: dict | None = None,
        fallback_to_heuristic: bool = False,
    ) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != expected_version:
            raise RuntimeError("VERSION_CONFLICT")

        evaluator_model_code = evaluator_model_code.strip() or DEFAULT_EVALUATOR_MODEL_CODE
        model_snapshot = model_snapshot or resolve_model_snapshot(
            evaluator_model_code,
            capability=EVALUATION_CAPABILITY,
            database=self.db,
        )
        model_snapshot = _limit_evaluation_output(model_snapshot)
        if settings.evaluation_fallback_provider and fallback_model_snapshot is None:
            fallback_model_snapshot = resolve_model_snapshot(
                settings.evaluation_fallback_provider,
                capability=EVALUATION_CAPABILITY,
                database=self.db,
            )
        fallback_model_snapshot = _limit_evaluation_output(fallback_model_snapshot)
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
            "model_snapshot": model_snapshot,
            "fallback_model_snapshot": fallback_model_snapshot,
            "fallback_to_heuristic": bool(fallback_to_heuristic),
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
            "processing_attempt_count": 0,
            "max_attempts": settings.job_max_attempts,
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
                self._supersede_previous_evaluation_jobs(
                    question["_id"],
                    version["_id"],
                    job["_id"],
                    now,
                    session=session,
                )
        except DuplicateKeyError:
            active_job = self.db.evaluation_jobs.find_one(
                {"dedupe_key": dedupe_key, "status": {"$in": list(EVALUATION_ACTIVE_STATUSES)}}
            )
            if active_job:
                return json_safe(active_job)
            raise
        return json_safe(job)

    def mark_evaluation_enqueue_error(
        self,
        question_id: str,
        *,
        expected_version: int,
        evaluator_model_code: str,
        message: str,
    ) -> dict | None:
        now = utc_now()
        error = {"message": message, "at": now, "stage": "ENQUEUE"}
        updated = self.db.questions.find_one_and_update(
            {
                "_id": object_id(question_id, "question_id"),
                "current_version": expected_version,
                "lifecycle_status": "ACTIVE",
                "evaluation_status": {"$in": list(EVALUATION_RETRYABLE_STATUSES)},
            },
            {
                "$set": {
                    "evaluation_status": "ERROR",
                    "quality_summary": {
                        "evaluated_version_id": None,
                        "evaluator_model_code": evaluator_model_code,
                        "error": error,
                    },
                    "updated_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return json_safe(updated) if updated else None

    def _mark_evaluation_job_error(
        self,
        job: dict,
        message: str,
        *,
        status: str = "ERROR",
        raw_model_response: str | None = None,
        duration_ms: int | None = None,
        dead_lettered: bool = False,
    ) -> dict:
        now = utc_now()
        error = {
            "message": message,
            "raw_model_response_excerpt": (raw_model_response or "")[:1200] or None,
            "at": now,
        }
        with mongo_transaction() as session:
            job_fields = {
                "status": status,
                "error": error,
                "finished_at": now,
                "duration_ms": duration_ms,
                "updated_at": now,
            }
            if dead_lettered:
                job_fields["dead_lettered_at"] = now
            if status in {"ERROR", "STALE", "CANCELLED"}:
                job_fields["expires_at"] = now + timedelta(days=settings.job_retention_days)
            job_query = {"_id": job["_id"], "status": {"$in": ["QUEUED", "PROCESSING"]}}
            if job.get("locked_by"):
                job_query["locked_by"] = job["locked_by"]
            self.db.evaluation_jobs.update_one(
                job_query,
                {
                    "$set": job_fields,
                    "$unset": {"locked_by": "", "lease_expires_at": "", "heartbeat_at": ""},
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

    def heartbeat_evaluation_job(self, job_id: str, worker_id: str) -> bool:
        now = utc_now()
        result = self.db.evaluation_jobs.update_one(
            {
                "_id": object_id(job_id, "evaluation_job_id"),
                "status": "PROCESSING",
                "locked_by": worker_id,
            },
            {
                "$set": {
                    "heartbeat_at": now,
                    "lease_expires_at": now + timedelta(seconds=settings.job_lease_seconds),
                    "updated_at": now,
                }
            },
        )
        return result.modified_count == 1

    def _retry_or_dead_letter_evaluation_job(
        self,
        job: dict,
        message: str,
        *,
        raw_model_response: str | None,
        duration_ms: int,
    ) -> dict:
        attempts = int(job.get("processing_attempt_count") or 1)
        max_attempts = int(job.get("max_attempts") or settings.job_max_attempts)
        if attempts >= max_attempts:
            return self._mark_evaluation_job_error(
                job,
                message,
                raw_model_response=raw_model_response,
                duration_ms=duration_ms,
                dead_lettered=True,
            )
        now = utc_now()
        delay = min(
            settings.job_retry_base_seconds * (2 ** max(0, attempts - 1)),
            settings.job_retry_max_seconds,
        )
        error = {
            "message": message,
            "raw_model_response_excerpt": (raw_model_response or "")[:1200] or None,
            "at": now,
        }
        with mongo_transaction() as session:
            self.db.evaluation_jobs.update_one(
                {
                    "_id": job["_id"],
                    "status": "PROCESSING",
                    "locked_by": job.get("locked_by"),
                },
                {
                    "$set": {
                        "status": "QUEUED",
                        "error": error,
                        "next_attempt_at": now + timedelta(seconds=delay),
                        "updated_at": now,
                    },
                    "$unset": {"locked_by": "", "lease_expires_at": "", "heartbeat_at": ""},
                },
                session=session,
            )
            self.db.questions.update_one(
                {"_id": job["question_id"], "current_version_id": job["question_version_id"]},
                {
                    "$set": {
                        "evaluation_status": "QUEUED",
                        "quality_summary.last_retry_error": error,
                        "updated_at": now,
                    }
                },
                session=session,
            )
        return json_safe({**job, "status": "QUEUED", "error": error})

    async def process_evaluation_job(self, job_id: str, worker_id: str) -> dict | None:
        job_oid = object_id(job_id, "evaluation_job_id")
        now = utc_now()
        job = await asyncio.to_thread(
            self.db.evaluation_jobs.find_one_and_update,
            {
                "_id": job_oid,
                "$or": [
                    {
                        "status": "QUEUED",
                        "$or": [
                            {"next_attempt_at": {"$exists": False}},
                            {"next_attempt_at": {"$lte": now}},
                        ],
                    },
                    {"status": "PROCESSING", "lease_expires_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "status": "PROCESSING",
                    "locked_by": worker_id,
                    "started_at": now,
                    "heartbeat_at": now,
                    "lease_expires_at": now + timedelta(seconds=settings.job_lease_seconds),
                    "updated_at": now,
                },
                "$inc": {"processing_attempt_count": 1},
                "$unset": {"next_attempt_at": ""},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not job:
            return None

        question, version = await asyncio.gather(
            asyncio.to_thread(
                self.db.questions.find_one,
                {
                    "_id": job["question_id"],
                    "schema_version": SCHEMA_VERSION,
                    "lifecycle_status": "ACTIVE",
                },
            ),
            asyncio.to_thread(
                self.db.question_versions.find_one,
                {"_id": job["question_version_id"]},
            ),
        )
        if not question or not version or question.get("current_version_id") != job["question_version_id"]:
            return await asyncio.to_thread(
                self._mark_evaluation_job_error,
                job,
                "Phiên bản câu hỏi đã thay đổi trước khi AI đánh giá",
                status="STALE",
            )

        await asyncio.to_thread(
            self.db.questions.update_one,
            {
                "_id": question["_id"],
                "current_version_id": version["_id"],
                "evaluation_status": {"$in": ["QUEUED", "PROCESSING"]},
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
            policy_snapshot = job.get("policy_snapshot")
            if not policy_snapshot:
                policy_snapshot = await asyncio.to_thread(self._policy)
            prompt, prompt_snapshot, _ = await asyncio.to_thread(
                self._build_evaluation_prompt,
                question,
                version,
                policy_snapshot,
            )
            prompt, prompt_snapshot, effective_model_snapshot = _prepare_evaluation_attempt(
                prompt,
                prompt_snapshot,
                job.get("model_snapshot"),
                int(job.get("processing_attempt_count") or 1),
            )
            llm = get_llm_service(
                job.get("evaluator_model_code") or DEFAULT_EVALUATOR_MODEL_CODE,
                settings.evaluation_fallback_provider,
                model_snapshot=effective_model_snapshot,
                fallback_model_snapshot=job.get("fallback_model_snapshot"),
            )
            heuristic_fallback = False
            try:
                raw_model_response = await llm.generate_text(prompt)
                scores, feedback, evidence = self._parse_llm_evaluation(raw_model_response)
                scores, feedback, evidence = self._apply_evaluation_guardrails(
                    scores,
                    feedback,
                    evidence,
                    version,
                )
                evidence = {
                    **evidence,
                    "consistency": self._validate_llm_evaluation_consistency(
                        scores,
                        feedback,
                        evidence,
                        policy_snapshot,
                    ),
                }
            except Exception as exc:
                if not job.get("fallback_to_heuristic"):
                    raise
                heuristic_fallback = True
                scores, feedback, evidence = self._auto_scores(question, version)
                scores, feedback, evidence = self._apply_evaluation_guardrails(
                    scores,
                    feedback,
                    evidence,
                    version,
                )
                feedback = {
                    **feedback,
                    "summary": "AI đánh giá lỗi; hệ thống đã dùng heuristic dự phòng.",
                }
                evidence = {**evidence, "fallback_reason": str(exc)}
            duration_ms = int((time.perf_counter() - started) * 1000)
            evidence = {
                **evidence,
                "mode": "heuristic_fallback" if heuristic_fallback else "local_llm",
                "evaluation_job_id": str(job["_id"]),
                "source_snapshot": json_safe(job.get("source_snapshot") or []),
            }
            evaluation_payload = EvaluationCreateRequest(
                    expected_version=version["version"],
                    scores=scores,
                    feedback=feedback,
                    evidence=evidence,
                    evaluator_model_code=job.get("evaluator_model_code") or DEFAULT_EVALUATOR_MODEL_CODE,
                    raw_model_response=raw_model_response,
                    policy_snapshot=policy_snapshot,
                    prompt_snapshot=prompt_snapshot,
                    duration_ms=duration_ms,
                    evaluation_job_id=str(job["_id"]),
                    trigger=job.get("trigger"),
                    model_snapshot=(
                        {
                            "model_code": "local-heuristic-evaluator-v1",
                            "model_name": "Local heuristic evaluator",
                            "runtime": "INTERNAL",
                        }
                        if heuristic_fallback
                        else effective_model_snapshot or {}
                    ),
                    model_execution=get_llm_execution_snapshot(llm),
                )
            evaluation = await asyncio.to_thread(
                self.evaluate,
                str(question["_id"]),
                evaluation_payload,
                job.get("requested_by_user_id"),
            )
            finished_at = utc_now()
            await asyncio.to_thread(
                self.db.evaluation_jobs.update_one,
                {
                    "_id": job["_id"],
                    "status": "PROCESSING",
                    "locked_by": worker_id,
                },
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
                        "model_execution": get_llm_execution_snapshot(llm),
                        "finished_at": finished_at,
                        "expires_at": finished_at + timedelta(days=settings.job_retention_days),
                        "updated_at": finished_at,
                    },
                    "$unset": {
                        "locked_by": "",
                        "lease_expires_at": "",
                        "heartbeat_at": "",
                        "next_attempt_at": "",
                    },
                },
            )
            return evaluation
        except RuntimeError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            if str(exc) == "VERSION_CONFLICT":
                return await asyncio.to_thread(
                    self._mark_evaluation_job_error,
                    job,
                    "Phiên bản câu hỏi đã thay đổi trong lúc AI đánh giá",
                    status="STALE",
                    raw_model_response=raw_model_response,
                    duration_ms=duration_ms,
                )
            return await asyncio.to_thread(
                self._retry_or_dead_letter_evaluation_job,
                job,
                str(exc),
                raw_model_response=raw_model_response,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return await asyncio.to_thread(
                self._retry_or_dead_letter_evaluation_job,
                job,
                str(exc),
                raw_model_response=raw_model_response,
                duration_ms=duration_ms,
            )

    def _lock_expires_at(self, now) -> object:
        return now + timedelta(minutes=max(1, settings.review_lock_timeout_minutes))

    def _assignment_available_filter(self, current_user: CurrentUser, now) -> list[dict]:
        if has_permission(current_user, "questions.review_assign"):
            return []
        return [
            {"review_assignment": {"$exists": False}},
            {"review_assignment.status": "UNASSIGNED"},
            {"review_assignment.reviewer_user_id": current_user.id},
            {"review_assignment.lock_expires_at": None},
            {"review_assignment.lock_expires_at": {"$lte": now}},
        ]

    def _ensure_review_lock(self, question: dict, current_user: CurrentUser, now) -> None:
        if has_permission(current_user, "questions.review_assign"):
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
                "$or": [
                    {"role": "Reviewer"},
                    {"permissions": "questions.review"},
                ],
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
        if not self._has_review_scope(question, version, current_user):
            raise PermissionError("Bạn chưa được phân công vào học phần của câu hỏi")
        if self._owns_question(question, version, current_user.id):
            raise PermissionError("Người tạo hoặc chủ nguồn không được tự kiểm duyệt câu hỏi")
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
        if not has_permission(current_user, "questions.review_assign"):
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
            subject_id = subject_id_from_record(question, version)
            if (
                subject_id is not None
                and getattr(self.db, "subject_memberships", None) is not None
                and not has_subject_access(self.db, reviewer["_id"], subject_id)
            ):
                raise ValueError("Reviewer chưa được phân công vào học phần của câu hỏi")
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
        assignment_query = {
            "_id": question["_id"],
            "current_version_id": version["_id"],
            "lifecycle_status": "ACTIVE",
            "review_status": "PENDING",
        }
        if "review_assignment" in question:
            assignment_query["review_assignment"] = question.get("review_assignment")
        updated = self.db.questions.find_one_and_update(
            assignment_query,
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

    def get_review_draft(self, question_id: str, current_user: CurrentUser) -> dict | None:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        draft = self.db.question_review_drafts.find_one(
            {
                "question_id": question["_id"],
                "reviewer_user_id": current_user.id,
            }
        )
        if not draft:
            return None
        draft["is_stale"] = draft.get("question_version_id") != version["_id"]
        return json_safe(draft)

    def save_review_draft(
        self,
        question_id: str,
        payload: ReviewDraftUpsertRequest,
        current_user: CurrentUser,
    ) -> dict:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        now = utc_now()
        draft = self.db.question_review_drafts.find_one_and_update(
            {
                "question_id": question["_id"],
                "reviewer_user_id": current_user.id,
            },
            {
                "$set": {
                    "schema_version": SCHEMA_VERSION,
                    "question_version_id": version["_id"],
                    "question_version": version["version"],
                    "decision": payload.decision,
                    "draft": payload.draft,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "question_id": question["_id"],
                    "reviewer_user_id": current_user.id,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return json_safe(draft)

    def delete_review_draft(self, question_id: str, current_user: CurrentUser) -> bool:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        result = self.db.question_review_drafts.delete_one(
            {
                "question_id": question["_id"],
                "reviewer_user_id": current_user.id,
            }
        )
        return bool(result.deleted_count)

    def review(self, question_id: str, payload: ReviewCreateRequest, current_user: CurrentUser) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        if question.get("review_status") != "PENDING":
            raise ValueError("Chỉ câu hỏi đang chờ duyệt mới có thể được kiểm duyệt")
        if not self._has_review_scope(question, version, current_user):
            raise PermissionError("Bạn chưa được phân công vào học phần của câu hỏi")
        if self._owns_question(question, version, current_user.id):
            raise PermissionError("Người tạo hoặc chủ nguồn không được tự kiểm duyệt câu hỏi")
        if payload.override.applied and not has_permission(current_user, "questions.review_override"):
            raise PermissionError("Bạn không có quyền override kết quả đánh giá AI")
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
            update_query = {
                "_id": question["_id"],
                "current_version_id": version["_id"],
                "lifecycle_status": "ACTIVE",
                "latest_review_id": question.get("latest_review_id"),
            }
            if not has_permission(current_user, "questions.review_assign"):
                assignment = question.get("review_assignment") or {}
                update_query.update(
                    {
                        "review_assignment.status": "IN_REVIEW",
                        "review_assignment.reviewer_user_id": current_user.id,
                        "review_assignment.lock_expires_at": assignment.get("lock_expires_at"),
                    }
                )
            result = self.db.questions.update_one(
                update_query,
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
        if hasattr(self.db, "question_review_drafts"):
            self.db.question_review_drafts.delete_one(
                {
                    "question_id": question["_id"],
                    "reviewer_user_id": current_user.id,
                }
            )
        return json_safe(review)

    def list_comments(self, question_id: str, current_user: CurrentUser) -> dict:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        comments = list(
            self.db.question_comments.find({"question_id": question["_id"], "deleted_at": None})
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

    def update_comment(
        self,
        question_id: str,
        comment_id: str,
        payload: QuestionCommentUpdateRequest,
        current_user: CurrentUser,
    ) -> dict:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        query = {
            "_id": object_id(comment_id, "comment_id"),
            "question_id": question["_id"],
            "deleted_at": None,
        }
        if current_user.role != "Admin":
            query["author_user_id"] = current_user.id
        now = utc_now()
        updated = self.db.question_comments.find_one_and_update(
            query,
            {"$set": {"body": payload.body.strip(), "updated_at": now, "edited_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise PermissionError("Bạn chỉ có thể sửa bình luận của mình")
        self.db.audit_logs.insert_one(
            {
                "schema_version": SCHEMA_VERSION,
                "actor": {"type": "USER", "user_id": current_user.id, "model_id": None, "service_name": None},
                "entity": {"type": "QUESTION", "id": question["_id"], "version_id": version["_id"]},
                "action": "QUESTION_COMMENT_UPDATED",
                "changes": [],
                "before_hash": version["content_hash"],
                "after_hash": version["content_hash"],
                "metadata": {"comment_id": updated["_id"]},
                "created_at": now,
            }
        )
        return json_safe(updated)

    def delete_comment(
        self,
        question_id: str,
        comment_id: str,
        current_user: CurrentUser,
    ) -> bool:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        query = {
            "_id": object_id(comment_id, "comment_id"),
            "question_id": question["_id"],
            "deleted_at": None,
        }
        if current_user.role != "Admin":
            query["author_user_id"] = current_user.id
        now = utc_now()
        updated = self.db.question_comments.find_one_and_update(
            query,
            {"$set": {"body": "", "deleted_at": now, "deleted_by_user_id": current_user.id, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise PermissionError("Bạn chỉ có thể xóa bình luận của mình")
        self.db.audit_logs.insert_one(
            {
                "schema_version": SCHEMA_VERSION,
                "actor": {"type": "USER", "user_id": current_user.id, "model_id": None, "service_name": None},
                "entity": {"type": "QUESTION", "id": question["_id"], "version_id": version["_id"]},
                "action": "QUESTION_COMMENT_DELETED",
                "changes": [],
                "before_hash": version["content_hash"],
                "after_hash": version["content_hash"],
                "metadata": {"comment_id": updated["_id"]},
                "created_at": now,
            }
        )
        return True

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

    @staticmethod
    def _moodle_export_error(question: dict, version: dict, expected_version: int | None = None) -> tuple[str, str] | None:
        if expected_version is not None and question["current_version"] != expected_version:
            return "VERSION_CONFLICT", "Phiên bản câu hỏi đã thay đổi"
        if question["review_status"] != "APPROVED":
            return "NOT_APPROVED", "Câu hỏi chưa được duyệt"
        if question.get("approved_version_id") != version["_id"]:
            return "STALE_APPROVAL", "Phiên bản hiện tại chưa được duyệt"
        return None

    def export_moodle(
        self,
        question_id: str,
        export_format: str = "gift",
        current_user: CurrentUser | None = None,
    ) -> dict:
        question, version = self._pair(question_id)
        self._ensure_read_access(question, version, current_user)
        eligibility_error = self._moodle_export_error(question, version)
        if eligibility_error:
            raise ValueError(eligibility_error[1])
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

    def export_moodle_bulk(self, items, export_format: str, current_user: CurrentUser) -> dict:
        normalized = export_format.lower()
        if normalized not in {"gift", "xml"}:
            raise ValueError("Định dạng export Moodle phải là gift hoặc xml")
        resolved = []
        errors = []
        for item in items:
            try:
                question, version = self._pair(item.question_id)
                self._ensure_read_access(question, version, current_user)
                eligibility_error = self._moodle_export_error(
                    question, version, item.expected_version
                )
                if eligibility_error:
                    errors.append(
                        {
                            "question_id": item.question_id,
                            "question_code": question.get("question_code"),
                            "code": eligibility_error[0],
                            "message": eligibility_error[1],
                        }
                    )
                    continue
                resolved.append((question, version))
            except LookupError as exc:
                errors.append(
                    {
                        "question_id": item.question_id,
                        "question_code": None,
                        "code": "NOT_FOUND",
                        "message": str(exc),
                    }
                )
            except PermissionError as exc:
                errors.append(
                    {
                        "question_id": item.question_id,
                        "question_code": None,
                        "code": "FORBIDDEN",
                        "message": str(exc),
                    }
                )
            except ValueError as exc:
                errors.append(
                    {
                        "question_id": item.question_id,
                        "question_code": None,
                        "code": "INVALID_REQUEST",
                        "message": str(exc),
                    }
                )
        if errors:
            return {
                "filename": None,
                "content": None,
                "format": normalized,
                "exported_count": 0,
                "errors": errors,
            }
        if normalized == "gift":
            content = "\n\n".join(self._moodle_gift(question, version) for question, version in resolved) + "\n"
        else:
            body = "\n".join(self._moodle_xml_question(question, version) for question, version in resolved)
            content = f'<?xml version="1.0" encoding="UTF-8"?>\n<quiz>\n{body}\n</quiz>\n'
        return {
            "filename": f"moodle-questions.{normalized}",
            "content": content,
            "format": normalized,
            "exported_count": len(resolved),
            "errors": [],
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
        current_user = user_id if isinstance(user_id, CurrentUser) else None
        publisher_user_id = current_user.id if current_user else user_id
        publisher_role = current_user.role if current_user else publisher_role
        if current_user:
            self._ensure_read_access(question, version, current_user)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        eligibility_error = self._moodle_export_error(question, version, payload.expected_version)
        if eligibility_error:
            if eligibility_error[0] == "VERSION_CONFLICT":
                raise RuntimeError("VERSION_CONFLICT")
            raise ValueError(eligibility_error[1])

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
            "publisher_user_id": publisher_user_id,
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
        is_admin = self._can_manage_all(current_user)
        pending_base = {
            "schema_version": SCHEMA_VERSION,
            "lifecycle_status": "ACTIVE",
            "review_status": "PENDING",
        }
        if not is_admin and getattr(self.db, "subject_memberships", None) is not None:
            subject_ids = active_subject_ids(self.db, current_user.id)
            pending_base["$or"] = [
                {"subject_id": {"$in": list(subject_ids)}},
                {"subject_id": None},
            ]

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
        criterion_calibration = {
            key: {"sample_size": 0, "agreements": 0, "disagreements": 0}
            for key in REVIEW_CRITERION_KEYS
        }
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
            review_form = review.get("review_form") or {}
            human_by_key = {
                item.get("key"): item.get("rating")
                for item in review_form.get("criterion_assessments") or []
                if item.get("key") in criterion_calibration
            }
            if not human_by_key:
                for item in review_form.get("checklist") or []:
                    key = LEGACY_REVIEW_CRITERION_MAP.get(item.get("key"), item.get("key"))
                    if key in criterion_calibration:
                        human_by_key[key] = "PASS" if item.get("passed") else "FAIL"
            evaluation_scores = evaluation.get("scores") or {}
            for key, human_rating in human_by_key.items():
                ai_score = evaluation_scores.get(key)
                if not isinstance(ai_score, (int, float)) or human_rating == "NO_DATA":
                    continue
                ai_positive = ai_score >= DEFAULT_THRESHOLDS["pass_min"]
                human_positive = human_rating == "PASS"
                item = criterion_calibration[key]
                item["sample_size"] += 1
                if ai_positive == human_positive:
                    item["agreements"] += 1
                else:
                    item["disagreements"] += 1

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
            "criteria": {
                key: {
                    **value,
                    "agreement_rate": (
                        round(value["agreements"] / value["sample_size"], 3)
                        if value["sample_size"]
                        else None
                    ),
                }
                for key, value in criterion_calibration.items()
            },
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


async def _wait_for_evaluation_job_superseded(
    service: QuestionWorkflowService,
    job_id: str,
    worker_id: str,
    stop_event: asyncio.Event,
) -> bool:
    """Return True as soon as this worker's evaluation job is no longer active."""
    job_oid = object_id(job_id, "evaluation_job_id")
    poll_seconds = max(0.1, min(float(settings.job_worker_poll_seconds), 1.0))
    while not stop_event.is_set():
        job = await asyncio.to_thread(
            service.db.evaluation_jobs.find_one,
            {"_id": job_oid},
            {"status": 1, "locked_by": 1},
        )
        if not job:
            return True
        status = job.get("status")
        if status not in EVALUATION_ACTIVE_STATUSES:
            return True
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue
    return False


async def process_evaluation_job_background(job_id: str, worker_id: str) -> None:
    from core.job_worker import maintain_lease

    service = get_workflow_service()
    lease_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        maintain_lease(lambda: service.heartbeat_evaluation_job(job_id, worker_id), lease_stop)
    )
    async with evaluation_semaphore:
        processing_task = asyncio.create_task(service.process_evaluation_job(job_id, worker_id))
        superseded_task = asyncio.create_task(
            _wait_for_evaluation_job_superseded(
                service,
                job_id,
                worker_id,
                lease_stop,
            )
        )
        try:
            done, _ = await asyncio.wait(
                {processing_task, superseded_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            superseded = (
                superseded_task in done
                and superseded_task.result()
                and not processing_task.done()
            )
            if superseded:
                processing_task.cancel()
                try:
                    await processing_task
                except asyncio.CancelledError:
                    logger.info(
                        "Evaluation job %s stopped because a newer question version superseded it",
                        job_id,
                    )
            else:
                await processing_task
        finally:
            lease_stop.set()
            if not processing_task.done():
                processing_task.cancel()
                try:
                    await processing_task
                except asyncio.CancelledError:
                    pass
            if not superseded_task.done():
                superseded_task.cancel()
                try:
                    await superseded_task
                except asyncio.CancelledError:
                    pass
            await heartbeat_task
