from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.database import Database

from core.bootstrap import SCHEMA_VERSION
from core.dependencies import effective_permissions


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def object_id(value: str | ObjectId) -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except Exception as exc:
        raise ValueError("ID người dùng không hợp lệ") from exc


def serialize_user(user: dict) -> dict:
    # Some documents predate the nested `profile` schema and still carry
    # school/address/avatar as top-level legacy fields (see
    # scripts/database/migrate_v2.py). Fall back to those so already-stored
    # data isn't silently dropped for users that haven't been migrated.
    profile = user.get("profile") or {}
    profile = {
        "school": profile.get("school") or user.get("School", ""),
        "address": profile.get("address") or user.get("Địa Chỉ", ""),
        "avatar": profile.get("avatar") or user.get("avatar", ""),
    }
    return {
        "id": str(user["_id"]),
        "firebase_uid": user["firebase_uid"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "permissions": list(effective_permissions(user)),
        "profile": profile,
        "is_active": user.get("is_active", True),
        "created_at": user["created_at"],
        "updated_at": user["updated_at"],
    }


class UserRepository(Protocol):
    def find_by_id(self, user_id: str | ObjectId) -> dict | None: ...

    def find_by_firebase_uid(self, firebase_uid: str) -> dict | None: ...

    def create(self, data: dict) -> dict: ...

    def sync_identity(self, claims: dict) -> dict: ...

    def list(self, page: int, page_size: int, role: str | None, search: str | None) -> tuple[list[dict], int]: ...

    def count_by_role(self, search: str | None = None) -> dict[str, int]: ...

    def update(self, user_id: str | ObjectId, fields: dict) -> dict | None: ...

    def count_active_admins(self) -> int: ...

    def delete_by_id(self, user_id: str | ObjectId) -> None: ...

    def get_stats(self, user_id: str | ObjectId) -> dict: ...


class MongoUserRepository:
    def __init__(self, database: Database):
        self.db = database
        self.collection = database.users

    def get_stats(self, user_id: str | ObjectId) -> dict:
        oid = object_id(user_id)
        documents_count = self.db.documents.count_documents(
            {"uploaded_by_user_id": oid, "status": {"$ne": "ARCHIVED"}}
        )
        questions_count = self.db.questions.count_documents(
            {"created_by_user_id": oid, "lifecycle_status": {"$ne": "ARCHIVED"}}
        )
        pending_questions_count = self.db.questions.count_documents(
            {"created_by_user_id": oid, "review_status": "PENDING"}
        )
        return {
            "documents_count": documents_count,
            "questions_count": questions_count,
            "pending_questions_count": pending_questions_count,
        }

    def find_by_id(self, user_id: str | ObjectId) -> dict | None:
        return self.collection.find_one({"_id": object_id(user_id)})

    def find_by_firebase_uid(self, firebase_uid: str) -> dict | None:
        return self.collection.find_one({"firebase_uid": firebase_uid})

    def create(self, data: dict) -> dict:
        now = utc_now()
        record = {
            "schema_version": SCHEMA_VERSION,
            "firebase_uid": data["firebase_uid"],
            "email": data["email"].lower(),
            "display_name": data["display_name"],
            "role": data.get("role", "Teacher"),
            "permissions": data.get("permissions") or [],
            "profile": data.get("profile") or {"school": "", "address": "", "avatar": ""},
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        result = self.collection.insert_one(record)
        return self.collection.find_one({"_id": result.inserted_id})

    def sync_identity(self, claims: dict) -> dict:
        now = utc_now()
        firebase_uid = claims["uid"]
        email = (claims.get("email") or f"{firebase_uid}@firebase.local").lower()
        display_name = claims.get("name") or email.split("@", 1)[0]
        avatar = claims.get("picture") or ""
        profile_defaults = {"school": "", "address": "", "avatar": ""}
        profile_overlay = {"avatar": avatar} if avatar else {}
        return self.collection.find_one_and_update(
            {"firebase_uid": firebase_uid},
            [
                {
                    "$set": {
                        "schema_version": {"$ifNull": ["$schema_version", SCHEMA_VERSION]},
                        "firebase_uid": firebase_uid,
                        "email": email,
                        "display_name": {"$ifNull": ["$display_name", display_name]},
                        "role": {"$ifNull": ["$role", "Teacher"]},
                        "permissions": {"$ifNull": ["$permissions", []]},
                        "profile": {
                            "$mergeObjects": [
                                profile_defaults,
                                {"$ifNull": ["$profile", {}]},
                                profile_overlay,
                            ]
                        },
                        "is_active": {"$ifNull": ["$is_active", True]},
                        "created_at": {"$ifNull": ["$created_at", now]},
                        "updated_at": now,
                    }
                }
            ],
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    @staticmethod
    def _search_filter(search: str | None) -> dict:
        term = re.escape((search or "").strip())
        if not term:
            return {}
        return {
            "$or": [
                {"display_name": {"$regex": term, "$options": "i"}},
                {"email": {"$regex": term, "$options": "i"}},
            ]
        }

    def list(
        self,
        page: int,
        page_size: int,
        role: str | None,
        search: str | None,
    ) -> tuple[list[dict], int]:
        query: dict = self._search_filter(search)
        if role:
            query["role"] = role
        total = self.collection.count_documents(query)
        records = list(
            self.collection.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return records, total

    def count_by_role(self, search: str | None = None) -> dict[str, int]:
        base_query = self._search_filter(search)
        return {
            "all": self.collection.count_documents(base_query),
            **{
                role: self.collection.count_documents({**base_query, "role": role})
                for role in ("Admin", "Teacher", "Reviewer")
            },
        }

    def update(self, user_id: str | ObjectId, fields: dict) -> dict | None:
        fields = {**fields, "updated_at": utc_now()}
        return self.collection.find_one_and_update(
            {"_id": object_id(user_id)},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )

    def count_active_admins(self) -> int:
        return self.collection.count_documents({"role": "Admin", "is_active": True})

    def delete_by_id(self, user_id: str | ObjectId) -> None:
        self.collection.delete_one({"_id": object_id(user_id)})

    def get_calendar_documents(self, user_id: str | ObjectId) -> list[dict]:
        oid = object_id(user_id)
        return list(
            self.db.documents.find(
                {"uploaded_by_user_id": oid, "status": {"$ne": "ARCHIVED"}}
            )
        )

    def get_calendar_questions(self, user_id: str | ObjectId) -> list[dict]:
        oid = object_id(user_id)
        return list(
            self.db.questions.find(
                {"created_by_user_id": oid, "lifecycle_status": {"$ne": "ARCHIVED"}}
            )
        )

    def get_document_ids_with_questions(self, document_ids: list[ObjectId]) -> set[str]:
        if not document_ids:
            return set()
        cursor = self.db.questions.find(
            {"document_id": {"$in": document_ids}, "lifecycle_status": {"$ne": "ARCHIVED"}},
            {"document_id": 1},
        )
        return {str(doc["document_id"]) for doc in cursor if doc.get("document_id")}
