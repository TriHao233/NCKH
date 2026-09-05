from __future__ import annotations

from collections.abc import Iterable

from bson import ObjectId


ACTIVE_MEMBERSHIP_STATUSES = {"ACTIVE"}


def _as_object_id(value) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if value and ObjectId.is_valid(str(value)):
        return ObjectId(str(value))
    return None


def active_subject_ids(database, user_id) -> tuple[ObjectId, ...]:
    """Resolve active subject scope; absence is deny-by-default."""

    collection = getattr(database, "subject_memberships", None) if database is not None else None
    user_oid = _as_object_id(user_id)
    if collection is None or user_oid is None:
        return ()
    records: Iterable[dict] = collection.find(
        {"user_id": user_oid, "status": {"$in": sorted(ACTIVE_MEMBERSHIP_STATUSES)}},
        {"subject_id": 1},
    )
    resolved = []
    for record in records:
        subject_id = _as_object_id(record.get("subject_id"))
        if subject_id is not None and subject_id not in resolved:
            resolved.append(subject_id)
    subjects = getattr(database, "subjects", None)
    if subjects is not None:
        for record in subjects.find(
            {"owner_id": user_oid, "is_active": True}, {"_id": 1}
        ):
            subject_id = _as_object_id(record.get("_id"))
            if subject_id is not None and subject_id not in resolved:
                resolved.append(subject_id)
    return tuple(resolved)


def has_subject_access(database, user_id, subject_id) -> bool:
    subject_oid = _as_object_id(subject_id)
    if subject_oid is None:
        return False
    subjects = getattr(database, "subjects", None) if database is not None else None
    user_oid = _as_object_id(user_id)
    if subjects is not None and user_oid is not None:
        owned = subjects.find_one(
            {"_id": subject_oid, "owner_id": user_oid, "is_active": True}, {"_id": 1}
        )
        if owned:
            return True
    return subject_oid in set(active_subject_ids(database, user_id))


def subject_id_from_record(record: dict | None, version: dict | None = None):
    record = record or {}
    subject_id = record.get("subject_id")
    if subject_id:
        return subject_id
    classification = (version or {}).get("classification") or {}
    subject = classification.get("subject") or {}
    return subject.get("id") if isinstance(subject, dict) else subject


def is_explicitly_shared(record: dict | None, user_id) -> bool:
    if not record:
        return False
    user_oid = _as_object_id(user_id)
    return user_oid is not None and user_oid in set(record.get("shared_with_user_ids") or [])


def is_subject_shared_with_member(
    database,
    record: dict | None,
    user_id,
    *,
    version: dict | None = None,
) -> bool:
    if not record or record.get("shared_scope") != "SUBJECT":
        return False
    return has_subject_access(database, user_id, subject_id_from_record(record, version))
