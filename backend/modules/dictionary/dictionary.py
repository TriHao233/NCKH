import json
import logging

import httpx
from bson import ObjectId

from core.config import settings
from core.database import get_rag_db
from modules.dictionary.mongodb import add_pending_keywords

logger = logging.getLogger(__name__)


def _document_page_query(document_id: str) -> dict:
    try:
        return {"document_id": ObjectId(document_id)}
    except Exception:
        return {"document_id": document_id}


async def run_dictionary_auto_learning(document_id: str, course_id: str = "it_fundamentals"):
    """
    Hàm phân tích tài liệu ngầm: Trích xuất các đoạn văn đặc sắc,
    gọi AI để học từ khóa mới và đưa vào vùng chờ duyệt.
    """
    logger.info(f"==> Bắt đầu tiến trình Auto-Learning cho Document: {document_id}")
    db = get_rag_db()

    # 1. Lấy tối đa 15 trang V2 để làm mẫu học từ khóa.
    pages_cursor = (
        db.document_pages.find(_document_page_query(document_id))
        .sort("page_number", 1)
        .limit(15)
    )

    sample_texts = []
    for page in pages_cursor:
        text = (page.get("cleaned_text") or page.get("raw_text") or "").strip()
        if len(text) > 200:  # Bỏ qua trang quá ngắn như trang bìa, mục lục trống
            sample_texts.append(text[:1500])  # Giới hạn ký tự mỗi trang để tránh tràn Context Window bừa bãi

    if not sample_texts:
        logger.warning("Không tìm thấy văn bản đủ điều kiện để học từ khóa.")
        return

    combined_text = "\n--- TRANG MẪU ---\n".join(sample_texts)

    # 2. Xây dựng cấu trúc Prompt chuyên sâu ép cấu trúc JSON đầu ra
    prompt = f"""
Bạn là một chuyên gia tối ưu hóa hệ thống thông tin và xử lý ngôn ngữ tự nhiên (NLP) cho lĩnh vực Công nghệ thông tin.
Nhiệm vụ của bạn là đọc kỹ đoạn văn bản trích dẫn từ giáo trình dưới đây và trích xuất ra các "Thuật ngữ chuyên ngành cốt lõi" (Technical Keywords/Phrases).

Mục tiêu của các từ khóa này là giúp hệ thống RAG đo lường chính xác mật độ tri thức của văn bản.

Yêu cầu trích xuất:
1. Từ khóa phải là thuật ngữ kỹ thuật chuyên sâu (Ví dụ: "con trỏ", "mảng động", "độ phức tạp thuật toán", "bộ nhớ đệm", "bảng băm", "danh sách liên kết").
2. Chấp nhận cả thuật ngữ tiếng Việt thông dụng và tiếng Anh chuẩn kỹ thuật.
3. KHÔNG lấy các từ ngữ đời sống phổ thông hoặc từ nối (Ví dụ: "chương trình", "máy tính", "sử dụng", "thực hiện" -> KHÔNG LẤY).
4. Kết quả TRẢ VỀ DUY NHẤT một mảng JSON thuần túy gồm các chuỗi (Array of Strings), không bao gồm ký tự markdown ```json hay giải thích gì thêm.

VĂN BẢN GIÁO TRÌNH:
{combined_text}

JSON KẾT QUẢ ĐÚNG FORMAT MẪU:
["từ khóa 1", "từ khóa 2", "từ khóa 3"]
"""


    try:
        # 3. Sử dụng factory chung của hệ thống để gọi LLM
        from modules.generation.llm.factory import get_llm_service
        llm = get_llm_service()

        raw_ai_text = await llm.generate_text(prompt)

        # Làm sạch chuỗi trả về để tránh lỗi parse JSON do dính markdown
        cleaned_text = raw_ai_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()

        # Parse mảng từ khóa từ AI
        parsed_data = json.loads(cleaned_text)

        # Nếu AI trả về dict dạng {"keywords": [...]}, ta trích xuất mảng bên trong
        if isinstance(parsed_data, dict):
            for key, val in parsed_data.items():
                if isinstance(val, list):
                    parsed_data = val
                    break

        extracted_keywords = parsed_data

        if isinstance(extracted_keywords, list):
            # Lọc bỏ những thứ không phải string
            extracted_keywords = [str(k) for k in extracted_keywords if isinstance(k, str) or isinstance(k, int)]
            logger.info(f"AI đã học được {len(extracted_keywords)} từ khóa tiềm năng: {extracted_keywords}")

            # 4. Đẩy vào MongoDB vùng chờ duyệt (Pending)
            add_pending_keywords(course_id=course_id, keywords=extracted_keywords)
            logger.info("Đã cập nhật bộ từ khóa vào trạng thái Chờ duyệt (Pending) thành công!")
        else:
            logger.error("Đầu ra của AI không phải định dạng List chuẩn.")

    except json.JSONDecodeError as e:
        logger.error(f"Lỗi parse JSON đầu ra của AI: {raw_ai_text} - {str(e)}")
    except Exception as e:
        logger.exception(f"Tiến trình Auto-Learning thất bại do sự cố: {str(e)}")
