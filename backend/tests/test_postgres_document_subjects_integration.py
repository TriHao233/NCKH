"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on a test database."""

import os
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_shadow_copy_preserves_all_document_subjects_and_order():
    now = datetime.now(timezone.utc)
    primary, secondary, document_id = ObjectId(), ObjectId(), ObjectId()
    subjects = [
        {"_id": primary, "subject_code": f"P-{primary}", "subject_name": "Primary"},
        {"_id": secondary, "subject_code": f"S-{secondary}", "subject_name": "Secondary"},
    ]
    document = {
        "_id": document_id, "title": "Multi-subject", "original_filename": "sample.pdf",
        "subject_id": primary, "subject_ids": [primary, secondary, primary],
        "status": "READY", "current_version": 1, "created_at": now, "updated_at": now,
    }
    try:
        with postgres_connection() as conn:
            with conn.transaction():
                for subject in subjects:
                    for table, row in projected_rows("subjects", subject):
                        upsert(conn, table, row)
                for _ in range(2):
                    for table, row in projected_rows("documents", document):
                        upsert(conn, table, row)
            rows = conn.execute(
                "SELECT subject_id, position_no FROM document_subjects "
                "WHERE document_id=%s ORDER BY position_no", (str(document_id),),
            ).fetchall()
            assert rows == [
                {"subject_id": str(primary), "position_no": 0},
                {"subject_id": str(secondary), "position_no": 1},
            ]
    finally:
        with postgres_connection() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM documents WHERE id=%s", (str(document_id),))
                conn.execute("DELETE FROM subjects WHERE id=ANY(%s)",
                             ([str(primary), str(secondary)],))
