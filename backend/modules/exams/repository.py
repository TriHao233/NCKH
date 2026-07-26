from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from bson import ObjectId
from pymongo.database import Database

from core.bootstrap import SCHEMA_VERSION
from core.database import mongo_transaction
from modules.exams.schemas import MAX_VARIANTS_PER_EXAM


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def object_id(value: str | ObjectId, field_name: str = "id") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(value)
    except Exception as exc:
        raise ValueError(f"{field_name} không hợp lệ") from exc


def json_safe(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


class ExamRepository(Protocol):
    def create(self, exam: dict) -> dict: ...

    def find(self, exam_id: str | ObjectId) -> dict | None: ...

    def list(self, page: int, page_size: int, created_by_user_id: ObjectId | None) -> tuple[list[dict], int]: ...

    def update(self, exam_id: str | ObjectId, updates: dict) -> dict | None: ...

    def delete(self, exam_id: str | ObjectId) -> bool: ...

    def count_variants(self, exam_id: str | ObjectId) -> int: ...


class ExamVariantRepository(Protocol):
    def create(self, variant: dict) -> dict: ...

    def find(self, variant_id: str | ObjectId) -> dict | None: ...

    def list_by_exam(self, exam_id: str | ObjectId) -> list[dict]: ...

    def delete(self, variant_id: str | ObjectId) -> bool: ...


class MongoExamRepository:
    def __init__(self, database: Database):
        self.db = database

    def create(self, exam: dict) -> dict:
        self.db.exams.insert_one(exam)
        return exam

    def find(self, exam_id: str | ObjectId) -> dict | None:
        return self.db.exams.find_one(
            {"_id": object_id(exam_id, "exam_id"), "schema_version": SCHEMA_VERSION}
        )

    def list(
        self,
        page: int,
        page_size: int,
        created_by_user_id: ObjectId | None,
    ) -> tuple[list[dict], int]:
        match: dict = {"schema_version": SCHEMA_VERSION}
        if created_by_user_id is not None:
            match["created_by_user_id"] = created_by_user_id
        total = self.db.exams.count_documents(match)
        items = list(
            self.db.exams.find(match)
            .sort("updated_at", -1)
            .skip((page - 1) * page_size)
            .limit(page_size)
        )
        return items, total

    def update(self, exam_id: str | ObjectId, updates: dict) -> dict | None:
        updates = dict(updates)
        updates["updated_at"] = utc_now()
        result = self.db.exams.find_one_and_update(
            {"_id": object_id(exam_id, "exam_id"), "schema_version": SCHEMA_VERSION},
            {"$set": updates},
            return_document=True,
        )
        return result

    def delete(self, exam_id: str | ObjectId) -> bool:
        result = self.db.exams.delete_one(
            {"_id": object_id(exam_id, "exam_id"), "schema_version": SCHEMA_VERSION}
        )
        return result.deleted_count == 1

    def count_variants(self, exam_id: str | ObjectId) -> int:
        return self.db.exam_variants.count_documents(
            {"exam_id": object_id(exam_id, "exam_id")}
        )


class MongoExamVariantRepository:
    def __init__(self, database: Database):
        self.db = database

    def create(self, variant: dict) -> dict:
        exam_id = variant["exam_id"]
        with mongo_transaction() as session:
            existing = self.db.exam_variants.count_documents(
                {"exam_id": exam_id}, session=session
            )
            if existing >= MAX_VARIANTS_PER_EXAM:
                raise ValueError(
                    f"Đã đạt tối đa {MAX_VARIANTS_PER_EXAM} mã đề cho kỳ thi này"
                )
            duplicate = self.db.exam_variants.find_one(
                {"exam_id": exam_id, "exam_code": variant["exam_code"]},
                session=session,
            )
            if duplicate:
                raise ValueError("Mã đề này đã tồn tại trong kỳ thi")
            self.db.exam_variants.insert_one(variant, session=session)
        return variant

    def find(self, variant_id: str | ObjectId) -> dict | None:
        return self.db.exam_variants.find_one(
            {"_id": object_id(variant_id, "variant_id")}
        )

    def list_by_exam(self, exam_id: str | ObjectId) -> list[dict]:
        return list(
            self.db.exam_variants.find(
                {"exam_id": object_id(exam_id, "exam_id")}
            ).sort("created_at", 1)
        )

    def delete(self, variant_id: str | ObjectId) -> bool:
        result = self.db.exam_variants.delete_one(
            {"_id": object_id(variant_id, "variant_id")}
        )
        return result.deleted_count == 1
