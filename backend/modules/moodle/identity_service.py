from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from datetime import datetime, timezone

from bson import ObjectId

from modules.admin.moodle_schemas import MoodleSyncPageRequest


def _now():
    return datetime.now(timezone.utc)


class MoodleIdentitySyncService:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def _page_key(payload: MoodleSyncPageRequest) -> str:
        raw = f"{payload.site_key}|{payload.sync_id}|{payload.checkpoint}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _resolve_identity(self, site_key: str, item, now) -> tuple[dict | None, str | None]:
        key = {"site_key": site_key, "external_user_id": item.external_user_id}
        existing = self.db.external_identities.find_one(key)
        internal_id = existing.get("internal_user_id") if existing else None
        if not internal_id and item.internal_user_id:
            token = self.db.external_identity_link_tokens.find_one(
                {
                    **key,
                    "internal_user_id": ObjectId(item.internal_user_id),
                    "used_at": None,
                    "expires_at": {"$gt": now},
                }
            )
            digest = hashlib.sha256(str(item.link_token or "").encode()).hexdigest()
            if not token or not hmac.compare_digest(token.get("token_sha256", ""), digest):
                return None, "LINK_VERIFICATION_FAILED"
            internal_id = ObjectId(item.internal_user_id)
            self.db.external_identity_link_tokens.update_one(
                {"_id": token["_id"], "used_at": None}, {"$set": {"used_at": now}}
            )
        if not internal_id:
            return None, "UNLINKED_EXTERNAL_IDENTITY"
        record = self.db.external_identities.find_one_and_update(
            key,
            {
                "$set": {
                    "internal_user_id": internal_id,
                    "username": item.username,
                    "email": item.email,
                    "display_name": item.display_name,
                    "is_active": item.is_active,
                    "updated_at": now,
                },
                "$setOnInsert": {"_id": ObjectId(), "created_at": now},
            },
            upsert=True,
            return_document=True,
        )
        return record, None

    def sync_page(self, payload: MoodleSyncPageRequest) -> dict:
        page_key = self._page_key(payload)
        replay = self.db.moodle_sync_pages.find_one({"page_key": page_key})
        if replay:
            return {**replay["result"], "replayed": True}
        now = _now()
        run = self.db.moodle_sync_runs.find_one({"site_key": payload.site_key})
        if run and run.get("sync_id") == payload.sync_id:
            if run.get("status") != "IN_PROGRESS":
                raise ValueError("Phiên đồng bộ này đã kết thúc")
            if run.get("next_checkpoint") != payload.checkpoint:
                raise ValueError("Checkpoint không nối tiếp trang đồng bộ trước")
            page_number = int(run.get("page_count") or 0) + 1
            if payload.page_number != page_number:
                raise ValueError("Số trang đồng bộ không nối tiếp trang trước")
        else:
            if run and run.get("status") == "IN_PROGRESS":
                raise ValueError("Site đang có một phiên đồng bộ khác chưa hoàn tất")
            page_number = 1
            if payload.page_number != page_number:
                raise ValueError("Phiên đồng bộ phải bắt đầu từ trang 1")
            self.db.moodle_sync_runs.update_one(
                {"site_key": payload.site_key},
                {
                    "$set": {
                        "sync_id": payload.sync_id,
                        "status": "IN_PROGRESS",
                        "next_checkpoint": payload.checkpoint,
                        "page_count": 0,
                        "started_at": now,
                        "completed_at": None,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"_id": ObjectId(), "created_at": now},
                },
                upsert=True,
            )
        resolved = {}
        errors = []
        for item in payload.identities:
            record, error = self._resolve_identity(payload.site_key, item, now)
            if error:
                errors.append({"external_user_id": item.external_user_id, "code": error})
            else:
                resolved[item.external_user_id] = record
        membership_count = 0
        for item in payload.memberships:
            identity = resolved.get(item.external_user_id) or self.db.external_identities.find_one(
                {
                    "site_key": payload.site_key,
                    "external_user_id": item.external_user_id,
                }
            )
            if not identity:
                errors.append({"external_user_id": item.external_user_id, "code": "IDENTITY_NOT_LINKED"})
                continue
            membership_active = bool(item.is_active and identity.get("is_active", True))
            key = {
                "source": "MOODLE",
                "site_key": payload.site_key,
                "external_course_id": item.external_course_id,
                "user_id": identity["internal_user_id"],
                "subject_id": ObjectId(item.subject_id),
            }
            self.db.subject_memberships.find_one_and_update(
                key,
                {
                    "$set": {
                        "status": "ACTIVE" if membership_active else "REVOKED",
                        "external_role": item.external_role,
                        "last_seen_sync_id": payload.sync_id,
                        "revoked_at": None if membership_active else now,
                        "updated_at": now,
                    },
                    "$setOnInsert": {"_id": ObjectId(), "created_at": now},
                },
                upsert=True,
                return_document=True,
            )
            membership_count += 1
        for external_user_id, identity in resolved.items():
            if identity.get("is_active", True):
                continue
            self.db.subject_memberships.update_many(
                {
                    "source": "MOODLE",
                    "site_key": payload.site_key,
                    "user_id": identity["internal_user_id"],
                    "status": "ACTIVE",
                },
                {"$set": {"status": "REVOKED", "revoked_at": now, "updated_at": now}},
            )
        revoked = 0
        completed = bool(payload.is_last_page and not errors)
        if completed:
            result = self.db.subject_memberships.update_many(
                {
                    "source": "MOODLE",
                    "site_key": payload.site_key,
                    "last_seen_sync_id": {"$ne": payload.sync_id},
                    "status": "ACTIVE",
                },
                {"$set": {"status": "REVOKED", "revoked_at": now, "updated_at": now}},
            )
            revoked = result.modified_count
        result = {
            "site_key": payload.site_key,
            "sync_id": payload.sync_id,
            "checkpoint": payload.checkpoint,
            "next_checkpoint": payload.next_checkpoint,
            "page_number": page_number,
            "identity_count": len(resolved),
            "membership_count": membership_count,
            "revoked_count": revoked,
            "errors": errors,
            "completed": completed,
            "replayed": False,
        }
        self.db.moodle_sync_pages.insert_one(
            {
                "_id": ObjectId(),
                "page_key": page_key,
                "site_key": payload.site_key,
                "sync_id": payload.sync_id,
                "checkpoint": payload.checkpoint,
                "next_checkpoint": payload.next_checkpoint,
                "page_number": page_number,
                "is_last_page": payload.is_last_page,
                "result": result,
                "created_at": now,
            }
        )
        self.db.moodle_sync_runs.update_one(
            {
                "site_key": payload.site_key,
                "sync_id": payload.sync_id,
                "status": "IN_PROGRESS",
                "next_checkpoint": payload.checkpoint,
            },
            {
                "$set": {
                    "status": (
                        "COMPLETED"
                        if completed
                        else ("FAILED" if payload.is_last_page and errors else "IN_PROGRESS")
                    ),
                    "next_checkpoint": payload.next_checkpoint,
                    "page_count": page_number,
                    "completed_at": now if payload.is_last_page else None,
                    "updated_at": now,
                    "errors": errors,
                }
            },
        )
        return result

    def issue_link_token(self, payload) -> dict:
        now = _now()
        internal_id = ObjectId(payload.internal_user_id)
        if not self.db.users.find_one({"_id": internal_id, "is_active": True}):
            raise LookupError("Không tìm thấy internal user đang hoạt động")
        raw = secrets.token_urlsafe(32)
        record = {
            "_id": ObjectId(),
            "site_key": payload.site_key,
            "external_user_id": payload.external_user_id,
            "internal_user_id": internal_id,
            "token_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "expires_at": now + timedelta(minutes=payload.expires_in_minutes),
            "used_at": None,
            "created_at": now,
        }
        self.db.external_identity_link_tokens.insert_one(record)
        return {"link_token": raw, "expires_at": record["expires_at"]}
