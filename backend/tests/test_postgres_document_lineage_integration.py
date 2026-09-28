"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from modules.documents import postgres_repository
from modules.documents.postgres_repository import PostgresDocumentRepository
from modules.rag.lineage import CandidateLineage, LineagePromotionService
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


class VectorCollection:
    def find_one(self, *_args, **_kwargs):
        return {"status": "COMPLETED", "is_active": True}


def test_lineage_promotion_and_rollback_are_atomic_in_postgres(monkeypatch):
    for name in ("user_store", "catalog_store", "document_store"):
        monkeypatch.setattr(settings, name, "postgres")
    monkeypatch.setattr(postgres_repository, "get_database",
                        lambda: SimpleNamespace(documents=object()))
    suffix = uuid4().hex[:12]
    user = PostgresUserRepository().create({
        "firebase_uid": f"lineage-{suffix}",
        "email": f"lineage-{suffix}@example.test",
        "display_name": "Teacher", "role": "Teacher",
    })
    subject_id = ObjectId()
    now = datetime.now(timezone.utc)
    with postgres_connection() as conn:
        for table, row in projected_rows("subjects", {
            "_id": subject_id, "subject_code": f"L-{suffix}",
            "subject_name": "Lineage", "created_at": now, "updated_at": now,
        }):
            upsert(conn, table, row)
    document_id = None
    try:
        repository = PostgresDocumentRepository()
        document = repository.create({
            "title": "Lineage", "original_filename": "lineage.pdf",
            "subject_id": str(subject_id),
        }, user["_id"])
        document_id = document["_id"]
        ocr_a = repository.create_job(document_id, "OCR")
        repository.update_job(ocr_a["_id"], "COMPLETED")
        chunk_a = repository.create_job(document_id, "CHUNK")
        set_a, vector_a = ObjectId(), ObjectId()
        assert repository.finish_chunk_job(
            document_id, chunk_a["_id"], set_a, ocr_a["_id"], vector_a,
            total_chunks=1, stats={}, dry_run=False,
        ) is True

        ocr_b = repository.create_job(document_id, "OCR")
        repository.update_job(ocr_b["_id"], "COMPLETED")
        chunk_b = repository.create_job(document_id, "CHUNK")
        set_b, vector_b = ObjectId(), ObjectId()
        repository.finish_chunk_job(
            document_id, chunk_b["_id"], set_b, ocr_b["_id"], vector_b,
            total_chunks=2, stats={}, dry_run=False,
        )
        pending = repository.find_by_id(document_id)["pending_processing"]
        assert pending["chunk_set_id"] == set_b

        candidate = CandidateLineage(str(document_id), str(ocr_b["_id"]),
                                     str(set_b), str(vector_b))
        validator = SimpleNamespace(validate=lambda *_args, **_kwargs: {
            "status": "passed", "errors": [], "warnings": [], "metrics": {},
        })
        vectors = SimpleNamespace(chunk_sets=VectorCollection(),
                                  vector_collections=VectorCollection())
        service = LineagePromotionService(vectors, validator)
        promoted = service.promote(
            candidate, smoke_queries=["lineage"], actor="admin",
            reason="verified", confirmation=service.confirmation_token(candidate),
        )
        active = repository.find_by_id(document_id)
        assert active["current_processing"]["chunk_set_id"] == set_b
        assert active["pending_processing"] == {}
        with pytest.raises(RuntimeError, match="concurrently"):
            repository.promote_lineage(
                document_id, {"ocr_job_id": ocr_b["_id"], "chunk_set_id": set_b,
                              "vector_collection_id": vector_b},
                operation_id=str(uuid4()), validation={"status": "passed"},
                expected_current={"ocr_job_id": ocr_a["_id"],
                                  "chunk_set_id": set_a,
                                  "vector_collection_id": vector_a},
                expected_version=1,
                actor="admin", reason="duplicate",
            )
        with postgres_connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM document_lineage_events "
                                "WHERE document_id=%s AND event_type='PROMOTE'",
                                (str(document_id),)).fetchone()["n"] == 1
            event_payload = conn.execute(
                "SELECT payload FROM document_lineage_events WHERE operation_id=%s",
                (promoted["operation_id"],),
            ).fetchone()["payload"]
        assert event_payload["actor"] == "admin"
        assert event_payload["to_snapshot"]["chunk_set_id"] == str(set_b)

        restored = service.rollback(promoted["operation_id"], actor="admin",
                                    reason="restore previous")
        assert restored["restored_snapshot"]["chunk_set_id"] == set_a
        assert repository.find_by_id(document_id)["current_processing"]["chunk_set_id"] == set_a
        with pytest.raises(LookupError):
            service.rollback(promoted["operation_id"], actor="admin", reason="again")
        with postgres_connection() as conn:
            assert conn.execute("SELECT count(*) AS n FROM audit_logs "
                                "WHERE entity_id=%s AND action IN "
                                "('document.lineage_promote','document.lineage_rollback')",
                                (str(document_id),)).fetchone()["n"] == 2

        legacy_promotion_id, legacy_rollback_id = str(uuid4()), str(uuid4())
        legacy_promotion = {
            "_id": ObjectId(), "operation_id": legacy_promotion_id,
            "event_type": "PROMOTE", "document_id": document_id,
            "actor": "admin", "reason": "legacy promotion",
            "from_snapshot": {"ocr_job_id": ocr_a["_id"], "chunk_set_id": set_a,
                              "vector_collection_id": vector_a},
            "to_snapshot": {"ocr_job_id": ocr_b["_id"], "chunk_set_id": set_b,
                            "vector_collection_id": vector_b},
            "validation": {"status": "passed"}, "rollback_available": False,
            "created_at": now,
        }
        legacy_rollback = {
            "_id": ObjectId(), "operation_id": legacy_rollback_id,
            "event_type": "ROLLBACK", "document_id": document_id,
            "actor": "admin", "reason": "legacy rollback",
            "promotion_operation_id": legacy_promotion_id,
            "from_snapshot": legacy_promotion["to_snapshot"],
            "to_snapshot": legacy_promotion["from_snapshot"],
            "created_at": now,
        }
        with postgres_connection() as conn:
            # The deferred FK permits historical events to arrive out of order.
            for event in (legacy_rollback, legacy_promotion):
                for table, row in projected_rows("pipeline_lineage_events", event):
                    upsert(conn, table, row)
        with postgres_connection() as conn:
            copied = conn.execute(
                """SELECT event_type, promotion_operation_id, payload
                   FROM document_lineage_events WHERE operation_id=%s""",
                (legacy_rollback_id,),
            ).fetchone()
        assert copied["event_type"] == "ROLLBACK"
        assert copied["promotion_operation_id"] == legacy_promotion_id
        assert copied["payload"]["to_snapshot"]["chunk_set_id"] == str(set_a)
    finally:
        with postgres_connection() as conn:
            if document_id:
                conn.execute("DELETE FROM audit_logs WHERE entity_id=%s", (str(document_id),))
                conn.execute("DELETE FROM document_lineage_events WHERE document_id=%s",
                             (str(document_id),))
                conn.execute("DELETE FROM document_jobs WHERE document_id=%s",
                             (str(document_id),))
                conn.execute("DELETE FROM documents WHERE id=%s", (str(document_id),))
            conn.execute("DELETE FROM subjects WHERE id=%s", (str(subject_id),))
            conn.execute("DELETE FROM users WHERE id=%s", (str(user["_id"]),))
