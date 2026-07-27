from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from core.audit import record_audit_event
from core.bootstrap import SCHEMA_VERSION
from core.dependencies import CurrentUser
from modules.admin.moodle_schemas import MoodleTargetPayload
from modules.questions.repository import json_safe
from modules.questions.workflow_schemas import MoodlePublicationRequest


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def object_id(value: str | ObjectId, field_name: str = "id") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise ValueError(f"{field_name} không hợp lệ") from exc


def _error_message(error: Any) -> str | None:
    if isinstance(error, dict):
        return error.get("message") or error.get("detail")
    if error:
        return str(error)
    return None


def _publication_status_label(status: str | None, publication_mode: str | None, external_sync: bool | None) -> str:
    if status == "PUBLISHED" and publication_mode == "MOCK":
        return "Đã ghi mô phỏng"
    if status == "PUBLISHED" and external_sync is False:
        return "Đã ghi cục bộ"
    if status == "PUBLISHED":
        return "Đã đồng bộ"
    if status == "FAILED":
        return "Lỗi"
    if status in {"QUEUED", "PROCESSING"}:
        return "Đang xử lý"
    return status or "Chưa rõ"


def _target_public(record: dict | None) -> dict | None:
    if not record:
        return None
    public = json_safe(record)
    public.setdefault("last_check", None)
    return public


def _safe_publication_item(record: dict) -> dict:
    request_payload = record.get("request_payload") or {}
    response_payload = record.get("response_payload") or {}
    target = record.get("target") or {}
    publication_mode = record.get("publication_mode") or response_payload.get("publication_mode")
    if not publication_mode:
        publication_mode = "MOCK" if request_payload.get("mock") else target.get("mode")
    external_sync = record.get("external_sync")
    if external_sync is None:
        external_sync = response_payload.get("external_sync")
    if external_sync is None and publication_mode == "MOCK":
        external_sync = False
    status_detail = record.get("status_detail") or response_payload.get("status_detail")
    if not status_detail and publication_mode == "MOCK" and record.get("status") == "PUBLISHED":
        status_detail = "SIMULATED_LOCAL_RECORD"
    message = response_payload.get("message")
    if not message and publication_mode == "MOCK":
        message = "Mô phỏng Moodle: chỉ ghi nhận publication cục bộ, chưa gửi dữ liệu sang Moodle thật."
    return json_safe(
        {
            "id": record.get("_id"),
            "question_id": record.get("question_id"),
            "question_version_id": record.get("question_version_id"),
            "question_version": record.get("question_version"),
            "publisher_user_id": record.get("publisher_user_id"),
            "target": target,
            "publication_mode": publication_mode,
            "configured_mode": target.get("configured_mode") or target.get("mode"),
            "external_sync": external_sync,
            "status_detail": status_detail,
            "status_label": _publication_status_label(record.get("status"), publication_mode, external_sync),
            "message": message,
            "published_content_hash": record.get("published_content_hash"),
            "status": record.get("status"),
            "attempt_no": record.get("attempt_no"),
            "moodle_question_ref_id": record.get("moodle_question_ref_id"),
            "question_code": request_payload.get("question_code"),
            "export_format": request_payload.get("export_format"),
            "export_formats": response_payload.get("export_formats") or [],
            "mock": request_payload.get("mock"),
            "error_message": _error_message(record.get("error")),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "published_at": record.get("published_at"),
        }
    )


