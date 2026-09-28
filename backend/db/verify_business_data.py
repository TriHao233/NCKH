"""Compare MongoDB business IDs and critical fields with the PostgreSQL copy.

This is read-only. It reports counts, never document content or credentials.
"""

from __future__ import annotations

import argparse

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pymongo import MongoClient

from core.config import settings
from db.copy_business_data import SOURCE_ORDER, fingerprint, projected_rows

CHILD_TABLES = {
    "subject_chapters", "learning_outcomes", "ai_model_versions",
    "document_artifacts", "document_subjects", "document_lineage_events",
    "exam_questions", "legacy_dictionaries",
}
CRITICAL_FIELDS = {
    "users": ("firebase_uid", "email", "role", "is_active",
              "permissions", "permission_grants", "permission_revokes",
              "review_subject_ids"),
    "subjects": ("subject_code", "subject_name", "is_active"),
    "documents": ("subject_id", "status", "current_version", "active_chunk_set_id"),
    "document_subjects": ("position_no",),
    "document_pages": ("document_id", "version", "unit_number", "page_number", "source_location"),
    "document_jobs": ("document_id", "job_type", "status", "attempt_no"),
    "document_artifacts": (
        "document_id", "artifact_type", "storage_provider", "storage_key",
        "checksum_sha256", "mime_type", "size_bytes", "version",
    ),
    "document_lineage_events": ("document_id", "event_type", "rollback_available",
                                "promotion_operation_id", "status"),
    "audit_logs": ("actor_user_id", "actor_type", "actor_role", "action",
                   "entity_type", "entity_id", "before_hash", "after_hash"),
    "review_settings": ("updated_by_user_id",),
    "moodle_targets": ("site_key", "site_name", "mode", "secret_ref", "is_active"),
    "questions": (
        "question_code", "current_version", "current_version_id",
        "approved_version_id", "review_status", "lifecycle_status",
    ),
    "question_versions": ("question_id", "version", "content_hash"),
    "evaluation_jobs": ("question_id", "question_version_id", "status",
                        "evaluator_model_code", "attempt_no"),
    "ai_model_versions": ("model_id", "version", "config_hash"),
    "prompt_templates": ("template_key", "version", "content_hash", "is_active"),
    "evaluation_policies": ("policy_name", "version", "weights_hash", "is_active"),
}
DOCUMENT_CONTENT_FIELDS = {
    "documents": ("payload",),
    "document_jobs": ("payload",),
    "document_pages": ("payload", "raw_text", "clean_text"),
    "document_artifacts": ("payload",),
    "document_lineage_events": ("payload", "from_snapshot", "to_snapshot", "validation"),
    "audit_logs": ("payload", "before_state", "after_state", "changes", "metadata"),
    "review_settings": ("payload",),
    "evaluation_jobs": ("payload", "model_snapshot", "policy_snapshot",
                        "source_snapshot", "result", "error"),
}


def row_key(table: str, row: dict):
    if table == "llm_slots":
        return (row["provider"], row["slot_index"])
    if table == "exam_questions":
        return (row["exam_id"], row["position"])
    if table == "document_subjects":
        return (row["document_id"], row["subject_id"])
    if table == "document_lineage_events":
        return row["operation_id"]
    return row["id"]


