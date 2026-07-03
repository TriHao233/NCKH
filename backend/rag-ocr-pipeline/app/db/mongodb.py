import os
import logging

from datetime import datetime

from pymongo import MongoClient
from bson.objectid import ObjectId

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "rag_database"

_mongo_client = None

def get_db():
    """Hàm khởi tạo kết nối MongoDB (Singleton)"""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(MONGO_URI)
    return _mongo_client[DB_NAME]

def create_document_record(filename: str, title: str) -> str:
    """Tạo vé chờ (Job ID) với trạng thái queued"""
    db = get_db()
    doc = {
        "filename": filename,
        "title": title,
        "status": "queued", # Trạng thái ban đầu
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "error_message": None,
        "stats": None
    }
    result = db["documents"].insert_one(doc)
    return str(result.inserted_id)

def update_document_status(doc_id: str, status: str, stats: dict = None, error_message: str = None):
    """Cập nhật trạng thái tiến trình (processing, completed, failed)"""
    db = get_db()
    update_data = {
        "status": status,
        "updated_at": datetime.utcnow()
    }
    if stats: update_data["stats"] = stats
    if error_message: update_data["error_message"] = error_message
    
    db["documents"].update_one({"_id": ObjectId(doc_id)}, {"$set": update_data})

def save_document_pages(doc_id: str, pages: list):
    """Lưu TỪNG TRANG thành các bản ghi riêng biệt để không bao giờ chạm trần 16MB"""
    db = get_db()
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
    db = get_db()
    doc = db["documents"].find_one({"_id": ObjectId(doc_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
        return doc
    return None


def get_document_record(doc_id: str) -> dict | None:
    """Lay document metadata tu documents collection."""
    db = get_db()
    doc = db["documents"].find_one({"_id": ObjectId(doc_id)})
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


def iter_document_pages(doc_id: str):
    """Stream cac trang theo thu tu tang dan (page_number)."""
    db = get_db()
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
    db = get_db()
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

def init_default_dictionary(course_id: str = "it_fundamentals"):
    """Khởi tạo từ điển mặc định nếu chưa tồn tại"""
    db = get_db()
    existing = db["dictionaries"].find_one({"course_id": course_id})
    if not existing:
        default_dict = {
            "course_id": course_id,
            "name": "Từ điển Công nghệ Thông tin Căn bản",
            "category": "tech_keywords",
            "is_active": True,
            "core_keywords": [
                "struct", "pointer", "array", "linked list", "stack", 
                "queue", "tree", "graph", "heap", "hash", "sort", 
                "search", "binary", "complexity", "con trỏ", "mảng", 
                "giải thuật", "thuật toán", "đệ quy", "biến", "hằng"
            ],
            "learned_keywords": [],
            "pending_keywords": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        db["dictionaries"].insert_one(default_dict)

def get_active_keywords(course_id: str = "it_fundamentals") -> list[str]:
    """Lấy toàn bộ từ khóa active (Core + Learned) để phục vụ tính toán Density"""
    db = get_db()
    # Khởi tạo nếu trống
    init_default_dictionary(course_id)
    
    dict_doc = db["dictionaries"].find_one({"course_id": course_id, "is_active": True})
    if not dict_doc:
        return []
        
    core = dict_doc.get("core_keywords", [])
    learned = dict_doc.get("learned_keywords", [])
    
    # Gộp lại và chuẩn hóa viết thường
    all_kws = list(set(core + learned))
    return [str(kw).lower().strip() for kw in all_kws if kw]

def add_pending_keywords(course_id: str, keywords: list[str]):
    """Đẩy các từ khóa mới do AI tự học vào vùng chờ duyệt (Pending)"""
    db = get_db()
    # Lấy từ điển hiện tại để tránh trùng với từ đã có
    dict_doc = db["dictionaries"].find_one({"course_id": course_id})
    if not dict_doc:
        return

    existing_core = set([k.lower() for k in dict_doc.get("core_keywords", [])])
    existing_learned = set([k.lower() for k in dict_doc.get("learned_keywords", [])])
    existing_pending = set([k.lower() for k in dict_doc.get("pending_keywords", [])])
    
    new_filtered = []
    for kw in keywords:
        kw_clean = kw.strip().lower()
        if (kw_clean and 
            kw_clean not in existing_core and 
            kw_clean not in existing_learned and 
            kw_clean not in existing_pending):
            new_filtered.append(kw.strip()) # Giữ nguyên format chữ để hiển thị

    if new_filtered:
        db["dictionaries"].update_one(
            {"course_id": course_id},
            {
                "$push": {"pending_keywords": {"$each": new_filtered}},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )

def save_generated_questions(document_id: str, questions: list) -> int:
    """Lưu danh sách câu hỏi AI sinh ra vào collection 'questions'"""
    # [QUAN TRỌNG NHẤT]: Gọi get_db() để lấy kết nối tới MongoDB
    db = get_db() 
    
    if not questions:
        return 0

    docs_to_insert = []
    for q in questions:
        # q lúc này đã là dạng dict (do lệnh model_dump() ở service)
        q_dict = dict(q) 
        q_dict["document_id"] = str(document_id)
        q_dict["created_at"] = datetime.utcnow()
        q_dict["status"] = "pending" # Trạng thái chờ giảng viên duyệt
        docs_to_insert.append(q_dict)
        
    try:
        if docs_to_insert:
            result = db["questions"].insert_many(docs_to_insert)
            return len(result.inserted_ids)
        return 0
    except Exception as e:
        print(f"Lỗi Insert MongoDB: {e}")
        raise e