class MoodleTargetService:
    def __init__(self, database):
        self.db = database

    def list_targets(self, *, include_inactive: bool = True) -> dict:
        query = {} if include_inactive else {"is_active": True}
        targets = [
            _target_public(item)
            for item in self.db.moodle_targets.find(query).sort("site_key", 1)
        ]
        return {"items": targets}

    def find_target(self, identifier: str | ObjectId, *, active_only: bool = False) -> dict | None:
        query: dict = {"site_key": str(identifier)}
        try:
            oid = object_id(identifier)
            query = {"$or": [{"site_key": str(identifier)}, {"_id": oid}]}
        except ValueError:
            pass
        if active_only:
            query = {"$and": [query, {"is_active": True}]}
        return self.db.moodle_targets.find_one(query)

    def save_target(self, payload: MoodleTargetPayload, current_user: CurrentUser) -> dict:
        now = utc_now()
        data = payload.model_dump()
        record = self.db.moodle_targets.find_one_and_update(
            {"site_key": payload.site_key},
            {
                "$set": {
                    "schema_version": SCHEMA_VERSION,
                    **data,
                    "updated_by_user_id": current_user.id,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": ObjectId(),
                    "created_by_user_id": current_user.id,
                    "created_at": now,
                    "last_check": None,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        self._audit(current_user, "admin.moodle_target_save", payload.site_key, after=_target_public(record))
        return _target_public(record)

    def deactivate_target(self, identifier: str, current_user: CurrentUser) -> dict:
        now = utc_now()
        target = self.find_target(identifier)
        if not target:
            raise LookupError("Không tìm thấy Moodle target")
        record = self.db.moodle_targets.find_one_and_update(
            {"_id": target["_id"]},
            {"$set": {"is_active": False, "updated_by_user_id": current_user.id, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        self._audit(current_user, "admin.moodle_target_deactivate", target["site_key"], after=_target_public(record))
        return _target_public(record)

    def check_target(self, identifier: str, current_user: CurrentUser) -> dict:
        target = self.find_target(identifier)
        if not target:
            raise LookupError("Không tìm thấy Moodle target")
        started = time.perf_counter()
        check = self._run_check(target, started)
        record = self.db.moodle_targets.find_one_and_update(
            {"_id": target["_id"]},
            {"$set": {"last_check": check, "updated_by_user_id": current_user.id, "updated_at": utc_now()}},
            return_document=ReturnDocument.AFTER,
        )
        self._audit(current_user, "admin.moodle_target_check", target["site_key"], metadata=check)
        return {"target": _target_public(record), "check": json_safe(check)}

    def list_publications(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
        site_key: str | None = None,
        search: str | None = None,
    ) -> dict:
        query: dict = {}
        if status and status != "all":
            query["status"] = status.upper()
        if site_key and site_key != "all":
            query["target.moodle_site_id"] = site_key
        if search:
            query["$or"] = [
                {"moodle_question_ref_id": {"$regex": search, "$options": "i"}},
                {"request_payload.question_code": {"$regex": search, "$options": "i"}},
                {"error.message": {"$regex": search, "$options": "i"}},
            ]
        total = self.db.moodle_publications.count_documents(query)
        items = list(
            self.db.moodle_publications.find(query)
            .sort("created_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return {
            "items": [_safe_publication_item(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "summary": self._publication_summary(site_key),
        }

    def retry_publication(self, publication_id: str, current_user: CurrentUser) -> dict:
        publication = self.db.moodle_publications.find_one(
            {"_id": object_id(publication_id, "publication_id")}
        )
        if not publication:
            raise LookupError("Không tìm thấy Moodle publication")
        if publication.get("status") != "FAILED":
            raise ValueError("Chỉ publication lỗi mới được retry")
        if not publication.get("idempotency_key"):
            raise ValueError("Publication lỗi thiếu idempotency key")

        request_payload = publication.get("request_payload") or {}
        target = publication.get("target") or {}
        export_format = (request_payload.get("export_format") or "BOTH").upper()
        if export_format not in {"GIFT", "XML", "BOTH"}:
            export_format = "BOTH"
        target_id = target.get("target_id") or request_payload.get("target_id")

        payload = MoodlePublicationRequest(
            expected_version=publication.get("question_version"),
            target_id=str(target_id) if target_id else None,
            moodle_site_id=target.get("moodle_site_id") or request_payload.get("moodle_site_id") or "demo-moodle",
            course_id=target.get("course_id") or request_payload.get("course_id") or "ctdl-demo",
            category_id=target.get("category_id") or request_payload.get("category_id") or "qbank-demo",
            export_format=export_format,
            mock=bool(request_payload.get("mock", publication.get("publication_mode") == "MOCK")),
        )

        from modules.questions.workflow_service import QuestionWorkflowService

        result = QuestionWorkflowService(self.db).publish_to_moodle(
            str(publication["question_id"]),
            payload,
            current_user.id,
            current_user.role,
        )
        saved_id = result.get("_id") or result.get("id")
        saved = (
            self.db.moodle_publications.find_one({"_id": object_id(saved_id, "publication_id")})
            if saved_id
            else None
        )
        safe_item = _safe_publication_item(saved or result)
        self._audit(
            current_user,
            "admin.moodle_publication_retry",
            str(publication["_id"]),
            after=safe_item,
            metadata={"previous_status": "FAILED", "attempt_no": safe_item.get("attempt_no")},
            entity_type="moodle_publication",
        )
        return safe_item

    def _run_check(self, target: dict, started: float) -> dict:
        now = utc_now()
        mode = target.get("mode", "MOCK")
        if mode == "MOCK":
            return {
                "ok": True,
                "mode": mode,
                "message": "Mock target sẵn sàng để ghi nhận publication cục bộ",
                "checked_at": now,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

        token_env_var = target.get("token_env_var") or ""
        token = os.getenv(token_env_var)
        if not token:
            return {
                "ok": False,
                "mode": mode,
                "message": f"Chưa cấu hình biến môi trường {token_env_var}",
                "checked_at": now,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

        try:
            response = httpx.get(
                f"{target['base_url'].rstrip('/')}/webservice/rest/server.php",
                params={
                    "wstoken": token,
                    "wsfunction": "core_webservice_get_site_info",
                    "moodlewsrestformat": "json",
                },
                timeout=6,
            )
            payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            if response.status_code >= 400 or payload.get("exception"):
                message = payload.get("message") or f"Moodle trả HTTP {response.status_code}"
                ok = False
            else:
                message = payload.get("sitename") or "Kết nối Moodle thành công"
                ok = True
            return {
                "ok": ok,
                "mode": mode,
                "message": message,
                "http_status": response.status_code,
                "checked_at": now,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "mode": mode,
                "message": str(exc),
                "checked_at": now,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

    def _publication_summary(self, site_key: str | None = None) -> dict:
        match = {} if not site_key or site_key == "all" else {"target.moodle_site_id": site_key}
        simulated_match = {
            **match,
            "$or": [
                {"publication_mode": "MOCK"},
                {"response_payload.publication_mode": "MOCK"},
                {"request_payload.mock": True},
            ],
        }
        return {
            "total": self.db.moodle_publications.count_documents(match),
            "published": self.db.moodle_publications.count_documents({**match, "status": "PUBLISHED"}),
            "simulated": self.db.moodle_publications.count_documents(simulated_match),
            "failed": self.db.moodle_publications.count_documents({**match, "status": "FAILED"}),
            "pending": self.db.moodle_publications.count_documents({**match, "status": {"$in": ["QUEUED", "PROCESSING"]}}),
        }

    @staticmethod
    def _audit(
        current_user: CurrentUser,
        action: str,
        entity_id: str,
        *,
        after: dict | None = None,
        metadata: dict | None = None,
        entity_type: str = "moodle_target",
    ) -> None:
        record_audit_event(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=current_user.id,
            actor_role=current_user.role,
            after=after,
            metadata=metadata or {},
        )
