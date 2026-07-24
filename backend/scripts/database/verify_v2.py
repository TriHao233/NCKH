"""Read-only integrity checks for Database V2."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import AUTH_COLLECTIONS, RAG_COLLECTIONS, SCHEMA_VERSION
from core.database import get_auth_db, get_rag_db, ping_database


def main() -> int:
    ping_database()
    auth_db = get_auth_db()
    db = get_rag_db()
    failures: list[str] = []
    missing_auth = sorted(set(AUTH_COLLECTIONS) - set(auth_db.list_collection_names()))
    missing_rag = sorted(set(RAG_COLLECTIONS) - set(db.list_collection_names()))
    if missing_auth:
        failures.append(f"missing auth collections={missing_auth}")
    if missing_rag:
        failures.append(f"missing RAG collections={missing_rag}")

    rag_uids = {
        uid
        for uid in db.users.distinct("firebase_uid")
        if isinstance(uid, str) and uid
    }
    auth_users = list(auth_db["User"].find({}))
    auth_uids = {
        item.get("uid")
        for item in auth_users
        if isinstance(item.get("uid"), str) and item.get("uid")
    }
    missing_session_links = len(rag_uids - auth_uids)
    if missing_session_links:
        failures.append(
            f"rag users without NCKH.User link={missing_session_links}"
        )
    orphan_session_links = len(auth_uids - rag_uids)
    if orphan_session_links:
        failures.append(
            f"NCKH.User links without rag profile={orphan_session_links}"
        )
    invalid_auth_users = sum(
        1
        for item in auth_users
        if set(item) - {"_id", "uid", "token"}
        or not isinstance(item.get("uid"), str)
        or not isinstance(item.get("token"), (str, type(None)))
    )
    if invalid_auth_users:
        failures.append(f"invalid NCKH.User documents={invalid_auth_users}")

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
