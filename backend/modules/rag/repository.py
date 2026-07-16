from datetime import datetime

from bson.objectid import ObjectId

from core.database import get_rag_db


def get_document_record(doc_id: str) -> dict | None:
    """Lay document metadata tu documents collection."""
    db = get_rag_db()
    doc = db["documents"].find_one({"_id": ObjectId(doc_id)})
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


def iter_document_pages(doc_id: str):
    """Stream cac trang theo thu tu tang dan (page_number)."""
    db = get_rag_db()
    cursor = db["pages"].find({"document_id": str(doc_id)}).sort("page_number", 1)
    for page in cursor:
        yield {
            "page_number": int(page.get("page_number", 0)),
            "text": page.get("text", ""),
        }


def update_chunking_status(
    doc_id: str,
    status: str,
    stats: dict | None = None,
    error_message: str | None = None,
    collection_name: str | None = None,
    total_chunks: int | None = None,
    stored_chunks: int | None = None,
):
    """Cap nhat trang thai chunking va thong tin luu tru."""
    db = get_rag_db()
    update_data = {
        "chunk_status": status,
        "chunk_updated_at": datetime.utcnow(),
    }
    if stats is not None:
        update_data["chunk_stats"] = stats
    if error_message is not None:
        update_data["chunk_error_message"] = error_message
    if collection_name is not None:
        update_data["chunk_collection"] = collection_name
    if total_chunks is not None:
        update_data["chunk_total"] = total_chunks
    if stored_chunks is not None:
        update_data["chunk_stored"] = stored_chunks

    db["documents"].update_one({"_id": ObjectId(doc_id)}, {"$set": update_data})
