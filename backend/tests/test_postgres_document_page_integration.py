"""Verify shadow copying non-PDF source units into PostgreSQL."""

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


def test_docx_unit_without_page_number_survives_shadow_copy():
    now = datetime.now(timezone.utc)
    document_id, job_id, page_id = ObjectId(), ObjectId(), ObjectId()
    location = {"kind": "paragraph", "index": 3}
    document = {
        "_id": document_id, "title": "DOCX", "original_filename": "test.docx",
        "status": "OCR_PROCESSING", "current_version": 2,
        "created_at": now, "updated_at": now,
    }
    job = {
        "_id": job_id, "document_id": document_id, "job_type": "OCR",
        "status": "COMPLETED", "document_version": 2,
        "created_at": now, "updated_at": now,
    }
    page = {
        "_id": page_id, "document_id": document_id, "ocr_job_id": job_id,
        "document_version": 2, "unit_number": 4, "page_number": None,
        "source_location": location, "raw_text": "Original",
        "cleaned_text": "Clean", "created_at": now,
    }

    with postgres_connection() as conn:
        with conn.transaction():
            for name, item in (("documents", document), ("document_jobs", job),
                               ("document_pages", page)):
                for table, row in projected_rows(name, item):
                    upsert(conn, table, row)
            stored = conn.execute(
                """SELECT document_id, ocr_job_id, version, unit_number,
                          page_number, source_location, raw_text, clean_text
                   FROM document_pages WHERE id=%s""",
                (str(page_id),),
            ).fetchone()
            assert stored == {
                "document_id": str(document_id), "ocr_job_id": str(job_id),
                "version": 2, "unit_number": 4, "page_number": None,
                "source_location": location, "raw_text": "Original", "clean_text": "Clean",
            }
            conn.execute("DELETE FROM document_pages WHERE id=%s", (str(page_id),))
            conn.execute("DELETE FROM document_jobs WHERE id=%s", (str(job_id),))
            conn.execute("DELETE FROM documents WHERE id=%s", (str(document_id),))
