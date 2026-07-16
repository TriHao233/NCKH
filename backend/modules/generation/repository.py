from datetime import datetime

from core.database import get_rag_db


def save_generated_questions(document_id: str, questions: list) -> int:
    """Lưu danh sách câu hỏi AI sinh ra vào collection 'questions'"""
    db = get_rag_db()

    if not questions:
        return 0

    docs_to_insert = []
    for q in questions:
        # q lúc này đã là dạng dict (do lệnh model_dump() ở service)
        q_dict = dict(q)
        q_dict["document_id"] = str(document_id)
        q_dict["created_at"] = datetime.utcnow()
        q_dict["status"] = "pending"  # Trạng thái chờ giảng viên duyệt
        docs_to_insert.append(q_dict)

    try:
        if docs_to_insert:
            result = db["questions"].insert_many(docs_to_insert)
            return len(result.inserted_ids)
        return 0
    except Exception as e:
        print(f"Lỗi Insert MongoDB: {e}")
        raise e
