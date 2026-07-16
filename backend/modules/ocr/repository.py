from datetime import datetime

from bson.objectid import ObjectId

from core.database import get_rag_db


def create_document_record(filename: str, title: str) -> str:
    """Tạo vé chờ (Job ID) với trạng thái queued"""
    db = get_rag_db()
    doc = {
        "filename": filename,
        "title": title,
        "status": "queued",  # Trạng thái ban đầu
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "error_message": None,
        "stats": None
    }
    result = db["documents"].insert_one(doc)
    return str(result.inserted_id)


def update_document_status(doc_id: str, status: str, stats: dict = None, error_message: str = None):
    """Cập nhật trạng thái tiến trình (processing, completed, failed)"""
    db = get_rag_db()
    update_data = {
        "status": status,
        "updated_at": datetime.utcnow()
    }
    if stats: update_data["stats"] = stats
    if error_message: update_data["error_message"] = error_message

    db["documents"].update_one({"_id": ObjectId(doc_id)}, {"$set": update_data})


def save_document_pages(doc_id: str, pages: list):
    """Lưu TỪNG TRANG thành các bản ghi riêng biệt để không bao giờ chạm trần 16MB"""
    db = get_rag_db()
    page_docs = []
    for page in pages:
        page_docs.append({
            "document_id": str(doc_id),
            "page_number": page["page_number"],
            "text": page["text"],
            "created_at": datetime.utcnow()
        })
    if page_docs:
        db["pages"].insert_many(page_docs)


def get_document_status(doc_id: str) -> dict:
    """Hàm API dùng để truy vấn trạng thái tiến trình"""
    db = get_rag_db()
    doc = db["documents"].find_one({"_id": ObjectId(doc_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
        return doc
    return None
