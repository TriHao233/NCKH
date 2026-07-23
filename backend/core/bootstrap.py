import hashlib
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import CollectionInvalid

from core.database import get_database

SCHEMA_VERSION = 2

COLLECTIONS = (
    "users",
    "subjects",
    "documents",
    "document_jobs",
    "document_pages",
    "chunk_sets",
    "document_chunks",
    "vector_collections",
    "chunk_embeddings",
    "keywords",
    "ai_models",
    "prompt_templates",
    "evaluation_policies",
    "generation_runs",
    "questions",
    "question_versions",
    "question_evaluations",
    "question_reviews",
    "audit_logs",
    "moodle_publications",
    "schema_meta",
    "migration_id_map",
)

VALIDATORS = {
    "users": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "firebase_uid",
                "email",
                "display_name",
                "role",
                "is_active",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "firebase_uid": {"bsonType": "string", "minLength": 1},
                "email": {"bsonType": "string", "minLength": 3},
                "display_name": {"bsonType": "string", "minLength": 1},
                "role": {"enum": ["Admin", "Teacher"]},
                "is_active": {"bsonType": "bool"},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    },
    "documents": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "schema_version",
                "title",
                "original_filename",
                "status",
                "current_version",
                "artifacts",
                "current_processing",
                "pipeline_summary",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "schema_version": {"bsonType": "int", "minimum": 2},
                "title": {"bsonType": "string", "minLength": 1},
                "original_filename": {"bsonType": "string", "minLength": 1},
                "status": {
                    "enum": [
                        "UPLOADED",
                        "PROCESSING",
                        "READY",
                        "FAILED",
                        "ARCHIVED",
                    ]
                },
                "current_version": {"bsonType": "int", "minimum": 1},
                "artifacts": {"bsonType": "array"},
                "current_processing": {"bsonType": "object"},
                "pipeline_summary": {"bsonType": "object"},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    },
    "questions": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "schema_version",
                "question_code",
                "current_version",
                "current_version_id",
                "lifecycle_status",
                "evaluation_status",
                "review_status",
                "publication_status",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "schema_version": {"bsonType": "int", "minimum": 2},
                "question_code": {"bsonType": "string", "minLength": 1},
                "current_version": {"bsonType": "int", "minimum": 1},
                "current_version_id": {"bsonType": "objectId"},
                "lifecycle_status": {"enum": ["ACTIVE", "ARCHIVED"]},
                "evaluation_status": {
                    "enum": ["NOT_STARTED", "PROCESSING", "PASSED", "FAILED"]
                },
                "review_status": {
                    "enum": ["PENDING", "APPROVED", "REJECTED", "NEEDS_REVISION"]
                },
                "publication_status": {
                    "enum": ["NOT_PUBLISHED", "PUBLISHED", "STALE", "FAILED"]
                },
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    },
    "question_versions": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "question_id",
                "version",
                "origin",
                "classification",
                "content",
                "question_data",
                "sources",
                "content_hash",
                "created_at",
            ],
            "properties": {
                "question_id": {"bsonType": "objectId"},
                "version": {"bsonType": "int", "minimum": 1},
                "origin": {"enum": ["AI", "MANUAL", "IMPORT"]},
                "content": {"bsonType": "string", "minLength": 1},
                "question_data": {"bsonType": "object"},
                "sources": {"bsonType": "array"},
                "content_hash": {"bsonType": "string", "minLength": 1},
                "created_at": {"bsonType": "date"},
            },
        }
    },
}


def _ensure_collections() -> None:
    db = get_database()
    existing = set(db.list_collection_names())
    for name in COLLECTIONS:
        if name in existing:
            continue
        options = {}
        if name in VALIDATORS:
            options = {
                "validator": VALIDATORS[name],
                "validationLevel": "strict",
                "validationAction": "error",
            }
        try:
            db.create_collection(name, **options)
        except CollectionInvalid:
            pass

    for name, validator in VALIDATORS.items():
        db.command(
            {
                "collMod": name,
                "validator": validator,
                "validationLevel": "strict",
                "validationAction": "error",
            }
        )


