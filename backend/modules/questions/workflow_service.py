from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database, mongo_transaction
from modules.questions.repository import MongoQuestionRepository, json_safe, utc_now
from modules.questions.workflow_schemas import EvaluationCreateRequest, ReviewCreateRequest

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

    def history(self, question_id: str, kind: str) -> list[dict]:
        question, _ = self._pair(question_id)
        if kind == "evaluations":
            cursor = self.db.question_evaluations.find(
                {"question_id": question["_id"]}
            ).sort("created_at", -1)
        else:
            cursor = self.db.question_reviews.find(
                {"question_id": question["_id"]}
            ).sort("reviewed_at", -1)
        return [json_safe(item) for item in cursor]


def get_workflow_service() -> QuestionWorkflowService:
    return QuestionWorkflowService(get_database())
