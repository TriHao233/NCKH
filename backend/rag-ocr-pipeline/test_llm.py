import asyncio
import sys
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.services.generation.prompt_builder import PromptBuilder
from app.services.llm.factory import get_llm_service
from app.services.generation.question import _clean_llm_output

async def run_test():
    context = """
    Danh sách liên kết (Linked List) là một cấu trúc dữ liệu tuyến tính, trong đó các phần tử không được lưu trữ ở các vị trí nhớ liên tiếp. Thay vào đó, mỗi phần tử (node) chứa dữ liệu và một con trỏ (pointer) trỏ đến phần tử tiếp theo. Ưu điểm của danh sách liên kết là kích thước động và dễ dàng chèn/xóa phần tử mà không cần dịch chuyển bộ nhớ. Nhược điểm là tốn thêm bộ nhớ cho con trỏ và không hỗ trợ truy cập ngẫu nhiên (phải duyệt từ đầu danh sách).
    """
    
    test_cases = [
        {"bloom": "nho", "type": "trac_nghiem", "num": 1},
        {"bloom": "hieu", "type": "trac_nghiem", "num": 1},
        {"bloom": "van_dung", "type": "tinh_huong", "num": 1}
    ]
    
    provider = "qwen" 
    llm = get_llm_service(provider)
    builder = PromptBuilder()

    print(f"=== ĐANG CHẠY TEST LLM VỚI PROVIDER: {provider.upper()} ===\n")

    for case in test_cases:
        print(f"[*] Testing -> Bloom: {case['bloom'].upper()} | Type: {case['type']} ...")
        prompt = builder.build(context, case['bloom'], case['type'], case['num'])
        
        raw_res = ""
        try:
            raw_res = await llm.generate_text(prompt)
            clean_res = _clean_llm_output(raw_res)
            parsed = json.loads(clean_res)
            
            # Giả định cấu trúc JSON có key "questions" như trong question.py của bạn
            questions = parsed.get("questions", [])
            if questions:
                print(f"    - Câu hỏi: {questions[0]['question']}")
                print(f"    - Đáp án: {questions[0]['correct_answer']}")
            print("-" * 50)
            
        except Exception as e:
            print(f"    ❌ LỖI: {str(e)}")
            if raw_res:
                print(f"    Raw Output: {raw_res[:200]}...")

if __name__ == "__main__":
    asyncio.run(run_test())