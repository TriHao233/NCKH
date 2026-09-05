import asyncio
import importlib
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from bson import ObjectId

from core.database import get_database, mongo_transaction
from core.bootstrap import SCHEMA_VERSION
from modules.documents.repository import MongoDocumentRepository
from modules.documents.worker import process_document_job_background
from modules.rag.mongodb import start_chunk_set
from scripts.database.backfill_document_processing_revisions import backfill
from modules.generation.mongodb import claim_generation_job
from modules.generation.llm.concurrency import _release_slot, _try_acquire_slot


@unittest.skipUnless(os.getenv("RUN_MONGO_INTEGRATION") == "1", "requires Mongo replica set")
class MongoReplicaSetIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db = get_database()
        self.job_ids: list[ObjectId] = []
        self.document_ids: list[ObjectId] = []
        self.vector_collection_names: list[str] = []

    def tearDown(self):
        if self.job_ids:
            self.db.generation_jobs.delete_many({"_id": {"$in": self.job_ids}})
        self.db.integration_transactions.delete_many({"test_marker": "codex-integration"})
        self.db.llm_slots.delete_many({"provider": "integration-provider"})
        if self.document_ids:
            chunk_sets = list(
                self.db.chunk_sets.find({"document_id": {"$in": self.document_ids}}, {"_id": 1})
            )
            chunk_set_ids = [item["_id"] for item in chunk_sets]
            if chunk_set_ids:
                self.db.chunk_embeddings.delete_many({"chunk_set_id": {"$in": chunk_set_ids}})
                self.db.document_chunks.delete_many({"chunk_set_id": {"$in": chunk_set_ids}})
                self.db.chunk_sets.delete_many({"_id": {"$in": chunk_set_ids}})
            self.db.document_pages.delete_many({"document_id": {"$in": self.document_ids}})
            self.db.document_processing_revisions.delete_many(
                {"document_id": {"$in": self.document_ids}}
            )
            self.db.document_jobs.delete_many({"document_id": {"$in": self.document_ids}})
            self.db.documents.delete_many({"_id": {"$in": self.document_ids}})
        if self.vector_collection_names:
            self.db.vector_collections.delete_many(
                {"collection_name": {"$in": self.vector_collection_names}}
            )

    def test_transaction_rolls_back_on_error(self):
        try:
            with mongo_transaction() as session:
                self.db.integration_transactions.insert_one(
                    {"test_marker": "codex-integration"},
                    session=session,
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass

        self.assertIsNone(
            self.db.integration_transactions.find_one({"test_marker": "codex-integration"})
        )

    def test_only_one_worker_can_claim_a_queued_job(self):
        now = datetime.now(timezone.utc)
        job_id = ObjectId()
        self.job_ids.append(job_id)
        self.db.generation_jobs.insert_one(
            {
                "_id": job_id,
                "request": {},
                "requested_by_user_id": None,
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 3,
                "result": None,
                "metrics": None,
                "error_message": None,
                "created_at": now,
                "updated_at": now,
            }
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda worker: claim_generation_job(str(job_id), worker),
                    ("worker-a", "worker-b"),
                )
            )

        claimed = [result for result in results if result is not None]
        self.assertEqual(len(claimed), 1)
        self.assertIn(claimed[0]["locked_by"], {"worker-a", "worker-b"})

    def test_expired_lease_can_be_reclaimed(self):
        now = datetime.now(timezone.utc)
        job_id = ObjectId()
        self.job_ids.append(job_id)
        self.db.generation_jobs.insert_one(
            {
                "_id": job_id,
                "request": {},
                "requested_by_user_id": None,
                "status": "processing",
                "attempt_count": 1,
                "max_attempts": 3,
                "locked_by": "dead-worker",
                "lease_expires_at": now - timedelta(seconds=1),
                "result": None,
                "metrics": None,
                "error_message": None,
                "created_at": now,
                "updated_at": now,
            }
        )

        claimed = claim_generation_job(str(job_id), "replacement-worker")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["locked_by"], "replacement-worker")
        self.assertEqual(claimed["attempt_count"], 2)

    def test_distributed_llm_slot_allows_only_configured_concurrency(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda holder: _try_acquire_slot("integration-provider", holder, 1),
                    ("holder-a", "holder-b"),
                )
            )

        acquired = [(holder, slot) for holder, slot in zip(("holder-a", "holder-b"), results) if slot]
        self.assertEqual(len(acquired), 1)
        holder, slot_id = acquired[0]
        _release_slot(slot_id, holder)
        self.assertIsNotNone(_try_acquire_slot("integration-provider", "holder-c", 1))

    def test_only_one_worker_can_claim_document_job_with_fencing(self):
        now = datetime.now(timezone.utc)
        job_id = ObjectId()
        document_id = ObjectId()
        self.document_ids.append(document_id)
        self.db.document_jobs.insert_one(
            {
                "_id": job_id,
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "document_version": 1,
                "job_type": "INDEX",
                "attempt_no": 1,
                "status": "QUEUED",
                "queued_at": now,
                "fencing_token": 0,
                "run_attempt": 0,
            }
        )
        repository = MongoDocumentRepository(self.db)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda worker: repository.claim_job(job_id, worker),
                    ("document-worker-a", "document-worker-b"),
                )
            )

        claimed = [result for result in results if result is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["fencing_token"], 1)
        self.assertEqual(claimed[0]["run_attempt"], 1)

    def test_saving_new_processing_revision_keeps_previous_pages(self):
        now = datetime.now(timezone.utc)
        document_id = ObjectId()
        self.document_ids.append(document_id)
        self.db.documents.insert_one(
            {
                "_id": document_id,
                "schema_version": SCHEMA_VERSION,
                "title": "Revision integration",
                "original_filename": "revision.pdf",
                "status": "UPLOADED",
                "current_version": 1,
                "current_processing": {},
                "pipeline_summary": {},
                "artifacts": [],
                "created_at": now,
                "updated_at": now,
                "archived_at": None,
            }
        )
        repository = MongoDocumentRepository(self.db)
        first = repository.create_job(document_id, "OCR", config={})
        repository.save_pages(
            str(document_id),
            str(first["_id"]),
            [{"page_number": 1, "text": "first", "original_text": "first"}],
        )
        second = repository.create_job(document_id, "OCR", config={})
        repository.save_pages(
            str(document_id),
            str(second["_id"]),
            [{"page_number": 1, "text": "second", "original_text": "second"}],
        )

        self.assertEqual(self.db.document_pages.count_documents({"document_id": document_id}), 2)
        self.assertEqual(
            self.db.document_pages.find_one({"ocr_job_id": first["_id"]})["cleaned_text"],
            "first",
        )

    def test_text_pdf_runs_through_durable_worker_and_activates_revision(self):
        import fitz

        repository = MongoDocumentRepository(self.db)
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "source.pdf"
            output_path = Path(directory) / "source.md"
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_text(
                (72, 72),
                "Queue FIFO and linked list source material. " * 8,
            )
            pdf.save(pdf_path)
            pdf.close()
            document = repository.create(
                {
                    "title": "Durable worker integration",
                    "original_filename": "source.pdf",
                    "original_uri": str(pdf_path),
                },
                None,
            )
            self.document_ids.append(document["_id"])
            job = repository.create_job(
                document["_id"],
                "OCR",
                config={
                    "source_format": "pdf",
                    "upload_path": str(pdf_path),
                    "output_path": str(output_path),
                    "document_title": document["title"],
                },
            )

            asyncio.run(process_document_job_background(str(job["_id"]), "integration-worker"))

            completed = repository.find_job(job["_id"])
            refreshed = repository.find_by_id(document["_id"])
            pages = repository.list_pages(document["_id"], document_version=1)
            self.assertEqual(completed["status"], "COMPLETED")
            self.assertEqual(refreshed["pipeline_summary"]["ocr_status"], "COMPLETED")
            self.assertEqual(
                refreshed["current_processing"]["processing_revision_id"],
                job["processing_revision_id"],
            )
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0]["extraction_method"], "TEXT")
            self.assertIn("Queue FIFO", pages[0]["raw_text"])

    def test_processing_revision_backfill_is_idempotent(self):
        now = datetime.now(timezone.utc)
        document_id = ObjectId()
        legacy_job_id = ObjectId()
        self.document_ids.append(document_id)
        self.db.documents.insert_one(
            {
                "_id": document_id,
                "schema_version": SCHEMA_VERSION,
                "title": "Legacy revision",
                "original_filename": "legacy.pdf",
                "status": "PROCESSING",
                "current_version": 1,
                "current_processing": {"ocr_job_id": legacy_job_id},
                "pipeline_summary": {"ocr_status": "COMPLETED"},
                "artifacts": [],
                "created_at": now,
                "updated_at": now,
                "archived_at": None,
            }
        )
        self.db.document_jobs.insert_one(
            {
                "_id": legacy_job_id,
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "document_version": 1,
                "job_type": "OCR",
                "attempt_no": 1,
                "status": "COMPLETED",
                "queued_at": now,
            }
        )
        self.db.document_pages.insert_one(
            {
                "_id": ObjectId(),
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "document_version": 1,
                "ocr_job_id": legacy_job_id,
                "page_number": 1,
                "raw_text": "legacy raw",
                "cleaned_text": "legacy clean",
                "created_at": now,
            }
        )

        dry_run = backfill(apply=False)
        first_apply = backfill(apply=True)
        second_apply = backfill(apply=True)

        self.assertGreaterEqual(dry_run["revisions_to_create"], 1)
        self.assertGreaterEqual(first_apply["revisions_to_create"], 1)
        self.assertEqual(second_apply["revisions_to_create"], 0)
        refreshed = self.db.documents.find_one({"_id": document_id})
        self.assertEqual(
            refreshed["current_processing"]["processing_revision_id"],
            legacy_job_id,
        )

    def test_chunk_candidate_is_verified_before_becoming_active(self):
        now = datetime.now(timezone.utc)
        document_id = ObjectId()
        source_job_id = ObjectId()
        revision_id = ObjectId()
        collection_name = f"integration_chunks_{document_id}"
        self.document_ids.append(document_id)
        self.vector_collection_names.append(collection_name)
        self.db.documents.insert_one(
            {
                "_id": document_id,
                "schema_version": SCHEMA_VERSION,
                "title": "Chunk activation",
                "original_filename": "chunk.pdf",
                "status": "PROCESSING",
                "current_version": 1,
                "current_processing": {
                    "ocr_job_id": source_job_id,
                    "processing_revision_id": revision_id,
                    "chunk_set_id": None,
                    "vector_collection_id": None,
                },
                "pipeline_summary": {
                    "ocr_status": "COMPLETED",
                    "chunk_status": "NOT_STARTED",
                    "index_status": "NOT_STARTED",
                },
                "artifacts": [],
                "created_at": now,
                "updated_at": now,
                "archived_at": None,
            }
        )
        self.db.document_pages.insert_one(
            {
                "_id": ObjectId(),
                "schema_version": SCHEMA_VERSION,
                "document_id": document_id,
                "document_version": 1,
                "ocr_job_id": source_job_id,
                "processing_revision_id": revision_id,
                "revision_no": 1,
                "page_number": 1,
                "raw_text": "Queue FIFO linked list. " * 30,
                "cleaned_text": "# Queue\n\nQueue FIFO linked list. " * 30,
                "created_at": now,
            }
        )
        config = {
            "strategy": "recursive",
            "chunk_size": 500,
            "chunk_overlap": 50,
            "buffer_max_pages": 10,
            "buffer_max_chars": 10_000,
            "max_code_block_lines": 50,
            "dry_run": False,
            "collection_name": collection_name,
        }
        chunk_job_id, chunk_set_id = start_chunk_set(str(document_id), config)

        fake_chromadb_engine = ModuleType("modules.rag.chromadb_engine")
        fake_chromadb_engine.store_chunks = lambda ids, *_args, **_kwargs: len(ids)
        with patch.dict(
            sys.modules,
            {"modules.rag.chromadb_engine": fake_chromadb_engine},
        ):
            chunking = importlib.import_module("modules.rag.chunking")
            with (
                patch.object(chunking, "get_active_keywords", return_value=[]),
                patch.object(
                    chunking,
                    "store_chunks",
                    side_effect=lambda ids, *_args, **_kwargs: len(ids),
                ),
                patch.object(
                    chunking,
                    "export_chunks_to_file",
                    return_value={
                        "json": {"uri": "chunks.json", "sha256": "json-hash"},
                        "markdown": {"uri": "chunks.md", "sha256": "markdown-hash"},
                    },
                ),
            ):
                asyncio.run(process_document_job_background(chunk_job_id, "chunk-worker"))

        job = self.db.document_jobs.find_one({"_id": ObjectId(chunk_job_id)})
        chunk_set = self.db.chunk_sets.find_one({"_id": ObjectId(chunk_set_id)})
        document = self.db.documents.find_one({"_id": document_id})
        self.assertEqual(job["status"], "COMPLETED")
        self.assertTrue(job["stats"]["index_validation"]["verified"])
        self.assertEqual(chunk_set["status"], "ACTIVE")
        self.assertEqual(document["status"], "READY")
        self.assertEqual(document["current_processing"]["chunk_set_id"], ObjectId(chunk_set_id))


if __name__ == "__main__":
    unittest.main()
