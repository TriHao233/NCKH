import json
import re
import logging
from typing import List
from app.models.schemas import (
    QuestionGenerateRequest, 
    QuestionGenerateResponse, 
    GeneratedQuestion
)
# Sử dụng PromptBuilder từ kiến trúc mới
from app.services.generation.prompt_builder import PromptBuilder
from app.services.rag.search import get_context_for_generation
from app.services.llm.factory import get_llm_service
from app.db.mongodb import save_generated_questions

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

def _validate_and_format(questions: list, req: QuestionGenerateRequest) -> List[GeneratedQuestion]:
    """Validate dữ liệu và ép kiểu về model chuẩn"""
    formatted = []
    for item in questions:
        # Cập nhật metadata đảm bảo nhất quán
        item.update({
            "question_type": req.question_type.value,
            "bloom_level": req.bloom_level.value
        })
        # Phải đưa append vào TRONG vòng lặp
        formatted.append(GeneratedQuestion(**item))
        
    return formatted