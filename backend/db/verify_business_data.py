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
from db.copy_business_data import SOURCE_ORDER, projected_rows

CHILD_TABLES = {
    "subject_chapters", "learning_outcomes", "ai_model_versions",
    "document_artifacts", "exam_questions", "legacy_dictionaries",
}
CRITICAL_FIELDS = {
    "users": ("firebase_uid", "email", "role", "is_active"),
    "subjects": ("subject_code", "subject_name", "is_active"),
    "documents": ("status", "current_version", "active_chunk_set_id"),
    "questions": (
        "question_code", "current_version", "current_version_id",
        "approved_version_id", "review_status", "lifecycle_status",
    ),
    "question_versions": ("question_id", "version", "content_hash"),
    "ai_model_versions": ("model_id", "version", "config_hash"),
    "prompt_templates": ("template_key", "version", "content_hash", "is_active"),
    "evaluation_policies": ("policy_name", "version", "weights_hash", "is_active"),
}


def row_key(table: str, row: dict):
    if table == "llm_slots":
        return (row["provider"], row["slot_index"])
    if table == "exam_questions":
        return (row["exam_id"], row["position"])
    return row["id"]


def verify(mongo_db, postgres_connection) -> list[str]:
    expected: dict[str, dict] = {}
    for name in SOURCE_ORDER:
        for document in mongo_db[name].find():
            for table, row in projected_rows(name, document):
                expected.setdefault(table, {})[row_key(table, row)] = row
    tables = (set(SOURCE_ORDER) - {"dictionaries"}) | CHILD_TABLES
    errors = []
    for table in sorted(tables):
        source = expected.get(table, {})
        rows = postgres_connection.execute(
            sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
        ).fetchall()
        target = {row_key(table, row): row for row in rows}
        missing = set(source) - set(target)
        extra = set(target) - set(source)
        mismatched = 0
        for key in set(source) & set(target):
            fields = CRITICAL_FIELDS.get(table, ())
            if any(source[key].get(field) != target[key].get(field) for field in fields):
                mismatched += 1
        print(
            f"{table}: source={len(source)} postgres={len(target)} "
            f"missing={len(missing)} extra={len(extra)} critical_mismatch={mismatched}"
        )
        if missing or extra or mismatched:
            errors.append(table)
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
