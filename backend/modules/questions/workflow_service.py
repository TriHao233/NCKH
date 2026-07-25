import hashlib
import re

from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database, mongo_transaction
from modules.questions.repository import MongoQuestionRepository, json_safe, utc_now
from modules.questions.workflow_schemas import (
    AutoEvaluationRequest,
    EvaluationCreateRequest,
    EvaluationScores,
    MoodlePublicationRequest,
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


class QuestionWorkflowService:
    def __init__(self, database):
        self.db = database
        self.questions = MongoQuestionRepository(database)

    def _pair(self, question_id: str) -> tuple[dict, dict]:
        pair = self.questions.find_pair(question_id)
        if not pair:
            raise LookupError("Không tìm thấy câu hỏi")
        return pair

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

    def _auto_scores(self, question: dict, version: dict) -> tuple[EvaluationScores, dict, dict]:
        question_data = version.get("question_data") or {}
        sources = version.get("sources") or []
        source_context = "\n\n".join(
            str(source.get("context_excerpt") or "")
            for source in sources
            if source.get("context_excerpt")
        )
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
        policy = self._policy()
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
        evaluation = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "question_id": question["_id"],
            "question_version_id": version["_id"],
            "question_version": version["version"],
            "question_snapshot_hash": version["content_hash"],
            "generation_run_id": version.get("generation_run_id"),
            "evaluator_model": {
                "id": None,
                "model_code": payload.evaluator_model_code,
                "model_name": payload.evaluator_model_code,
                "config": {},
            },
            "requested_by_user_id": user_id,
            "policy": {
                "id": policy.get("_id"),
                "name": policy.get("policy_name"),
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
            "parser_version": "evaluation-json-v1",
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
                            "evaluated_version_id": version["_id"],
                            "overall_score": overall,
                            "color": color,
                            "evaluated_at": now,
                        },
                        "updated_at": now,
                    }
                },
                session=session,
            )
            if not result.matched_count:
                raise RuntimeError("VERSION_CONFLICT")
        return json_safe(evaluation)

    def auto_evaluate(self, question_id: str, payload: AutoEvaluationRequest, user_id) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        scores, feedback, evidence = self._auto_scores(question, version)
        return self.evaluate(
            question_id,
            EvaluationCreateRequest(
                expected_version=payload.expected_version,
                scores=scores,
                feedback=feedback,
                evidence=evidence,
                evaluator_model_code=payload.evaluator_model_code,
                raw_model_response=None,
            ),
            user_id,
        )

    def review(self, question_id: str, payload: ReviewCreateRequest, user_id) -> dict:
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
        review = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "question_id": question["_id"],
            "question_version_id": version["_id"],
            "question_version": version["version"],
            "reviewer_user_id": user_id,
            "decision": payload.decision,
            "note": payload.note,
            "override": payload.override.model_dump(),
            "supersedes_review_id": question.get("latest_review_id"),
            "previous_status": question["review_status"],
            "resulting_status": payload.decision,
            "reviewed_at": now,
        }
        question_fields = {
            "review_status": payload.decision,
            "latest_review_id": review["_id"],
            "updated_at": now,
        }
        if payload.decision == "APPROVED":
            question_fields["approved_version_id"] = version["_id"]
        elif question.get("approved_version_id") == version["_id"]:
            question_fields["approved_version_id"] = None
        audit = {
            "schema_version": SCHEMA_VERSION,
            "actor": {
                "type": "USER",
                "user_id": user_id,
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

    def publish_to_moodle(self, question_id: str, payload: MoodlePublicationRequest, user_id) -> dict:
        question, version = self._pair(question_id)
        if question["current_version"] != payload.expected_version:
            raise RuntimeError("VERSION_CONFLICT")
        if question["review_status"] != "APPROVED" or question.get("approved_version_id") != version["_id"]:
            raise ValueError("Chỉ câu hỏi đã được duyệt ở phiên bản hiện tại mới được xuất Moodle")

        target = {
            "moodle_site_id": payload.moodle_site_id,
            "course_id": payload.course_id,
            "category_id": payload.category_id,
        }
        published_content_hash = version["content_hash"]
        idempotency_material = "|".join(
            [
                payload.moodle_site_id,
                payload.course_id,
                payload.category_id,
                str(version["_id"]),
                published_content_hash,
            ]
        )
        idempotency_key = hashlib.sha256(idempotency_material.encode("utf-8")).hexdigest()
        now = utc_now()
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
            "moodle_question_ref_id": f"mock-{str(version['_id'])}",
            "request_payload": {
                "question_code": question["question_code"],
                "content": version["content"],
                "question_data": version.get("question_data") or {},
                "classification": version.get("classification") or {},
                "mock": payload.mock,
            },
            "response_payload": {
                "mock": payload.mock,
                "message": "Mock Moodle publication recorded locally",
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

    def history(self, question_id: str, kind: str) -> list[dict]:
        question, _ = self._pair(question_id)
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