def _document_vector_errors(mongo_db, target: dict[str, dict]) -> list[str]:
    """Check references crossing PostgreSQL document metadata and Mongo vector data."""
    documents = target.get("documents", {})
    jobs = target.get("document_jobs", {})
    chunk_sets = {str(item["_id"]): item for item in mongo_db.chunk_sets.find()}
    missing_documents = 0
    invalid_sources = 0
    invalid_active_pointers = 0
    invalid_chunks = 0
    invalid_embeddings = 0
    for chunk_set in chunk_sets.values():
        document_id = str(chunk_set.get("document_id"))
        if document_id not in documents:
            missing_documents += 1
        source_id = chunk_set.get("source_ocr_job_id")
        if source_id:
            job = jobs.get(str(source_id))
            if not job or job["document_id"] != document_id or job["job_type"] != "OCR":
                invalid_sources += 1
    for document_id, document in documents.items():
        active_id = document.get("active_chunk_set_id")
        if not active_id:
            continue
        chunk_set = chunk_sets.get(active_id)
        if (not chunk_set or str(chunk_set.get("document_id")) != document_id
                or chunk_set.get("status") != "COMPLETED"):
            invalid_active_pointers += 1
    chunks = {}
    for chunk in mongo_db.document_chunks.find({}, {
        "_id": 1, "document_id": 1, "chunk_set_id": 1,
    }):
        chunk_id = str(chunk["_id"])
        chunks[chunk_id] = chunk
        chunk_set = chunk_sets.get(str(chunk.get("chunk_set_id")))
        if (not chunk_set or str(chunk.get("document_id")) not in documents
                or str(chunk_set.get("document_id")) != str(chunk.get("document_id"))):
            invalid_chunks += 1
    for embedding in mongo_db.chunk_embeddings.find({}, {
        "chunk_id": 1, "chunk_set_id": 1,
    }):
        chunk = chunks.get(str(embedding.get("chunk_id")))
        if not chunk or str(chunk.get("chunk_set_id")) != str(embedding.get("chunk_set_id")):
            invalid_embeddings += 1
    print(
        "vector_document_links: "
        f"missing_documents={missing_documents} invalid_ocr_sources={invalid_sources} "
        f"invalid_active_pointers={invalid_active_pointers} "
        f"invalid_chunks={invalid_chunks} invalid_embeddings={invalid_embeddings}"
    )
    return ["vector_document_links"] if any((missing_documents, invalid_sources,
                                               invalid_active_pointers, invalid_chunks,
                                               invalid_embeddings)) else []


def verify(mongo_db, postgres_connection) -> list[str]:
    expected: dict[str, dict] = {}
    for name in SOURCE_ORDER:
        for document in mongo_db[name].find():
            for table, row in projected_rows(name, document):
                expected.setdefault(table, {})[row_key(table, row)] = row
    tables = (set(SOURCE_ORDER) - {"dictionaries", "pipeline_lineage_events"}) | CHILD_TABLES
    errors = []
    targets: dict[str, dict] = {}
    for table in sorted(tables):
        source = expected.get(table, {})
        rows = postgres_connection.execute(
            sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
        ).fetchall()
        target = {row_key(table, row): row for row in rows}
        if table in {"documents", "document_jobs"}:
            targets[table] = target
        missing = set(source) - set(target)
        extra = set(target) - set(source)
        mismatched = 0
        content_mismatched = 0
        for key in set(source) & set(target):
            fields = CRITICAL_FIELDS.get(table, ())
            if any(source[key].get(field) != target[key].get(field) for field in fields):
                mismatched += 1
            content_fields = DOCUMENT_CONTENT_FIELDS.get(table, ())
            if any(fingerprint(source[key].get(field)) != fingerprint(target[key].get(field))
                   for field in content_fields):
                content_mismatched += 1
        print(
            f"{table}: source={len(source)} postgres={len(target)} "
            f"missing={len(missing)} extra={len(extra)} "
            f"critical_mismatch={mismatched} content_mismatch={content_mismatched}"
        )
        if missing or extra or mismatched or content_mismatched:
            errors.append(table)
    errors.extend(_document_vector_errors(mongo_db, targets))
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=settings.mongo_uri)
    parser.add_argument("--mongo-db", default=settings.rag_db_name)
    args = parser.parse_args()
    if not settings.postgres_dsn:
        parser.error("POSTGRES_DSN is required")
    with MongoClient(args.mongo_uri, serverSelectionTimeoutMS=10000) as client:
        with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as connection:
            errors = verify(client[args.mongo_db], connection)
    if errors:
        parser.exit(1, "Mismatch in: " + ", ".join(errors) + "\n")
    print("Business IDs and critical fields match; vector collections remain in MongoDB.")


if __name__ == "__main__":
    main()
