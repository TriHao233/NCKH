"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN against a test database."""

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from core.config import settings
from core.postgres import postgres_connection
from modules.catalog.postgres_subject_repository import subject_record, subject_records
from modules.catalog.schemas import (
    ChapterPayload, ChapterUpdatePayload, LearningOutcomePayload,
    LearningOutcomeUpdatePayload, SubjectPayload, SubjectUpdatePayload,
)
from modules.catalog.service import CatalogConflictError, CatalogService
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_subject_catalog_permissions_and_cross_module_reads(monkeypatch):
    monkeypatch.setattr(settings, "user_store", "postgres")
    monkeypatch.setattr(settings, "catalog_store", "postgres")
    suffix = uuid4().hex[:10]
    owner = PostgresUserRepository().create({
        "firebase_uid": f"subject-owner-{suffix}",
        "email": f"subject-owner-{suffix}@example.test",
        "display_name": "Test Teacher", "role": "Teacher",
    })
    other = PostgresUserRepository().create({
        "firebase_uid": f"subject-other-{suffix}",
        "email": f"subject-other-{suffix}@example.test",
        "display_name": "Other Teacher", "role": "Teacher",
    })
    viewer = SimpleNamespace(id=owner["_id"], email=owner["email"],
                             role="Teacher", permissions=("catalog.subjects.manage_own",))
    other_viewer = SimpleNamespace(id=other["_id"], email=other["email"],
                                   role="Teacher", permissions=("catalog.subjects.manage_own",))
    # No Mongo subjects collection is present: every subject read must use PG.
    database = SimpleNamespace()
    service = CatalogService(database)
    subject_id = None
    try:
        created = service.create_subject(
            SubjectPayload(subject_code=f" S{suffix} ", subject_name="Học phần thử"), viewer,
        )
        subject_id = created["id"]
        assert created["owner_id"] == str(owner["_id"])
        assert subject_record(database, subject_id)["subject_name"] == "Học phần thử"
        assert len(subject_records(database, ids=[subject_id], active_only=True)) == 1
        with pytest.raises(CatalogConflictError):
            service.create_subject(SubjectPayload(
                subject_code=f"s{suffix}", subject_name="Trùng mã",
            ), viewer)
        with pytest.raises(PermissionError):
            service.update_subject(subject_id, SubjectUpdatePayload(subject_name="Sai"), other_viewer)

        result = service.add_chapter(subject_id, ChapterPayload(
            chapter_code="Ch01", chapter_name="Chương 1",
        ), viewer)
        chapter_id = result["chapters"][0]["id"]
        with pytest.raises(ValueError):
            service.add_chapter(subject_id, ChapterPayload(
                chapter_code="ch01", chapter_name="Trùng chương",
            ), viewer)
        result = service.update_chapter(subject_id, chapter_id,
                                        ChapterUpdatePayload(chapter_name="Chương mới"), viewer)
        assert result["chapters"][0]["chapter_name"] == "Chương mới"

        result = service.add_learning_outcome(subject_id, LearningOutcomePayload(
            clo_code="CLO1", description="Hiểu kiến thức", target_weight=0.8,
        ), viewer)
        clo_id = result["learning_outcomes"][0]["id"]
        result = service.update_learning_outcome(subject_id, clo_id,
            LearningOutcomeUpdatePayload(description="Vận dụng kiến thức", target_weight=0.6), viewer)
        assert result["learning_outcomes"][0]["description"] == "Vận dụng kiến thức"
        assert result["learning_outcomes"][0]["target_weight"] == 0.6
        assert len(service.list_subjects(viewer)) >= 1
        with postgres_connection() as conn:
            count = conn.execute(
                "SELECT count(*) AS n FROM audit_logs WHERE entity_id IN (%s,%s,%s)",
                (subject_id, chapter_id, clo_id),
            ).fetchone()["n"]
        assert count >= 5
        service.deactivate_subject(subject_id, viewer)
        assert subject_record(database, subject_id, active_only=True) is None
        assert subject_record(database, subject_id) is not None
    finally:
        with postgres_connection() as conn:
            with conn.transaction():
                if subject_id:
                    conn.execute("""
                        DELETE FROM audit_logs WHERE entity_id=%s
                            OR entity_id IN (SELECT id FROM subject_chapters WHERE subject_id=%s)
                            OR entity_id IN (SELECT id FROM learning_outcomes WHERE subject_id=%s)
                    """, (subject_id, subject_id, subject_id))
                    conn.execute("DELETE FROM subject_chapters WHERE subject_id=%s", (subject_id,))
                    conn.execute("DELETE FROM learning_outcomes WHERE subject_id=%s", (subject_id,))
                    conn.execute("DELETE FROM subjects WHERE id=%s", (subject_id,))
                conn.execute("DELETE FROM users WHERE id IN (%s,%s)",
                             (str(owner["_id"]), str(other["_id"])))
