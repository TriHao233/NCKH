import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from core.config import settings
from core.database import get_database
from modules.questions.repository import object_id
from modules.rag.chromadb_engine import get_chroma_client, store_chunks


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild ChromaDB vectors from MongoDB document_chunks."
    )
    parser.add_argument(
        "--collection",
        default=settings.chromadb_collection_name,
        help="ChromaDB collection name. Defaults to CHROMADB_COLLECTION_NAME.",
    )
    parser.add_argument(
        "--document-id",
        help="Only rebuild chunks for one document ObjectId.",
    )
    parser.add_argument(
        "--chunk-set-id",
        help="Only rebuild chunks for one chunk set ObjectId.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without writing ChromaDB or updating MongoDB.",
    )
    parser.add_argument(
        "--reset-collection",
        action="store_true",
        help="Delete and recreate the ChromaDB collection before upsert.",
    )
    return parser.parse_args()


def vector_collection(db, collection_name: str) -> dict:
    record = db.vector_collections.find_one(
        {"provider": "CHROMA", "collection_name": collection_name, "is_active": True},
        sort=[("created_at", -1)],
    )
    if not record:
        raise RuntimeError(f"No active vector_collections record for '{collection_name}'")
    model_name = (record.get("embedding_model") or {}).get("model_name")
    if model_name != settings.embedding_model_name:
        raise RuntimeError(
            "Embedding model mismatch: "
            f"MongoDB has '{model_name}', settings uses '{settings.embedding_model_name}'."
        )
    return record


def chunk_filter(args: argparse.Namespace) -> dict:
    query = {}
    if args.document_id:
        query["document_id"] = object_id(args.document_id, "document_id")
    if args.chunk_set_id:
        query["chunk_set_id"] = object_id(args.chunk_set_id, "chunk_set_id")
    return query


def heading_path_text(path: list | None) -> str:
    return " > ".join(str(item) for item in (path or []) if item)


def metadata_for_chunk(chunk: dict, vector_id: ObjectId) -> dict:
    heading = chunk.get("heading") or {}
    heading_path = heading.get("path") or []
    page_range = chunk.get("page_range") or {}
    return {
        "document_id": str(chunk["document_id"]),
        "chunk_id": str(chunk["_id"]),
        "chunk_set_id": str(chunk["chunk_set_id"]),
        "vector_collection_id": str(vector_id),
        "content_hash": chunk.get("content_hash"),
        "heading": heading.get("title") or "",
        "heading_path": heading_path,
        "heading_path_text": heading_path_text(heading_path),
        "heading_norm": heading.get("normalized") or "",
        "page_start": page_range.get("start"),
        "page_end": page_range.get("end"),
        "page_marks": page_range.get("pages") or [],
        "content_type": chunk.get("content_type", "text"),
        "semantic_type": chunk.get("semantic_type", "theory"),
        "information_density": chunk.get("information_density", 0),
        "token_count": chunk.get("token_count", 0),
    }


def build_payload(db, args: argparse.Namespace, vector: dict) -> tuple[list[str], list[str], list[dict], list[ObjectId]]:
    chunks = list(db.document_chunks.find(chunk_filter(args)).sort([("chunk_set_id", 1), ("chunk_no", 1)]))
    if not chunks:
        return [], [], [], []

    chunk_ids = [chunk["_id"] for chunk in chunks]
    embeddings = {
        item["chunk_id"]: item
        for item in db.chunk_embeddings.find(
            {
                "chunk_id": {"$in": chunk_ids},
                "vector_collection_id": vector["_id"],
            }
        )
    }

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    embedding_ids: list[ObjectId] = []
    missing_embedding_count = 0

    for chunk in chunks:
        embedding = embeddings.get(chunk["_id"])
        if not embedding:
            missing_embedding_count += 1
            continue
        ids.append(embedding.get("external_vector_id") or f"{chunk['_id']}:{vector['_id']}")
        documents.append(chunk.get("content", ""))
        metadatas.append(metadata_for_chunk(chunk, vector["_id"]))
        embedding_ids.append(embedding["_id"])

    if missing_embedding_count:
        print(f"Skipped chunks without chunk_embeddings: {missing_embedding_count}")
    return ids, documents, metadatas, embedding_ids


def reset_collection(collection_name: str) -> None:
    client = get_chroma_client()
    try:
        client.delete_collection(collection_name)
        print(f"Deleted ChromaDB collection: {collection_name}")
    except Exception as exc:
        print(f"Collection delete skipped: {exc}")


def mark_embeddings_indexed(db, embedding_ids: list[ObjectId]) -> int:
    if not embedding_ids:
        return 0
    now = utc_now()
    result = db.chunk_embeddings.update_many(
        {"_id": {"$in": embedding_ids}},
        [
            {
                "$set": {
                    "status": "INDEXED",
                    "embedding_content_hash": "$chunk_content_hash",
                    "indexed_at": now,
                    "updated_at": now,
                    "error": None,
                }
            }
        ],
    )
    return result.modified_count


def main() -> int:
    args = parse_args()
    db = get_database()
    vector = vector_collection(db, args.collection)
    ids, documents, metadatas, embedding_ids = build_payload(db, args, vector)

    print(f"Collection: {args.collection}")
    print(f"Vector collection id: {vector['_id']}")
    print(f"Prepared chunks: {len(ids)}")

    if args.dry_run:
        return 0
    if args.reset_collection:
        reset_collection(args.collection)

    stored = store_chunks(ids, documents, metadatas, args.collection)
    updated = mark_embeddings_indexed(db, embedding_ids)
    print(f"Upserted vectors: {stored}")
    print(f"Updated chunk_embeddings: {updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
