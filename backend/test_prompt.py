import sys
from pathlib import Path

# Thêm thư mục gốc vào sys.path để có thể import package 'app'
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from modules.generation.prompt_builder import PromptBuilder

def main():
    print("=== BẮT ĐẦU KIỂM TRA PROMPT BUILDER ===\n")

    # 1. Khởi tạo dữ liệu giả lập (Mock data)
    dummy_context = """
    Cấu trúc dữ liệu mảng (Array) là một tập hợp các phần tử có cùng kiểu dữ liệu, 
    được lưu trữ liên tiếp nhau trong bộ nhớ. Mảng cho phép truy cập ngẫu nhiên 
    đến bất kỳ phần tử nào thông qua chỉ số (index), thường bắt đầu từ 0. 
    Tuy nhiên, kích thước của mảng cố định sau khi khởi tạo và việc chèn/xóa 
    phần tử ở giữa mảng tốn nhiều thời gian do phải dịch chuyển các phần tử khác.
    """
    
    # Test case 1: Mức độ Hiểu - Trắc nghiệm 1 lựa chọn
    bloom_level = "hieu"           
    question_type = "trac_nghiem"  
    num_questions = 2

    # 2. Khởi tạo và chạy Builder
    try:
        print(f"Đang load prompt cho Bloom: '{bloom_level}', Type: '{question_type}'...\n")
        builder = PromptBuilder()
        
        final_prompt = builder.build(
            context=dummy_context.strip(),
            bloom_level=bloom_level,
            question_type=question_type,
            num_questions=num_questions
        )

        print("✅ Xây dựng Prompt THÀNH CÔNG! Nội dung Prompt gửi cho LLM sẽ là:\n")
        print("=" * 60)
        print(final_prompt)
        print("=" * 60)
        
    except FileNotFoundError as fnf:
        print(f"❌ LỖI KHÔNG TÌM THẤY FILE PROMPT: {fnf}")
        print("💡 Gợi ý: Kiểm tra lại xem bạn đã tạo đủ các file .txt trong thư mục app/prompts/ chưa.")
    except Exception as e:
        print(f"❌ CÓ LỖI XẢY RA: {e}")

if __name__ == "__main__":
    main()