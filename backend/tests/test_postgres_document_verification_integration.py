"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN on an empty test database."""

import os
from datetime import datetime, timezone

import pytest
from bson import ObjectId

from core.config import settings
from core.postgres import postgres_connection
from db.copy_business_data import projected_rows, upsert
from db.verify_business_data import verify


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


class Collection:
    def __init__(self, records=()):
        self.records = list(records)

    def find(self, *_args):
        return iter(self.records)


class Source:
    def __init__(self, records, chunk_sets, chunks=(), embeddings=()):
        self.records = records
        self.chunk_sets = Collection(chunk_sets)
        self.document_chunks = Collection(chunks)
        self.chunk_embeddings = Collection(embeddings)

    def __getitem__(self, name):
        return Collection(self.records.get(name, ()))


def test_document_content_and_vector_pointer_are_verified():
    now = datetime.now(timezone.utc)
    document_id, job_id, page_id, chunk_set_id, chunk_id = (ObjectId() for _ in range(5))
    document = {
        "_id": document_id, "title": "Source", "original_filename": "source.pdf",
        "status": "READY", "current_version": 1,
        "current_processing": {"chunk_set_id": chunk_set_id},
        "created_at": now, "updated_at": now,
    }
    job = {
        "_id": job_id, "document_id": document_id, "job_type": "OCR",
        "status": "COMPLETED", "created_at": now, "updated_at": now,
    }
    page = {
        "_id": page_id, "document_id": document_id, "ocr_job_id": job_id,
        "unit_number": 1, "page_number": 1, "raw_text": "original",
        "cleaned_text": "clean", "created_at": now,
    }
    source = Source(
        {"documents": [document], "document_jobs": [job], "document_pages": [page]},
        [{"_id": chunk_set_id, "document_id": document_id,
          "source_ocr_job_id": job_id, "status": "COMPLETED"}],
        [{"_id": chunk_id, "document_id": document_id, "chunk_set_id": chunk_set_id}],
        [{"_id": ObjectId(), "chunk_id": chunk_id, "chunk_set_id": chunk_set_id}],
    )
    try:
        with postgres_connection() as conn:
            for name, item in (("documents", document), ("document_jobs", job),
                               ("document_pages", page)):
                for table, row in projected_rows(name, item):
                    upsert(conn, table, row)
        with postgres_connection() as conn:
            assert verify(source, conn) == []
            conn.execute("UPDATE document_pages SET raw_text='changed' WHERE id=%s", (str(page_id),))
        with postgres_connection() as conn:
            assert "document_pages" in verify(source, conn)
            conn.execute("UPDATE document_pages SET raw_text='original' WHERE id=%s", (str(page_id),))
        source.chunk_sets.records[0]["status"] = "FAILED"
        with postgres_connection() as conn:
            assert "vector_document_links" in verify(source, conn)
        source.chunk_sets.records[0]["status"] = "COMPLETED"
        source.chunk_embeddings.records[0]["chunk_id"] = ObjectId()
        with postgres_connection() as conn:
            assert "vector_document_links" in verify(source, conn)
    finally:
        with postgres_connection() as conn:
            conn.execute("DELETE FROM document_pages WHERE id=%s", (str(page_id),))
            conn.execute("DELETE FROM document_jobs WHERE id=%s", (str(job_id),))
            conn.execute("DELETE FROM documents WHERE id=%s", (str(document_id),))
