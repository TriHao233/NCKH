from datetime import datetime

from bson.errors import InvalidId
from bson.objectid import ObjectId

from core.database import get_rag_db


def save_generated_questions(document_id: str, questions: list) -> int:
    """Lưu danh sách câu hỏi AI sinh ra vào collection 'questions'"""
    db = get_rag_db()

    if not questions:
        return 0

    docs_to_insert = []
    for q in questions:
        q_dict = dict(q)
        q_dict["document_id"] = str(document_id)
        q_dict["created_at"] = datetime.utcnow()
        q_dict["status"] = "pending"
        docs_to_insert.append(q_dict)

    try:
        if docs_to_insert:
            result = db["questions"].insert_many(docs_to_insert)
            return len(result.inserted_ids)
        return 0
    except Exception as e:
        print(f"Lỗi Insert MongoDB: {e}")
        raise e


def create_generation_job(request: dict) -> str:
    """Tạo job sinh câu hỏi với trạng thái queued."""
    db = get_rag_db()
    now = datetime.utcnow()
    doc = {
        "request": request,
        "status": "queued",
        "result": None,
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    result = db["generation_jobs"].insert_one(doc)
    return str(result.inserted_id)


def update_generation_job(
    job_id: str,
    status: str,
    result: dict | None = None,
    error_message: str | None = None,
):
    """Cập nhật trạng thái job sinh câu hỏi."""
    db = get_rag_db()
    update_data: dict = {
        "status": status,
        "updated_at": datetime.utcnow(),
    }
    if result is not None:
        update_data["result"] = result
    if error_message is not None:
        update_data["error_message"] = error_message

    db["generation_jobs"].update_one({"_id": ObjectId(job_id)}, {"$set": update_data})


def get_generation_job(job_id: str) -> dict | None:
    """Lấy thông tin job sinh câu hỏi theo job_id."""
    db = get_rag_db()
    try:
        doc = db["generation_jobs"].find_one({"_id": ObjectId(job_id)})
    except InvalidId:
        return None

    if not doc:
        return None

    doc["job_id"] = str(doc.pop("_id"))
    return doc


def validate_document_ready_for_generation(document_id: str) -> None:
    """Kiểm tra document đã OCR và chunk xong trước khi enqueue generate."""
    try:
        oid = ObjectId(document_id)
    except InvalidId as exc:
        raise ValueError("document_id không hợp lệ") from exc

    db = get_rag_db()
    doc = db["documents"].find_one({"_id": oid})
    if not doc:
        raise ValueError("Không tìm thấy document_id trong hệ thống")

    ocr_status = doc.get("status")
    if ocr_status != "completed":
        raise ValueError(f"Tài liệu chưa OCR xong (status={ocr_status})")

    chunk_status = doc.get("chunk_status")
    if chunk_status != "completed":
        raise ValueError(f"Tài liệu chưa chunk xong (chunk_status={chunk_status})")
