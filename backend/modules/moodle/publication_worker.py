from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from modules.moodle.adapter import MoodleQuestionBankAdapter, MoodleRemoteUncertain
from modules.moodle.serializer import serialize_question


def _now():
    return datetime.now(timezone.utc)


class MoodlePublicationWorker:
    def __init__(self, database, adapter_factory=MoodleQuestionBankAdapter):
        self.db = database
        self.adapter_factory = adapter_factory

    def process_next(self, worker_id: str = "inline-admin") -> dict | None:
        now = _now()
        publication = self.db.moodle_publications.find_one_and_update(
            {"status": "QUEUED"},
            {
                "$set": {
                    "status": "PUBLISHING",
                    "worker_id": worker_id,
                    "lease_expires_at": now + timedelta(minutes=2),
                    "updated_at": now,
                }
            },
            sort=[("created_at", 1)],
            return_document=ReturnDocument.AFTER,
        )
        if not publication:
            return None
        return self._process(publication)

    def _target(self, publication):
        target_id = (publication.get("target") or {}).get("target_id")
        target = self.db.moodle_targets.find_one({"_id": target_id, "is_active": True})
        if not target or target.get("mode") != "REST_API":
            raise ValueError("Moodle REST target không tồn tại hoặc đang bị khóa")
        return target

    def _process(self, publication: dict) -> dict:
        now = _now()
        try:
            target = self._target(publication)
            question = self.db.questions.find_one({"_id": publication["question_id"]})
            version = self.db.question_versions.find_one({"_id": publication["question_version_id"]})
            if not question or not version:
                raise ValueError("Question/version của publication không còn tồn tại")
            serialized = serialize_question(question, version)
            target_ref = publication["target"]
            result = self.adapter_factory(target).publish(
                serialized,
                course_id=target_ref["course_id"],
                category_id=target_ref["category_id"],
                idempotency_key=publication["idempotency_key"],
            )
            if not result["verified"]:
                raise MoodleRemoteUncertain("Remote write chưa verify được content/version")
            updates = {
                "status": "PUBLISHED",
                "external_sync": True,
                "status_detail": "REMOTE_VERIFIED",
                "moodle_question_ref_id": result["remote_id"],
                "response_payload": result,
                "published_at": now,
                "updated_at": now,
                "error": None,
            }
            self.db.moodle_publications.update_one(
                {"_id": publication["_id"], "status": "PUBLISHING"}, {"$set": updates}
            )
            self.db.questions.update_one(
                {"_id": question["_id"], "current_version_id": version["_id"], "review_status": "APPROVED"},
                {"$set": {"publication_status": "PUBLISHED", "updated_at": now}},
            )
        except MoodleRemoteUncertain as exc:
            self.db.moodle_publications.update_one(
                {"_id": publication["_id"]},
                {
                    "$set": {
                        "status": "UNKNOWN",
                        "external_sync": False,
                        "status_detail": "CONFIRMATION_REQUIRED",
                        "error": {"code": "REMOTE_UNCERTAIN", "message": str(exc)},
                        "updated_at": now,
                    }
                },
            )
        except Exception as exc:
            self.db.moodle_publications.update_one(
                {"_id": publication["_id"]},
                {
                    "$set": {
                        "status": "FAILED",
                        "external_sync": False,
                        "status_detail": "CONFIRMED_FAILURE",
                        "error": {"code": "REMOTE_FAILURE", "message": str(exc)},
                        "updated_at": now,
                    }
                },
            )
        return self.db.moodle_publications.find_one({"_id": publication["_id"]})

    def reconcile(self, publication_id) -> dict:
        publication = self.db.moodle_publications.find_one({"_id": publication_id})
        if not publication or publication.get("status") != "UNKNOWN":
            raise ValueError("Chỉ publication UNKNOWN mới được đối soát")
        target = self._target(publication)
        found = self.adapter_factory(target).find_by_idempotency_key(publication["idempotency_key"])
        now = _now()
        if not found:
            updates = {"status": "FAILED", "status_detail": "REMOTE_NOT_FOUND", "updated_at": now}
        else:
            verified = self.adapter_factory(target).verify(
                str(found["questionid"]), str(publication["question_version_id"]), publication["published_content_hash"]
            )
            updates = {
                "status": "PUBLISHED" if verified else "FAILED",
                "external_sync": bool(verified),
                "status_detail": "REMOTE_VERIFIED" if verified else "REMOTE_MISMATCH",
                "moodle_question_ref_id": str(found["questionid"]),
                "updated_at": now,
                "published_at": now if verified else None,
            }
        self.db.moodle_publications.update_one({"_id": publication["_id"], "status": "UNKNOWN"}, {"$set": updates})
        return self.db.moodle_publications.find_one({"_id": publication["_id"]})
