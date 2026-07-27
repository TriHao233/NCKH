from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from bson import ObjectId
from firebase_admin import auth

from core.audit import record_audit_event
from core.database import get_rag_db
from core.dependencies import CurrentUser
from modules.auth.session_repository import (
    FirebaseSessionRepository,
    get_firebase_session_repository,
)
from modules.users import calendar_service
from modules.users.repository import MongoUserRepository, UserRepository, serialize_user
from modules.users.schemas import (
    PublicRegisterRequest,
    GenerationPresetPayload,
    TaskCalendarPayload,
    TaskCalendarUpdateRequest,
    UserAdminUpdateRequest,
    UserCreateRequest,
    UserSelfUpdateRequest,
)

MAX_GENERATION_PRESETS = 12
MAX_TASK_CALENDAR_ITEMS = 500


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IdentityGateway(Protocol):
    def create_user(self, *, email: str, password: str, display_name: str): ...

    def update_user(self, firebase_uid: str, **fields): ...

    def set_user_disabled(self, firebase_uid: str, disabled: bool): ...

    def delete_user(self, firebase_uid: str): ...


class FirebaseIdentityGateway:
    def create_user(self, *, email: str, password: str, display_name: str):
        return auth.create_user(email=email, password=password, display_name=display_name)

    def update_user(self, firebase_uid: str, **fields):
        return auth.update_user(firebase_uid, **fields)

    def set_user_disabled(self, firebase_uid: str, disabled: bool):
        return auth.update_user(firebase_uid, disabled=disabled)

    def delete_user(self, firebase_uid: str):
        return auth.delete_user(firebase_uid)


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        identity: IdentityGateway,
        sessions: FirebaseSessionRepository,
    ):
        self.repository = repository
        self.identity = identity
        self.sessions = sessions

    def sync_from_claims(self, claims: dict) -> dict:
        return serialize_user(self.repository.sync_identity(claims))

    def register_teacher(self, payload: PublicRegisterRequest) -> dict:
        firebase_user = self.identity.create_user(
            email=str(payload.email),
            password=payload.password,
            display_name=payload.full_name,
        )
        user = None
        try:
            user = self.repository.create(
                {
                    "firebase_uid": firebase_user.uid,
                    "email": str(payload.email),
                    "display_name": payload.full_name,
                    "role": "Teacher",
                }
            )
            self.sessions.upsert(firebase_user.uid, None)
        except Exception:
            if user:
                self.repository.delete_by_id(user["_id"])
            self.identity.delete_user(firebase_user.uid)
            raise
        return serialize_user(user)

    def create_user(self, payload: UserCreateRequest) -> dict:
        firebase_user = self.identity.create_user(
            email=str(payload.email),
            password=payload.password,
            display_name=payload.display_name,
        )
        user = None
        try:
            user = self.repository.create(
                {
                    "firebase_uid": firebase_user.uid,
                    "email": str(payload.email),
                    "display_name": payload.display_name,
                    "role": payload.role.value,
                    "profile": payload.profile.model_dump(),
                }
            )
            self.sessions.upsert(firebase_user.uid, None)
        except Exception:
            if user:
                self.repository.delete_by_id(user["_id"])
            self.identity.delete_user(firebase_user.uid)
            raise
        return serialize_user(user)

    def get(self, user_id: str) -> dict | None:
        user = self.repository.find_by_id(user_id)
        return serialize_user(user) if user else None

    def get_stats(self, user_id: str) -> dict | None:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        return self.repository.get_stats(user_id)

    def get_by_firebase_uid(self, firebase_uid: str) -> dict | None:
        user = self.repository.find_by_firebase_uid(firebase_uid)
        return serialize_user(user) if user else None

    def list(self, page: int, page_size: int, role: str | None, search: str | None) -> dict:
        records, total = self.repository.list(page, page_size, role, search)
        return {
            "items": [serialize_user(item) for item in records],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_self(self, user_id: str, payload: UserSelfUpdateRequest) -> dict | None:
        fields: dict = {}
        if payload.display_name is not None:
            fields["display_name"] = payload.display_name
        if payload.profile is not None:
            fields["profile"] = payload.profile.model_dump()
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        if payload.display_name is not None:
            self.identity.update_user(user["firebase_uid"], display_name=payload.display_name)
        updated = self.repository.update(user_id, fields)
        return serialize_user(updated) if updated else None

    @staticmethod
    def _generation_presets(user: dict) -> list[dict]:
        presets = user.get("generation_presets") or []
        return presets if isinstance(presets, list) else []

    def list_generation_presets(self, user_id: str) -> dict | None:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        return {"items": self._generation_presets(user)}

    def save_generation_preset(
        self,
        user_id: str,
        payload: GenerationPresetPayload,
    ) -> dict | None:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        now = utc_now()
        preset = {
            "id": str(ObjectId()),
            **payload.model_dump(),
            "createdAt": now,
            "updatedAt": now,
        }
        existing = self._generation_presets(user)
        next_presets = [preset, *existing][:MAX_GENERATION_PRESETS]
        updated = self.repository.update(
            user_id,
            {"generation_presets": next_presets},
        )
        if not updated:
            return None
        return preset

    def delete_generation_preset(self, user_id: str, preset_id: str) -> bool | None:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        existing = self._generation_presets(user)
        next_presets = [preset for preset in existing if preset.get("id") != preset_id]
        if len(next_presets) == len(existing):
            return False
        updated = self.repository.update(
            user_id,
            {"generation_presets": next_presets},
        )
        return updated is not None

    @staticmethod
    def _task_calendar(user: dict) -> list[dict]:
        tasks = user.get("task_calendar") or []
        return tasks if isinstance(tasks, list) else []

    def get_calendar(
        self,
        user_id: str,
        *,
        date_from=None,
        date_to=None,
        status: str | None = None,
        priority: str | None = None,
    ) -> dict | None:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        manual_tasks = self._task_calendar(user)
        documents = self.repository.get_calendar_documents(user_id)
        questions = self.repository.get_calendar_questions(user_id)
        document_ids = [document["_id"] for document in documents]
        document_ids_with_questions = self.repository.get_document_ids_with_questions(document_ids)
        return calendar_service.build_calendar(
            manual_tasks=manual_tasks,
            documents=documents,
            questions=questions,
            document_ids_with_questions=document_ids_with_questions,
            date_from=date_from,
            date_to=date_to,
            status=status,
            priority=priority,
        )

    def create_task(self, user_id: str, payload: TaskCalendarPayload) -> dict | None:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        now = utc_now()
        task = {
            "id": str(ObjectId()),
            **payload.model_dump(),
            "status": "todo",
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        existing = self._task_calendar(user)
        next_tasks = [task, *existing][:MAX_TASK_CALENDAR_ITEMS]
        updated = self.repository.update(user_id, {"task_calendar": next_tasks})
        if not updated:
            return None
        return task

    def update_task(
        self,
        user_id: str,
        task_id: str,
        payload: TaskCalendarUpdateRequest,
    ) -> dict | None | bool:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        existing = self._task_calendar(user)
        target = next((task for task in existing if task.get("id") == task_id), None)
        if target is None:
            return False
        fields = payload.model_dump(exclude_unset=True)
        now = utc_now()
        updated_task = {**target, **fields, "updated_at": now}
        if fields.get("status") == "done" and target.get("status") != "done":
            updated_task["completed_at"] = now
        elif fields.get("status") == "todo":
            updated_task["completed_at"] = None
        next_tasks = [updated_task if task.get("id") == task_id else task for task in existing]
        updated = self.repository.update(user_id, {"task_calendar": next_tasks})
        if not updated:
            return None
        return updated_task

    def delete_task(self, user_id: str, task_id: str) -> bool | None:
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        existing = self._task_calendar(user)
        next_tasks = [task for task in existing if task.get("id") != task_id]
        if len(next_tasks) == len(existing):
            return False
        updated = self.repository.update(user_id, {"task_calendar": next_tasks})
        return updated is not None

    def _ensure_admin_floor(self, user: dict, fields: dict) -> None:
        if user.get("role") != "Admin" or not user.get("is_active", True):
            return
        next_role = fields.get("role", user.get("role"))
        next_active = fields.get("is_active", user.get("is_active", True))
        if next_role == "Admin" and next_active is True:
            return
        if self.repository.count_active_admins() <= 1:
            raise ValueError("Hệ thống phải còn ít nhất một Admin active")

    @staticmethod
    def _user_audit_snapshot(user: dict | None) -> dict:
        if not user:
            return {}
        return {
            "role": user.get("role"),
            "is_active": user.get("is_active", True),
        }

    def update_admin(
        self,
        user_id: str,
        payload: UserAdminUpdateRequest,
        actor: CurrentUser | None = None,
    ) -> dict | None:
        fields = payload.model_dump(exclude_none=True)
        profile = fields.get("profile")
        if profile is not None and hasattr(profile, "model_dump"):
            fields["profile"] = profile.model_dump()
        role = fields.get("role")
        if role is not None:
            fields["role"] = role.value if hasattr(role, "value") else role
        user = self.repository.find_by_id(user_id)
        if not user:
            return None
        self._ensure_admin_floor(user, fields)
        before = self._user_audit_snapshot(user)
        if payload.display_name is not None:
            self.identity.update_user(user["firebase_uid"], display_name=payload.display_name)
        if payload.is_active is not None:
            self.identity.set_user_disabled(user["firebase_uid"], not payload.is_active)
        updated = self.repository.update(user_id, fields)
        if updated and payload.is_active is False:
            self.sessions.upsert(user["firebase_uid"], None)
        if updated and {"role", "is_active"} & set(fields):
            record_audit_event(
                action="user.admin_update",
                entity_type="user",
                entity_id=user["_id"],
                actor_user_id=actor.id if actor else None,
                actor_role=actor.role if actor else None,
                before=before,
                after=self._user_audit_snapshot(updated),
                metadata={"changed_fields": sorted({"role", "is_active"} & set(fields))},
            )
        return serialize_user(updated) if updated else None

    def deactivate(self, user_id: str, actor: CurrentUser | None = None) -> bool:
        user = self.repository.find_by_id(user_id)
        if not user:
            return False
        self._ensure_admin_floor(user, {"is_active": False})
        before = self._user_audit_snapshot(user)
        self.identity.set_user_disabled(user["firebase_uid"], True)
        updated = self.repository.update(user_id, {"is_active": False})
        if updated:
            self.sessions.upsert(user["firebase_uid"], None)
            record_audit_event(
                action="user.deactivate",
                entity_type="user",
                entity_id=user["_id"],
                actor_user_id=actor.id if actor else None,
                actor_role=actor.role if actor else None,
                before=before,
                after=self._user_audit_snapshot(updated),
            )
        return updated is not None


def get_user_service() -> UserService:
    return UserService(
        MongoUserRepository(get_rag_db()),
        FirebaseIdentityGateway(),
        get_firebase_session_repository(),
    )
