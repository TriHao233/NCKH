from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

ALLOWED_EVENT_TYPES = {
    "manual_task",
    "review_in_progress", "review_assigned", "review_unassigned_backlog",
    "document_processing_pending",
    "document_ready_for_generation",
    "question_draft_pending",
    "question_revision_required",
    "question_pending_review",
    "question_ready_for_moodle",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def compute_status(raw_status: str, due_date: datetime | None) -> str:
    """raw_status is 'todo' or 'done'. Returns 'todo' | 'done' | 'overdue'."""
    if raw_status == "done":
        return "done"
    due = _as_utc(due_date)
    if due is not None and due < utc_now():
        return "overdue"
    return "todo"


def manual_task_to_event(task: dict) -> dict:
    due_date = task.get("due_date")
    raw_status = task.get("status") or "todo"
    return {
        "id": task["id"],
        "title": task.get("title", ""),
        "description": task.get("description", ""),
        "event_type": "manual_task",
        "source": "manual",
        "related_entity_type": task.get("related_entity_type") or "none",
        "related_entity_id": task.get("related_entity_id"),
        "status": compute_status(raw_status, due_date),
        "priority": task.get("priority") or "medium",
        "date": task.get("created_at"),
        "due_date": due_date,
    }


def document_to_events(document: dict, has_questions: bool) -> list[dict]:
    doc_id = str(document["_id"])
    title = document.get("title") or document.get("original_filename") or "Tài liệu"
    status = document.get("status")
    updated_at = document.get("updated_at") or document.get("created_at")
    events: list[dict] = []

    if status in ("UPLOADED", "PROCESSING"):
        events.append(
            {
                "id": f"doc_pending_{doc_id}",
                "title": f'Tài liệu "{title}" đang xử lý (OCR/chunking)',
                "description": "",
                "event_type": "document_processing_pending",
                "source": "system",
                "related_entity_type": "document",
                "related_entity_id": doc_id,
                "status": "todo",
                "priority": "low",
                "date": updated_at,
                "due_date": None,
            }
        )
    elif status == "READY" and not has_questions:
        events.append(
            {
                "id": f"doc_ready_{doc_id}",
                "title": f'Tài liệu "{title}" đã xử lý xong, chưa sinh câu hỏi',
                "description": "",
                "event_type": "document_ready_for_generation",
                "source": "system",
                "related_entity_type": "document",
                "related_entity_id": doc_id,
                "status": "todo",
                "priority": "medium",
                "date": updated_at,
                "due_date": None,
            }
        )
    return events


_QUESTION_EVENT_MAP = {
    "DRAFT": ("question_draft_pending", "Câu hỏi ở trạng thái nháp", "low"),
    "NEEDS_REVISION": ("question_revision_required", "Câu hỏi bị trả về, cần chỉnh sửa", "high"),
    "PENDING": ("question_pending_review", "Câu hỏi đang chờ duyệt", "medium"),
}


def question_to_events(question: dict) -> list[dict]:
    question_id = str(question["_id"])
    code = question.get("question_code") or question_id
    updated_at = question.get("updated_at") or question.get("created_at")
    review_status = question.get("review_status")
    publication_status = question.get("publication_status")
    events: list[dict] = []

    mapped = _QUESTION_EVENT_MAP.get(review_status)
    if mapped:
        event_type, label, priority = mapped
        events.append(
            {
                "id": f"q_{event_type}_{question_id}",
                "title": f'{label}: "{code}"',
                "description": "",
                "event_type": event_type,
                "source": "system",
                "related_entity_type": "question",
                "related_entity_id": question_id,
                "status": "todo",
                "priority": priority,
                "date": updated_at,
                "due_date": None,
            }
        )
    elif review_status == "APPROVED" and publication_status == "NOT_PUBLISHED":
        events.append(
            {
                "id": f"q_ready_moodle_{question_id}",
                "title": f'Câu hỏi "{code}" đã duyệt, chưa xuất Moodle',
                "description": "",
                "event_type": "question_ready_for_moodle",
                "source": "system",
                "related_entity_type": "question",
                "related_entity_id": question_id,
                "status": "todo",
                "priority": "medium",
                "date": updated_at,
                "due_date": None,
            }
        )
    return events



def review_assignment_to_events(question: dict, *, now, lock_timeout_minutes, assignment_timeout_hours, sla_hours) -> list[dict]:
    """Stable review events for active, pending assignments."""
    assignment = question.get("review_assignment") or {}
    state = assignment.get("status")
    if question.get("review_status") != "PENDING" or question.get("lifecycle_status", "ACTIVE") != "ACTIVE" or state not in {"ASSIGNED", "IN_REVIEW"}:
        return []
    now = _as_utc(now)
    question_id = str(question["_id"])
    code = question.get("question_code") or question_id
    date = _as_utc(assignment.get("claimed_at") if state == "IN_REVIEW" else assignment.get("assigned_at"))
    if state == "IN_REVIEW":
        event_type, title, priority = "review_in_progress", f'Đang giữ câu "{code}"', "high"
        due = _as_utc(assignment.get("lock_expires_at"))
        if due is None and date is not None:
            due = date + timedelta(minutes=lock_timeout_minutes)
    else:
        event_type, title, priority = "review_assigned", f'Được giao duyệt câu "{code}"', "medium"
        due = date + timedelta(hours=assignment_timeout_hours) if date else None
    submitted = _as_utc((question.get("review_submission") or {}).get("submitted_at"))
    sla_breached = submitted is not None and submitted + timedelta(hours=sla_hours) < now
    return [{"id": f"review_{event_type}_{question_id}", "title": title,
             "description": "(quá hạn xử lý)" if sla_breached else "",
             "event_type": event_type, "source": "system", "related_entity_type": "question",
             "related_entity_id": question_id, "status": "overdue" if due and due < now else "todo",
             "priority": "high" if sla_breached else priority, "date": date or now, "due_date": due}]


def review_backlog_event(unassigned_count, now) -> dict | None:
    if unassigned_count <= 0:
        return None
    return {"id": "review_unassigned_backlog", "title": f"{unassigned_count} câu chờ duyệt chưa có người nhận",
            "description": "Mở hàng kiểm duyệt để phân công người duyệt.", "event_type": "review_unassigned_backlog",
            "source": "system", "related_entity_type": "review_queue", "related_entity_id": None,
            "status": "todo", "priority": "high" if unassigned_count >= 20 else "medium",
            "date": now, "due_date": None}

def build_summary(items: list[dict]) -> dict:
    todo = sum(1 for i in items if i["status"] == "todo")
    overdue = sum(1 for i in items if i["status"] == "overdue")
    done = sum(1 for i in items if i["status"] == "done")
    documents_waiting = sum(
        1
        for i in items
        if i["event_type"] in ("document_processing_pending", "document_ready_for_generation")
    )
    questions_need_revision = sum(1 for i in items if i["event_type"] == "question_revision_required")
    questions_pending_review = sum(1 for i in items if i["event_type"] in {"question_pending_review", "review_in_progress", "review_assigned"})
    return {
        "todo": todo,
        "overdue": overdue,
        "done": done,
        "documents_waiting": documents_waiting,
        "questions_need_revision": questions_need_revision,
        "questions_pending_review": questions_pending_review,
    }


def _sort_key(item: dict):
    status_rank = {"overdue": 0, "todo": 1, "done": 2}[item["status"]]
    has_due = 0 if item.get("due_date") else 1
    due = _as_utc(item.get("due_date")) or datetime.max.replace(tzinfo=timezone.utc)
    return (status_rank, has_due, due)


def sort_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=_sort_key)


