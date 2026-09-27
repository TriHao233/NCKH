from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.bootstrap import SCHEMA_VERSION
from core.database import get_database
from modules.questions.repository import json_safe, object_id

logger = logging.getLogger(__name__)
# Decisions after which a resubmission should reach the reviewer who made them.
RESUBMITTABLE_DECISIONS = {"NEEDS_REVISION", "REJECTED"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(record: dict) -> dict:
    return json_safe(
        {
            "id": record["_id"],
            "type": record["type"],
            "title": record["title"],
            "body": record.get("body", ""),
            "link": record.get("link", ""),
            "entity": record.get("entity") or {},
            "actor_user_id": record.get("actor_user_id"),
            "is_read": record.get("is_read", False),
            "read_at": record.get("read_at"),
            "created_at": record["created_at"],
        }
    )


class NotificationService:
    def __init__(self, database: Database):
        self.db = database

    def create(
        self,
        *,
        recipient_user_id: str | ObjectId | None,
        type: str,
        title: str,
        body: str = "",
        link: str = "",
        entity: dict[str, Any] | None = None,
        actor_user_id: str | ObjectId | None = None,
    ) -> dict | None:
        if recipient_user_id is None:
            return None
        now = utc_now()
        record = {
            "_id": ObjectId(),
            "schema_version": SCHEMA_VERSION,
            "recipient_user_id": object_id(recipient_user_id, "recipient_user_id"),
            "actor_user_id": object_id(actor_user_id, "actor_user_id")
            if actor_user_id is not None
            else None,
            "type": type,
            "title": title,
            "body": body,
            "link": link,
            "entity": entity or {},
            "is_read": False,
            "read_at": None,
            "created_at": now,
        }
        self.db.notifications.insert_one(record)
        return _serialize(record)

    def create_many(self, notifications: list[dict[str, Any]]) -> list[dict]:
        created = []
        seen: set[str] = set()
        for payload in notifications:
            recipient = payload.get("recipient_user_id")
            key = str(recipient)
            if not recipient or key in seen:
                continue
            seen.add(key)
            item = self.create(**payload)
            if item:
                created.append(item)
        return created

    def list(self, current_user, page: int, page_size: int, unread_only: bool = False) -> dict:
        query: dict = {"recipient_user_id": current_user.id}
        if unread_only:
            query["is_read"] = False
        total = self.db.notifications.count_documents(query)
        items = list(
            self.db.notifications.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [_serialize(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def unread_count(self, current_user) -> int:
        return self.db.notifications.count_documents(
            {"recipient_user_id": current_user.id, "is_read": False}
        )

    def mark_read(self, notification_id: str, current_user) -> dict | None:
        now = utc_now()
        record = self.db.notifications.find_one_and_update(
            {
                "_id": object_id(notification_id, "notification_id"),
                "recipient_user_id": current_user.id,
            },
            {"$set": {"is_read": True, "read_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize(record) if record else None

    def mark_all_read(self, current_user) -> int:
        now = utc_now()
        result = self.db.notifications.update_many(
            {"recipient_user_id": current_user.id, "is_read": False},
            {"$set": {"is_read": True, "read_at": now}},
        )
        return result.modified_count

    @staticmethod
    def _question_owner(question: dict, version: dict) -> ObjectId | None:
        return question.get("created_by_user_id") or version.get("created_by_user_id")

    @staticmethod
    def _question_entity(question: dict, version: dict) -> dict:
        return json_safe(
            {
                "type": "QUESTION",
                "id": question["_id"],
                "version_id": version["_id"],
                "question_code": question.get("question_code"),
            }
        )

    def notify_review_decision(
        self,
        *,
        question: dict,
        version: dict,
        review: dict,
        actor_user_id: ObjectId,
    ) -> dict | None:
        recipient = self._question_owner(question, version)
        if recipient is None or recipient == actor_user_id:
            return None
        decision = review.get("decision") or "PENDING"
        label = {
            "APPROVED": "đã được duyệt",
            "NEEDS_REVISION": "cần chỉnh sửa",
            "REJECTED": "bị từ chối",
        }.get(decision, decision)
        question_code = question.get("question_code", "Câu hỏi")
        return self.create(
            recipient_user_id=recipient,
            actor_user_id=actor_user_id,
            type=f"QUESTION_{decision}",
            title=f"{question_code} {label}",
            body=review.get("note") or "Reviewer đã cập nhật trạng thái kiểm duyệt.",
            link=f"/quan-ly?questionId={question['_id']}",
            entity=self._question_entity(question, version),
        )

    def notify_secondary_review_pending(
        self,
        *,
        question: dict,
        version: dict,
        reason: str,
        actor_user_id: ObjectId,
    ) -> dict | None:
        recipient = self._question_owner(question, version)
        if recipient is None or recipient == actor_user_id:
            return None
        question_code = question.get("question_code", "Câu hỏi")
        return self.create(
            recipient_user_id=recipient,
            actor_user_id=actor_user_id,
            type="QUESTION_SECONDARY_REVIEW_PENDING",
            title=f"{question_code} đạt lần duyệt đầu, đang chờ duyệt lần 2",
            body=reason or "Câu hỏi cần thêm một người duyệt xác nhận trước khi vào ngân hàng.",
            link=f"/quan-ly?questionId={question['_id']}",
            entity=self._question_entity(question, version),
        )

    def notify_exam_owners_question_reopened(
        self,
        *,
        question_id: str | ObjectId,
        question_code: str,
        actor_user_id: ObjectId,
    ) -> list[dict]:
        """An approved question was edited and left review: warn owners of open exams using it."""
        question_oid = object_id(question_id, "question_id")
        exams = list(
            self.db.exams.find(
                {
                    "questions.question_id": question_oid,
                    "status": {"$nin": ["FINALIZED", "ARCHIVED", "finalized", "archived"]},
                },
                {"name": 1, "created_by_user_id": 1},
            )
        )
        created = []
        for exam in exams:
            owner = exam.get("created_by_user_id")
            if not owner or owner == actor_user_id:
                continue
            item = self.create(
                recipient_user_id=owner,
                actor_user_id=actor_user_id,
                type="EXAM_QUESTION_NEEDS_REVIEW",
                title=f"{question_code} trong đề \"{exam.get('name', '')}\" đã bị sửa",
                body="Câu hỏi đã duyệt vừa được chỉnh sửa nên phải duyệt lại; đề chưa thể chốt với câu này.",
                link=f"/lam-de-thi/{exam['_id']}",
                entity=json_safe({"type": "EXAM", "id": exam["_id"], "question_id": question_oid}),
            )
            if item:
                created.append(item)
        return created

    def notify_review_assigned(
        self,
        *,
        question: dict,
        version: dict,
        reviewer_user_id: str | ObjectId | None,
        actor_user_id: ObjectId,
    ) -> dict | None:
        if reviewer_user_id is None:
            return None
        if reviewer_user_id == actor_user_id:
            return None
        question_code = question.get("question_code", "Câu hỏi")
        return self.create(
            recipient_user_id=reviewer_user_id,
            actor_user_id=actor_user_id,
            type="QUESTION_REVIEW_ASSIGNED",
            title=f"{question_code} được phân công kiểm duyệt",
            body="Admin đã phân công câu hỏi này cho bạn.",
            link=f"/kiem-duyet?questionId={question['_id']}",
            entity=self._question_entity(question, version),
        )

    def notify_question_resubmitted(
        self,
        *,
        question_id: str | ObjectId,
        previous_review_status: str | None,
        actor_user_id: ObjectId,
    ) -> list[dict]:
        # Editing a question moves it back to DRAFT before it is resubmitted, so
        # the status right before submission says nothing about earlier feedback.
        # Decide from the latest review decision instead.
        if previous_review_status == "PENDING":
            return []
        question = self.db.questions.find_one(
            {
                "_id": object_id(question_id, "question_id"),
                "schema_version": SCHEMA_VERSION,
                "lifecycle_status": "ACTIVE",
            }
        )
        if not question:
            return []
        version = self.db.question_versions.find_one({"_id": question["current_version_id"]})
        if not version:
            return []
        review = None
        if question.get("latest_review_id"):
            review = self.db.question_reviews.find_one({"_id": question["latest_review_id"]})
        if not review:
            review = self.db.question_reviews.find_one(
                {"question_id": question["_id"]},
                sort=[("reviewed_at", -1)],
            )
        decision = review.get("decision") if review else None
        if decision not in RESUBMITTABLE_DECISIONS:
            return []
        reviewer_id = review.get("reviewer_user_id")
        if not reviewer_id or reviewer_id == actor_user_id:
            return []
        question_code = question.get("question_code", "Câu hỏi")
        after_rejection = decision == "REJECTED"
        return self.create_many(
            [
                {
                    "recipient_user_id": reviewer_id,
                    "actor_user_id": actor_user_id,
                    "type": "QUESTION_RESUBMITTED",
                    "title": (
                        f"{question_code} được sửa và gửi lại sau khi bị từ chối"
                        if after_rejection
                        else f"{question_code} đã được gửi lại"
                    ),
                    "body": (
                        "Giảng viên đã chỉnh sửa câu hỏi bạn từ chối trước đó và gửi duyệt lại."
                        if after_rejection
                        else "Giảng viên đã chỉnh sửa theo yêu cầu và gửi lại câu hỏi cần duyệt."
                    ),
                    "link": f"/kiem-duyet?questionId={question['_id']}",
                    "entity": self._question_entity(question, version),
                }
            ]
        )


def get_notification_service() -> NotificationService:
    return NotificationService(get_database())


def safe_notify_review_decision(**kwargs) -> None:
    try:
        NotificationService(kwargs.pop("database")).notify_review_decision(**kwargs)
    except Exception as exc:
        logger.warning("Failed to notify review decision: %s", exc)


def safe_notify_exam_owners_question_reopened(**kwargs) -> None:
    try:
        NotificationService(kwargs.pop("database")).notify_exam_owners_question_reopened(**kwargs)
    except Exception as exc:
        logger.warning("Failed to notify exam owners about an edited question: %s", exc)


def safe_notify_secondary_review_pending(**kwargs) -> None:
    try:
        NotificationService(kwargs.pop("database")).notify_secondary_review_pending(**kwargs)
    except Exception as exc:
        logger.warning("Failed to notify pending secondary review: %s", exc)


def safe_notify_review_assigned(**kwargs) -> None:
    try:
        NotificationService(kwargs.pop("database")).notify_review_assigned(**kwargs)
    except Exception as exc:
        logger.warning("Failed to notify review assignment: %s", exc)


def safe_notify_question_resubmitted(**kwargs) -> None:
    try:
        NotificationService(kwargs.pop("database")).notify_question_resubmitted(**kwargs)
    except Exception as exc:
        logger.warning("Failed to notify question resubmission: %s", exc)
