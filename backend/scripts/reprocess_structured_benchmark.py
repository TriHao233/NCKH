"""Safely reprocess one document into an independent document/vector lineage.

The command is read-only unless ``--apply`` is supplied. It never deletes or
updates the source document, its pages, chunks, or vector collection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from bson import ObjectId

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.config import resolve_path, settings
from core.database import get_database
from modules.documents.repository import MongoDocumentRepository
from modules.ocr.pipeline import run_document_pipeline
from modules.rag.chunking import chunk_document_and_store
from modules.rag.mongodb import fail_chunk_set


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-document-id", required=True)
    parser.add_argument("--collection-name", required=True)
    parser.add_argument("--apply", action="store_true", help="Create and process the independent benchmark copy")
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def attach_artifact(
    repository: MongoDocumentRepository,
    document_id: ObjectId,
    job_id: ObjectId,
    path: Path,
    artifact_type: str,
    mime_type: str,
) -> None:
    repository.attach_processing_artifact(
        document_id,
        job_id=job_id,
        uri=str(path),
        size_bytes=path.stat().st_size,
        sha256=file_sha256(path),
        artifact_type=artifact_type,
        mime_type=mime_type,
    )


def main() -> int:
    args = parse_args()
    database = get_database()
    repository = MongoDocumentRepository(database)
    source = repository.find_by_id(args.source_document_id)
    if not source:
        raise SystemExit("Source document does not exist")
    original = next(
        (
            artifact
            for artifact in source.get("artifacts") or []
            if artifact.get("type") == "ORIGINAL_PDF" and artifact.get("is_current", True)
        ),
        None,
    )
    if not original:
        raise SystemExit("Source document has no current ORIGINAL_PDF artifact")
    source_path = Path((original.get("storage") or {}).get("uri") or "")
    if not source_path.is_file():
        raise SystemExit("Source PDF artifact is unavailable")
    if database.vector_collections.find_one({"provider": "CHROMA", "collection_name": args.collection_name}):
        raise SystemExit("Collection name already exists; choose a new name to avoid mixed vectors")

    plan = {
        "mode": "apply" if args.apply else "dry_run",
        "source_document_id": str(source["_id"]),
        "source_pdf": str(source_path),
        "source_current_processing": source.get("current_processing") or {},
        "target_collection": args.collection_name,
        "mutation_scope": "new document, OCR job, pages, chunk set, chunks and vector collection only",
    }
    print(json.dumps(plan, ensure_ascii=False, default=str))
    if not args.apply:
        return 0

    clone = repository.create(
        {
            "title": f"{source.get('title') or source_path.stem} [structured P0 benchmark]",
            "original_filename": source.get("original_filename") or source_path.name,
            "subject_id": str(source["subject_id"]) if source.get("subject_id") else None,
            "chapter_id": str(source["chapter_id"]) if source.get("chapter_id") else None,
            "original_uri": str(source_path),
            "size_bytes": source_path.stat().st_size,
            "sha256": file_sha256(source_path),
        },
        uploaded_by_user_id=source.get("uploaded_by_user_id"),
    )
    job = repository.create_job(clone["_id"], "OCR", config={"source_format": "pdf", "pipeline": "structured_p0"})
    repository.update_job(job["_id"], "PROCESSING", progress=1)
    output_path = resolve_path(settings.ocr_output_dir) / f"{clone['_id']}_{job['_id']}_result.md"
    try:
        extraction = run_document_pipeline(
            source_path=str(source_path),
            output_path=str(output_path),
            document_title=clone["title"],
            document_id=str(clone["_id"]),
            source_file_name=clone["original_filename"],
            source_uri=str(source_path),
            mime_type="application/pdf",
        )
        repository.save_pages(clone["_id"], job["_id"], extraction["pages"])
        attach_artifact(repository, clone["_id"], job["_id"], output_path, "EXTRACTION_MARKDOWN", "text/markdown")
        attach_artifact(
            repository,
            clone["_id"],
            job["_id"],
            Path(extraction["raw_extraction_file"]),
            "RAW_EXTRACTION_JSON",
            "application/json",
        )
        repository.update_job(job["_id"], "COMPLETED", stats=extraction["stats"])
    except Exception as exc:
        repository.update_job(job["_id"], "FAILED", error_message=str(exc))
        raise

    try:
        chunking = chunk_document_and_store(
            document_id=str(clone["_id"]),
            chunk_size=settings.chunk_size_default,
            chunk_overlap=settings.chunk_overlap_default,
            collection_name=args.collection_name,
        )
    except Exception as exc:
        fail_chunk_set(str(clone["_id"]), str(exc))
        raise

    result = {
        "source_document_id": str(source["_id"]),
        "benchmark_document_id": str(clone["_id"]),
        "ocr_job_id": str(job["_id"]),
        "chunk_job_id": chunking.chunk_job_id,
        "chunk_set_id": chunking.chunk_set_id,
        "vector_collection_id": chunking.vector_collection_id,
        "collection_name": chunking.collection_name,
        "extraction_stats": extraction["stats"],
        "chunking_stats": chunking.stats.model_dump(mode="json"),
    }
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
