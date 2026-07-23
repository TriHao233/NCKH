"""Read-only integrity checks for Database V2."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import COLLECTIONS, SCHEMA_VERSION
from core.database import get_database, ping_database


def main() -> int:
    ping_database()
    db = get_database()
    failures: list[str] = []
    existing = set(db.list_collection_names())
    missing = sorted(set(COLLECTIONS) - existing)
    if missing:
        failures.append(f"missing collections={missing}")

    orphan_versions = list(
        db.question_versions.aggregate(
            [
                {
                    "$lookup": {
                        "from": "questions",
                        "localField": "question_id",
                        "foreignField": "_id",
                        "as": "parent",
                    }
                },
                {"$match": {"parent": {"$size": 0}}},
                {"$count": "count"},
            ]
        )
    )
    if orphan_versions:
        failures.append(f"orphan question_versions={orphan_versions[0]['count']}")

    stale_embeddings = db.chunk_embeddings.count_documents(
        {
            "status": "INDEXED",
            "$expr": {"$ne": ["$chunk_content_hash", "$embedding_content_hash"]},
        }
    )
    if stale_embeddings:
        failures.append(f"stale indexed embeddings={stale_embeddings}")

    schema = db.schema_meta.find_one({"_id": "database_schema"})
    if not schema or schema.get("current_version") != SCHEMA_VERSION:
        failures.append("schema_meta is not at V2")

    if failures:
        print("Integrity failures:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("Database V2 integrity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
