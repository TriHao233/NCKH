import json
import re
import logging
from typing import List

from modules.generation.schemas import (
    QuestionGenerateRequest,
    QuestionGenerateResponse,
    GeneratedQuestion
)
from modules.generation.prompt_builder import PromptBuilder
from modules.rag.search import get_context_for_generation
from modules.generation.llm.factory import get_llm_service
from modules.generation.repository import save_generated_questions

logger = logging.getLogger(__name__)

async def generate_questions_rag(req: QuestionGenerateRequest) -> QuestionGenerateResponse:
    logger.info(f"Sinh câu hỏi [Doc: {req.document_id} | Type: {req.question_type.value}]")

    # 1. Truy xuất ngữ cảnh (RAG)
    context_text = get_context_for_generation(
        document_id=req.document_id,
        collection_name=req.collection_name,
        target_heading=req.target_heading
    )

    if not context_text:
        raise ValueError("Không tìm thấy đủ dữ liệu tri thức để sinh câu hỏi.")

    # 2. Xây dựng Prompt thông qua hệ thống file-based
    prompt_builder = PromptBuilder()
    full_prompt = prompt_builder.build(
        context=context_text,
        bloom_level=req.bloom_level.value,
        question_type=req.question_type.value,
        num_questions=req.num_questions
    )

    # 3. Gọi LLM
    llm = get_llm_service(req.model_provider)
    raw_response = await llm.generate_text(full_prompt)

    # 4. Làm sạch và Parse JSON
    clean_json_str = _clean_llm_output(raw_response)

    try:
        parsed_data = json.loads(clean_json_str)
        questions_list = _extract_questions_list(parsed_data)

        if not questions_list:
            raise ValueError("LLM không trả về danh sách câu hỏi hợp lệ.")

        # Cắt nếu AI sinh thừa
        questions_list = questions_list[:req.num_questions]

        # Validate và đóng gói
        validated_data = _validate_and_format(questions_list, req)

        # 5. Lưu vào DB
        save_generated_questions(req.document_id, [q.model_dump() for q in validated_data])

        return QuestionGenerateResponse(status="success", data=validated_data)

    except json.JSONDecodeError:
        logger.error(f"Parse JSON lỗi: {clean_json_str}")
        raise Exception("Định dạng phản hồi từ LLM không hợp lệ.")

def _clean_llm_output(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'```json|```', '', text)
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    return match.group(1) if match else text.strip()

def _extract_questions_list(data: dict | list) -> list:
    if isinstance(data, list): return data
    return data.get("questions") or data.get("data") or []

def _check_type_format(item: dict, question_type: str) -> str | None:
    """Kiểm tra cấu trúc bắt buộc theo từng loại câu hỏi (xem app/prompts/question_type/*.txt).
    Trả về lý do lỗi nếu vi phạm, None nếu hợp lệ."""
    options = item.get("options")
    correct_answer = item.get("correct_answer") or ""

    if question_type == "dien_khuyet":
        if "_____" not in (item.get("question") or ""):
            return "dien_khuyet thiếu placeholder '_____' trong câu hỏi"
        if options is not None:
            return "dien_khuyet phải có options = null"

    elif question_type == "dung_sai":
        if not isinstance(options, dict) or set(options.keys()) != {"A", "B"}:
            return "dung_sai phải có đúng 2 lựa chọn A/B"

    elif question_type in ("trac_nghiem", "tinh_huong", "nhieu_lua_chon"):
        if not isinstance(options, dict) or set(options.keys()) != {"A", "B", "C", "D"}:
            return f"{question_type} phải có đúng 4 lựa chọn A/B/C/D"
        if question_type == "nhieu_lua_chon":
            correct_keys = [c.strip() for c in correct_answer.split(",") if c.strip()]
            if len(correct_keys) < 2:
                return "nhieu_lua_chon phải có ít nhất 2 đáp án đúng"

    elif question_type == "ghep_cot":
        if not isinstance(options, dict):
            return "ghep_cot phải có options dạng object"
        numeric_keys = [k for k in options if str(k).isdigit()]
        alpha_keys = [k for k in options if str(k).isalpha()]
        if len(numeric_keys) < 3 or len(alpha_keys) < len(numeric_keys) + 1:
            return "ghep_cot cần tối thiểu 3 mục đánh số và số mục chữ phải nhiều hơn số mục số ít nhất 1 (distractor)"
        if not re.search(r"\d+\s*-\s*[a-zA-Z]", correct_answer):
            return "ghep_cot: correct_answer phải theo định dạng '1-b, 2-a, ...'"

    elif question_type == "sap_xep":
        if not isinstance(options, dict) or len(options) < 4:
            return "sap_xep cần tối thiểu 4 bước trong options"
        correct_keys = [c.strip() for c in correct_answer.split(",") if c.strip()]
        if sorted(correct_keys) != sorted(str(k) for k in options.keys()):
            return "sap_xep: correct_answer phải liệt kê đủ và đúng các khóa trong options theo thứ tự"

    return None


def _validate_and_format(questions: list, req: QuestionGenerateRequest) -> List[GeneratedQuestion]:
    """Validate dữ liệu và ép kiểu về model chuẩn. Loại bỏ các câu hỏi không đúng
    cấu trúc bắt buộc của question_type thay vì lưu dữ liệu hỏng vào ngân hàng câu hỏi."""
    formatted = []
    for item in questions:
        error = _check_type_format(item, req.question_type.value)
        if error:
            logger.warning(f"Bỏ qua câu hỏi sai định dạng ({req.question_type.value}): {error} | item={item}")
            continue

        # Cập nhật metadata đảm bảo nhất quán
        item.update({
            "question_type": req.question_type.value,
            "bloom_level": req.bloom_level.value
        })
        formatted.append(GeneratedQuestion(**item))

    if not formatted:
        raise ValueError("Tất cả câu hỏi LLM sinh ra đều không đúng định dạng yêu cầu, vui lòng thử lại.")

    return formatted