def filter_items(
    items: list[dict],
    *,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    priority: str | None = None,
) -> list[dict]:
    result = items
    if status and status != "all":
        result = [i for i in result if i["status"] == status]
    if priority and priority != "all":
        result = [i for i in result if i["priority"] == priority]
    if date_from is not None:
        df = _as_utc(date_from)
        result = [
            i
            for i in result
            if (_as_utc(i.get("due_date")) or _as_utc(i.get("date"))) is not None
            and (_as_utc(i.get("due_date")) or _as_utc(i.get("date"))) >= df
        ]
    if date_to is not None:
        dt = _as_utc(date_to)
        result = [
            i
            for i in result
            if (_as_utc(i.get("due_date")) or _as_utc(i.get("date"))) is not None
            and (_as_utc(i.get("due_date")) or _as_utc(i.get("date"))) <= dt
        ]
    return result


def build_calendar(
    *,
    manual_tasks: list[dict],
    documents: list[dict],
    questions: list[dict],
    document_ids_with_questions: set[str],
    review_questions: list[dict] = (),
    review_backlog: int | None = None,
    lock_timeout_minutes: int = 30,
    assignment_timeout_hours: int = 72,
    sla_hours: int = 48,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    priority: str | None = None,
) -> dict:
    items: list[dict] = [manual_task_to_event(task) for task in manual_tasks]
    for document in documents:
        items.extend(
            document_to_events(document, str(document["_id"]) in document_ids_with_questions)
        )
    for question in questions:
        items.extend(question_to_events(question))

    now = utc_now()
    for question in review_questions:
        items.extend(review_assignment_to_events(question, now=now, lock_timeout_minutes=lock_timeout_minutes,
                                                assignment_timeout_hours=assignment_timeout_hours, sla_hours=sla_hours))
    if review_backlog is not None:
        backlog = review_backlog_event(review_backlog, now)
        if backlog:
            items.append(backlog)
    summary = build_summary(items)
    filtered = filter_items(items, date_from=date_from, date_to=date_to, status=status, priority=priority)
    return {"summary": summary, "items": sort_items(filtered)}
