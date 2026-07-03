import json
import logging
import httpx
from app.core.config import settings
from app.db.mongodb import get_db, add_pending_keywords

logger = logging.getLogger(__name__)

def run_dictionary_auto_learning(document_id: str, course_id: str = "it_fundamentals"):
    """
    Hàm phân tích tài liệu ngầm: Trích xuất các đoạn văn đặc sắc, 
    gọi AI để học từ khóa mới và đưa vào vùng chờ duyệt.
    """
    logger.info(f"==> Bắt đầu tiến trình Auto-Learning cho Document: {document_id}")
    db = get_db()
    
    # 1. Lấy ra tối đa 15 trang có mật độ chữ tốt hoặc có cấu trúc phức tạp để làm mẫu học toán
    # Sắp xếp theo thứ tự trang tăng dần để bảo toàn mạch kiến thức giáo trình
    # OLD: pages_cursor = db["pages"].find({"document_id": str(document_id)}).limit(15)
    pages_cursor = db["pages"].find({"document_id": str(document_id)}).sort("page_number", 1).limit(15)
    
    sample_texts = []
    for page in pages_cursor:
        text = page.get("text", "").strip()
        if len(text) > 200: # Bỏ qua trang quá ngắn như trang bìa, mục lục trống
            sample_texts.append(text[:1500]) # Giới hạn ký tự mỗi trang để tránh tràn Context Window bừa bãi
            
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

    # 3. Thực hiện gọi API trực tiếp tới Gemini 1.5 Flash (Nhanh, rẻ, chuẩn xác cho Task Extraction)
    api_key = settings.GEMINI_API_KEY.strip() if settings.GEMINI_API_KEY else ""

    if not api_key:
        logger.error("Thiếu cấu hình GEMINI_API_KEY trong file .env")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1 
        }
    }

    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(f"Gemini API phản hồi lỗi: {response.text}")
                return
                
            res_json = response.json()
            raw_ai_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # Parse mảng từ khóa từ AI
            extracted_keywords = json.loads(raw_ai_text)
            if isinstance(extracted_keywords, list):
                logger.info(f"AI đã học được {len(extracted_keywords)} từ khóa tiềm năng: {extracted_keywords}")
                
                # 4. Đẩy vào MongoDB vùng chờ duyệt (Pending)
                add_pending_keywords(course_id=course_id, keywords=extracted_keywords)
                logger.info("Đã cập nhật bộ từ khóa vào trạng thái Chờ duyệt (Pending) thành công!")
            else:
                logger.error("Đầu ra của AI không phải định dạng List chuẩn.")
                
    except Exception as e:
        logger.exception(f"Tiến trình Auto-Learning thất bại do sự cố: {str(e)}")