def _ensure_indexes() -> None:
    db = get_database()
    db.users.create_indexes(
        [
            IndexModel([("firebase_uid", ASCENDING)], unique=True, name="uq_users_firebase_uid"),
            IndexModel([("email", ASCENDING)], unique=True, name="uq_users_email"),
            IndexModel([("role", ASCENDING), ("is_active", ASCENDING)], name="ix_users_role_active"),
        ]
    )
    db.subjects.create_index([("subject_code", ASCENDING)], unique=True, name="uq_subject_code")
    db.documents.create_indexes(
        [
            IndexModel(
                [
                    ("subject_id", ASCENDING),
                    ("chapter_id", ASCENDING),
                    ("status", ASCENDING),
                    ("created_at", DESCENDING),
                ],
                name="ix_documents_catalog",
            ),
            IndexModel([("uploaded_by_user_id", ASCENDING), ("created_at", DESCENDING)], name="ix_documents_uploader"),
            IndexModel([("artifacts.sha256", ASCENDING)], name="ix_documents_artifact_hash"),
        ]
    )
    db.document_jobs.create_indexes(
        [
            IndexModel(
                [
                    ("document_id", ASCENDING),
                    ("document_version", ASCENDING),
                    ("job_type", ASCENDING),
                    ("attempt_no", ASCENDING),
                ],
                unique=True,
                name="uq_document_job_attempt",
            ),
            IndexModel([("status", ASCENDING), ("queued_at", ASCENDING)], name="ix_document_jobs_queue"),
        ]
    )
    db.document_pages.create_indexes(
        [
            IndexModel([("ocr_job_id", ASCENDING), ("page_number", ASCENDING)], unique=True, name="uq_ocr_job_page"),
            IndexModel(
                [("document_id", ASCENDING), ("document_version", ASCENDING), ("page_number", ASCENDING)],
                name="ix_document_pages_version",
            ),
        ]
    )
    db.chunk_sets.create_indexes(
        [
            IndexModel([("chunk_job_id", ASCENDING)], unique=True, name="uq_chunk_set_job"),
            IndexModel([("document_id", ASCENDING), ("document_version", ASCENDING)], name="ix_chunk_sets_document"),
        ]
    )
    db.document_chunks.create_indexes(
        [
            IndexModel([("chunk_set_id", ASCENDING), ("chunk_no", ASCENDING)], unique=True, name="uq_chunk_set_number"),
            IndexModel([("document_id", ASCENDING), ("chunk_set_id", ASCENDING)], name="ix_chunks_document_set"),
        ]
    )
    db.vector_collections.create_index(
        [("provider", ASCENDING), ("collection_name", ASCENDING)],
        unique=True,
        name="uq_vector_collection",
    )
    db.chunk_embeddings.create_indexes(
        [
            IndexModel(
                [("chunk_id", ASCENDING), ("vector_collection_id", ASCENDING)],
                unique=True,
                name="uq_chunk_embedding",
            ),
            IndexModel(
                [("vector_collection_id", ASCENDING), ("external_vector_id", ASCENDING)],
                unique=True,
                name="uq_external_vector",
            ),
        ]
    )
    db.generation_runs.create_indexes(
        [
            IndexModel([("document_id", ASCENDING), ("created_at", DESCENDING)], name="ix_generation_document"),
            IndexModel([("requested_by_user_id", ASCENDING), ("created_at", DESCENDING)], name="ix_generation_requester"),
        ]
    )
    db.questions.create_indexes(
        [
            IndexModel([("question_code", ASCENDING)], unique=True, name="uq_question_code"),
            IndexModel(
                [
                    ("review_status", ASCENDING),
                    ("evaluation_status", ASCENDING),
                    ("updated_at", DESCENDING),
                ],
                name="ix_questions_workflow",
            ),
        ]
    )
    db.question_versions.create_indexes(
        [
            IndexModel([("question_id", ASCENDING), ("version", ASCENDING)], unique=True, name="uq_question_version"),
            IndexModel([("sources.chunk_id", ASCENDING)], name="ix_question_sources"),
        ]
    )
    db.question_evaluations.create_index(
        [("question_version_id", ASCENDING), ("created_at", DESCENDING)],
        name="ix_evaluations_version",
    )
    db.question_reviews.create_index(
        [("question_version_id", ASCENDING), ("reviewed_at", DESCENDING)],
        name="ix_reviews_version",
    )
    db.audit_logs.create_index(
        [("entity.type", ASCENDING), ("entity.id", ASCENDING), ("created_at", DESCENDING)],
        name="ix_audit_entity",
    )
    db.moodle_publications.create_index(
        [("idempotency_key", ASCENDING)],
        unique=True,
        name="uq_publication_idempotency",
    )
    db.migration_id_map.create_index(
        [("source_collection", ASCENDING), ("source_id", ASCENDING)],
        unique=True,
        name="uq_migration_source",
    )


def _seed_reference_data() -> None:
    db = get_database()
    now = datetime.now(timezone.utc)
    db.subjects.update_one(
        {"subject_code": "CTDL"},
        {
            "$setOnInsert": {
                "schema_version": SCHEMA_VERSION,
                "subject_name": "Cấu trúc dữ liệu",
                "description": "Học phần mặc định cho pipeline RAG",
                "chapters": [],
                "learning_outcomes": [],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )
    weights = {
        "faithfulness": 0.35,
        "contextual_relevancy": 0.20,
        "answer_relevancy": 0.15,
        "bloom_alignment": 0.15,
        "clo_alignment": 0.15,
    }
    db.evaluation_policies.update_one(
        {"policy_name": "Default question quality policy", "version": 1},
        {
            "$setOnInsert": {
                "schema_version": SCHEMA_VERSION,
                "weights": weights,
                "weights_hash": hashlib.sha256(str(sorted(weights.items())).encode()).hexdigest(),
                "thresholds": {"yellow_min": 0.60, "green_min": 0.80, "pass_min": 0.80},
                "is_active": True,
                "created_at": now,
            }
        },
        upsert=True,
    )


def bootstrap_database() -> None:
    """Create or align V2 collections without deleting existing data."""
    _ensure_collections()
    _ensure_indexes()
    _seed_reference_data()
    now = datetime.now(timezone.utc)
    get_database().schema_meta.update_one(
        {"_id": "database_schema"},
        {
            "$set": {"current_version": SCHEMA_VERSION, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
