"""Reprocess one existing document into a pending OCR/RAG lineage.

The command is read-only by default. Supplying ``--apply`` creates a new OCR
attempt, pages, processing artifacts, chunk set, chunks, embeddings, and a
dedicated vector collection for the same document. It never promotes a
candidate and never changes the active lineage.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bson import ObjectId

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.config import resolve_path, settings
from core.database import get_database
from modules.documents.repository import MongoDocumentRepository, object_id
from modules.documents.retention import deduplicate_artifact_file


ACTIVE_JOB_STATUSES = {"QUEUED", "PROCESSING"}
ORIGINAL_ARTIFACT_TYPES = {
    "ORIGINAL_PDF",
    "ORIGINAL_DOCX",
    "ORIGINAL_DOC",
    "ORIGINAL_MARKDOWN",
    "ORIGINAL_TEXT",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ReprocessRequest:
    document_id: str
    collection_name: str
    expected_source_sha256: str
    expected_active_ocr_job_id: str
    expected_active_chunk_set_id: str
    expected_active_vector_collection_id: str
    apply: bool = False

    @property
    def expected_active(self) -> dict[str, str]:
        return {
            "ocr_job_id": self.expected_active_ocr_job_id,
            "chunk_set_id": self.expected_active_chunk_set_id,
            "vector_collection_id": self.expected_active_vector_collection_id,
        }


@dataclass(frozen=True)
class ReprocessPlan:
    request: ReprocessRequest
    document: dict
    source_artifact: dict
    source_path: Path
    source_sha256: str
    active_snapshot: dict[str, str]
    active_state: dict

    def public_dict(self) -> dict:
        return {
            "mode": "apply" if self.request.apply else "read_only",
            "document_id": self.request.document_id,
            "document_version": self.document.get("current_version"),
            "source_file": str(self.source_path),
            "source_sha256": self.source_sha256,
            "collection_name": self.request.collection_name,
            "active_snapshot": self.active_snapshot,
            "preconditions": "passed",
            "mutation_scope": (
                "new OCR job/pages/artifacts, chunk job/set/chunks/embeddings, "
                "one new vector collection, generated chunk export/cache entries, "
                "and pending_processing only"
            ),
            "promotion_allowed": False,
        }


def parse_args(argv: list[str] | None = None) -> ReprocessRequest:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-active-ocr-job-id", required=True)
    parser.add_argument("--expected-active-chunk-set-id", required=True)
    parser.add_argument("--expected-active-vector-collection-id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    return ReprocessRequest(
        document_id=args.document_id,
        collection_name=args.collection_name.strip(),
        expected_source_sha256=args.expected_source_sha256.strip().lower(),
        expected_active_ocr_job_id=args.expected_active_ocr_job_id,
        expected_active_chunk_set_id=args.expected_active_chunk_set_id,
        expected_active_vector_collection_id=args.expected_active_vector_collection_id,
        apply=args.apply,
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _string_snapshot(value: dict | None) -> dict[str, str | None]:
    snapshot = value or {}
    return {
        "ocr_job_id": str(snapshot["ocr_job_id"]) if snapshot.get("ocr_job_id") else None,
        "chunk_set_id": str(snapshot["chunk_set_id"]) if snapshot.get("chunk_set_id") else None,
        "vector_collection_id": (
            str(snapshot["vector_collection_id"]) if snapshot.get("vector_collection_id") else None
        ),
    }


def _active_state(document: dict) -> dict:
    return {
        "status": document.get("status"),
        "current_processing": copy.deepcopy(document.get("current_processing") or {}),
        "pipeline_summary": copy.deepcopy(document.get("pipeline_summary") or {}),
    }


def _current_original_artifact(document: dict) -> dict:
    artifacts = [
        artifact
        for artifact in document.get("artifacts") or []
        if artifact.get("type") in ORIGINAL_ARTIFACT_TYPES and artifact.get("is_current", True)
    ]
    if len(artifacts) != 1:
        raise ValueError(f"expected exactly one current original artifact, found {len(artifacts)}")
    return artifacts[0]


def _chroma_collection_exists(collection_name: str) -> bool:
    """Query collection names without creating the requested collection."""
    from modules.rag.chromadb_engine import get_chroma_client

    collections = get_chroma_client().list_collections()
    return any(
        (item if isinstance(item, str) else getattr(item, "name", None)) == collection_name
        for item in collections
    )


def _validate_active_records(db, document: dict, expected: dict[str, str]) -> None:
    document_id = document["_id"]
    version = document.get("current_version")
    ocr_job = db.document_jobs.find_one({"_id": object_id(expected["ocr_job_id"], "ocr_job_id")})
    if (
        not ocr_job
        or ocr_job.get("document_id") != document_id
        or ocr_job.get("document_version") != version
        or ocr_job.get("job_type") != "OCR"
        or ocr_job.get("status") != "COMPLETED"
    ):
        raise ValueError("expected active OCR job is missing, incomplete, or belongs to another lineage")

    chunk_set = db.chunk_sets.find_one(
        {"_id": object_id(expected["chunk_set_id"], "chunk_set_id")}
    )
    if (
        not chunk_set
        or chunk_set.get("document_id") != document_id
        or chunk_set.get("document_version") != version
        or chunk_set.get("source_ocr_job_id") != ocr_job["_id"]
        or chunk_set.get("status") != "COMPLETED"
    ):
        raise ValueError("expected active chunk set is missing, incomplete, or has invalid ancestry")

    vector = db.vector_collections.find_one(
        {"_id": object_id(expected["vector_collection_id"], "vector_collection_id")}
    )
    if not vector or vector.get("provider") != "CHROMA" or not vector.get("is_active"):
        raise ValueError("expected active vector collection is missing or inactive")


def _assert_candidate_collection_absent(
    db,
    collection_name: str,
    chroma_collection_exists: Callable[[str], bool],
) -> None:
    if db.vector_collections.find_one({"collection_name": collection_name}):
        raise ValueError("vector collection name already exists in MongoDB")
    if chroma_collection_exists(collection_name):
        raise ValueError("vector collection name already exists in ChromaDB")


def inspect_reprocess_plan(
    request: ReprocessRequest,
    *,
    db=None,
    repository: MongoDocumentRepository | None = None,
    chroma_collection_exists: Callable[[str], bool] = _chroma_collection_exists,
) -> ReprocessPlan:
    database = db if db is not None else get_database()
    repo = repository if repository is not None else MongoDocumentRepository(database)

    if not request.collection_name:
        raise ValueError("collection name cannot be empty")
    if not 3 <= len(request.collection_name) <= 512:
        raise ValueError("collection name must contain between 3 and 512 characters")
    if not SHA256_PATTERN.fullmatch(request.expected_source_sha256):
        raise ValueError("expected source SHA-256 must contain exactly 64 hexadecimal characters")
    object_id(request.document_id, "document_id")
    for field_name, value in request.expected_active.items():
        object_id(value, field_name)

    document = repo.find_by_id(request.document_id)
    if not document or document.get("archived_at") is not None:
        raise ValueError("document is missing or archived")
    if document.get("status") != "READY":
        raise ValueError("document must be READY before creating a replacement lineage")
    pipeline_summary = document.get("pipeline_summary") or {}
    if any(
        pipeline_summary.get(key) != "COMPLETED"
        for key in ("ocr_status", "chunk_status", "index_status")
    ):
        raise ValueError("active OCR, chunk, and index pipeline summary must all be COMPLETED")

    active_snapshot = _string_snapshot(document.get("current_processing"))
    if active_snapshot != request.expected_active:
        raise ValueError(
            f"active lineage mismatch: expected {request.expected_active}, found {active_snapshot}"
        )
    if document.get("pending_processing"):
        raise ValueError("document already has a pending lineage")

    active_jobs = list(
        database.document_jobs.find(
            {"document_id": document["_id"], "status": {"$in": sorted(ACTIVE_JOB_STATUSES)}},
            {"_id": 1, "job_type": 1, "status": 1},
        )
    )
    if active_jobs:
        labels = [f"{item.get('_id')}:{item.get('job_type')}:{item.get('status')}" for item in active_jobs]
        raise ValueError(f"document already has active pipeline jobs: {labels}")

    _validate_active_records(database, document, request.expected_active)

    artifact = _current_original_artifact(document)
    artifact_version = artifact.get("document_version")
    if artifact_version is not None and artifact_version != document.get("current_version"):
        raise ValueError("current original artifact belongs to another document version")
    storage_uri = (artifact.get("storage") or {}).get("uri")
    if not storage_uri:
        raise ValueError("current original artifact has no storage URI")
    source_path = Path(storage_uri).resolve()
    if not source_path.is_file():
        raise ValueError(f"current original artifact is unavailable: {source_path}")
    artifact_sha256 = str(artifact.get("sha256") or "").lower()
    if artifact_sha256 != request.expected_source_sha256:
        raise ValueError("source SHA-256 does not match current artifact metadata")
    actual_sha256 = file_sha256(source_path)
    if actual_sha256 != request.expected_source_sha256:
        raise ValueError("source SHA-256 does not match file contents")
    expected_size = artifact.get("size_bytes")
    if expected_size is not None and int(expected_size) != source_path.stat().st_size:
        raise ValueError("source size does not match current artifact metadata")

    _assert_candidate_collection_absent(
        database,
        request.collection_name,
        chroma_collection_exists,
    )

    return ReprocessPlan(
        request=request,
        document=document,
        source_artifact=artifact,
        source_path=source_path,
        source_sha256=actual_sha256,
        active_snapshot={key: str(value) for key, value in request.expected_active.items()},
        active_state=_active_state(document),
    )


def _assert_active_state_unchanged(repository: MongoDocumentRepository, plan: ReprocessPlan) -> dict:
    document = repository.find_by_id(plan.request.document_id)
    if not document:
        raise RuntimeError("document disappeared while reprocessing")
    if _active_state(document) != plan.active_state:
        raise RuntimeError("active lineage status, pointer, or pipeline summary changed during reprocessing")
    return document


def _assert_only_expected_job_is_active(db, document_id: ObjectId, expected_job_id: ObjectId) -> None:
    active_jobs = list(
        db.document_jobs.find(
            {"document_id": document_id, "status": {"$in": sorted(ACTIVE_JOB_STATUSES)}},
            {"_id": 1},
        )
    )
    unexpected = [str(job["_id"]) for job in active_jobs if job.get("_id") != expected_job_id]
    if unexpected:
        raise RuntimeError(f"concurrent pipeline job detected: {unexpected}")


def _persist_extraction_artifacts(
    repository: MongoDocumentRepository,
    document_id: ObjectId,
    job_id: ObjectId,
    extraction: dict,
) -> list[dict]:
    attached: list[dict] = []
    artifacts = (
        (
            "RAW_EXTRACTION_JSON",
            extraction.get("raw_extraction_file"),
            extraction.get("raw_extraction_mime_type") or "application/json",
        ),
        ("EXTRACTION_MARKDOWN", extraction.get("output_file"), "text/markdown"),
    )
    for artifact_type, artifact_path, mime_type in artifacts:
        if not artifact_path:
            raise ValueError(f"extraction did not return {artifact_type}")
        blob = deduplicate_artifact_file(artifact_path, resolve_path(settings.artifact_blob_dir))
        repository.attach_processing_artifact(
            document_id,
            job_id=job_id,
            uri=blob["uri"],
            size_bytes=blob["size_bytes"],
            sha256=blob["sha256"],
            artifact_type=artifact_type,
            mime_type=mime_type,
        )
        attached.append({"type": artifact_type, **blob})
    return attached


def _verify_candidate(
    db,
    repository: MongoDocumentRepository,
    plan: ReprocessPlan,
    *,
    ocr_job_id: str,
    chunk_set_id: str,
    vector_collection_id: str,
) -> dict:
    document = _assert_active_state_unchanged(repository, plan)
    pending = _string_snapshot(document.get("pending_processing"))
    expected_pending = {
        "ocr_job_id": ocr_job_id,
        "chunk_set_id": chunk_set_id,
        "vector_collection_id": vector_collection_id,
    }
    if pending != expected_pending:
        raise RuntimeError(f"pending lineage mismatch: expected {expected_pending}, found {pending}")
    if (document.get("pending_processing") or {}).get("validation_status") != "AWAITING_VALIDATION":
        raise RuntimeError("candidate pending lineage is not awaiting validation")

    document_oid = document["_id"]
    version = document.get("current_version")
    ocr_job = db.document_jobs.find_one({"_id": object_id(ocr_job_id, "ocr_job_id")})
    chunk_set = db.chunk_sets.find_one({"_id": object_id(chunk_set_id, "chunk_set_id")})
    vector = db.vector_collections.find_one(
        {"_id": object_id(vector_collection_id, "vector_collection_id")}
    )
    if (
        not ocr_job
        or ocr_job.get("document_id") != document_oid
        or ocr_job.get("document_version") != version
        or ocr_job.get("job_type") != "OCR"
        or ocr_job.get("status") != "COMPLETED"
    ):
        raise RuntimeError("candidate OCR job failed ownership/version/status verification")
    if (
        not chunk_set
        or chunk_set.get("document_id") != document_oid
        or chunk_set.get("document_version") != version
        or chunk_set.get("source_ocr_job_id") != ocr_job["_id"]
        or chunk_set.get("status") != "COMPLETED"
    ):
        raise RuntimeError("candidate chunk set failed ownership/version/ancestry verification")
    if (
        not vector
        or vector.get("collection_name") != plan.request.collection_name
        or not vector.get("is_active")
    ):
        raise RuntimeError("candidate vector collection failed identity/status verification")

    chunk_count = db.document_chunks.count_documents(
        {"document_id": document_oid, "chunk_set_id": chunk_set["_id"]}
    )
    embedding_count = db.chunk_embeddings.count_documents(
        {"chunk_set_id": chunk_set["_id"], "vector_collection_id": vector["_id"]}
    )
    if chunk_count <= 0 or chunk_count != int(chunk_set.get("total_chunks") or 0):
        raise RuntimeError("candidate Mongo chunk count is empty or inconsistent")
    if embedding_count != chunk_count:
        raise RuntimeError("candidate Mongo embedding count does not match chunk count")
    return {
        "ocr_job_id": ocr_job_id,
        "chunk_set_id": chunk_set_id,
        "vector_collection_id": vector_collection_id,
        "collection_name": vector["collection_name"],
        "chunks": chunk_count,
        "embeddings": embedding_count,
        "pending_validation_status": (document.get("pending_processing") or {}).get("validation_status"),
    }


def execute_reprocess(
    request: ReprocessRequest,
    *,
    db=None,
    repository: MongoDocumentRepository | None = None,
    chroma_collection_exists: Callable[[str], bool] = _chroma_collection_exists,
    pipeline_runner=None,
    chunk_runner=None,
) -> dict:
    if not request.apply:
        raise ValueError("execute_reprocess requires --apply")
    database = db if db is not None else get_database()
    repo = repository if repository is not None else MongoDocumentRepository(database)
    plan = inspect_reprocess_plan(
        request,
        db=database,
        repository=repo,
        chroma_collection_exists=chroma_collection_exists,
    )

    if pipeline_runner is None:
        from modules.ocr.pipeline import run_document_pipeline

        pipeline_runner = run_document_pipeline
    if chunk_runner is None:
        from modules.rag.chunking import chunk_document_and_store

        chunk_runner = chunk_document_and_store

    source_format = plan.source_path.suffix.lower().lstrip(".") or "unknown"
    ocr_job = repo.create_job(
        plan.document["_id"],
        "OCR",
        config={
            "source_format": source_format,
            "pipeline": "structured_pending_lineage",
            "target_collection": request.collection_name,
            "expected_source_sha256": request.expected_source_sha256,
        },
    )
    ocr_job_id = str(ocr_job["_id"])
    ocr_completed = False
    try:
        _assert_only_expected_job_is_active(database, plan.document["_id"], ocr_job["_id"])
        if file_sha256(plan.source_path) != request.expected_source_sha256:
            raise RuntimeError("source file changed after precondition validation")
        repo.update_job(ocr_job["_id"], "PROCESSING", progress=1)
        _assert_active_state_unchanged(repo, plan)
        output_path = resolve_path(settings.ocr_output_dir) / (
            f"{plan.document['_id']}_{ocr_job['_id']}_result.md"
        )
        extraction = pipeline_runner(
            source_path=str(plan.source_path),
            output_path=str(output_path),
            document_title=plan.document.get("title") or plan.source_path.stem,
            document_id=request.document_id,
            source_file_name=plan.document.get("original_filename") or plan.source_path.name,
            source_uri=str(plan.source_path),
            mime_type=plan.source_artifact.get("mime_type"),
        )
        _assert_only_expected_job_is_active(database, plan.document["_id"], ocr_job["_id"])
        repo.save_pages(plan.document["_id"], ocr_job["_id"], extraction["pages"])
        attached_artifacts = _persist_extraction_artifacts(
            repo,
            plan.document["_id"],
            ocr_job["_id"],
            extraction,
        )
        repo.update_job(ocr_job["_id"], "COMPLETED", progress=100, stats=extraction["stats"])
        ocr_completed = True
        after_ocr = _assert_active_state_unchanged(repo, plan)
        pending_after_ocr = _string_snapshot(after_ocr.get("pending_processing"))
        if pending_after_ocr != {
            "ocr_job_id": ocr_job_id,
            "chunk_set_id": None,
            "vector_collection_id": None,
        }:
            raise RuntimeError(f"unexpected pending state after OCR: {pending_after_ocr}")
    except Exception as exc:
        if not ocr_completed:
            repo.update_job(ocr_job["_id"], "FAILED", error_message=str(exc))
        raise

    try:
        _assert_only_expected_job_is_active(database, plan.document["_id"], ocr_job["_id"])
        _assert_candidate_collection_absent(
            database,
            request.collection_name,
            chroma_collection_exists,
        )
        chunking = chunk_runner(
            document_id=request.document_id,
            chunk_size=settings.chunk_size_default,
            chunk_overlap=settings.chunk_overlap_default,
            collection_name=request.collection_name,
        )
    except Exception as exc:
        from modules.rag.mongodb import fail_chunk_set

        fail_chunk_set(request.document_id, str(exc))
        raise

    if not chunking.chunk_set_id or not chunking.vector_collection_id:
        raise RuntimeError("chunking completed without a chunk set or vector collection")
    candidate = _verify_candidate(
        database,
        repo,
        plan,
        ocr_job_id=ocr_job_id,
        chunk_set_id=chunking.chunk_set_id,
        vector_collection_id=chunking.vector_collection_id,
    )
    return {
        "status": "pending_created",
        "document_id": request.document_id,
        "document_version": plan.document.get("current_version"),
        "source_sha256": plan.source_sha256,
        "active_snapshot_unchanged": plan.active_snapshot,
        "candidate": candidate,
        "extraction_stats": extraction["stats"],
        "chunking_stats": chunking.stats.model_dump(mode="json"),
        "artifacts": attached_artifacts,
        "promoted": False,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        request = parse_args(argv)
        database = get_database()
        repository = MongoDocumentRepository(database)
        plan = inspect_reprocess_plan(request, db=database, repository=repository)
        print(json.dumps({"operation": "reprocess-plan", **plan.public_dict()}, ensure_ascii=False, default=str))
        if not request.apply:
            return 0
        result = execute_reprocess(request, db=database, repository=repository)
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "error_type": type(exc).__name__, "error": str(exc), "promoted": False},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
