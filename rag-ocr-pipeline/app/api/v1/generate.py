from fastapi import APIRouter, HTTPException
import logging
from app.models.schemas import QuestionGenerateRequest, QuestionGenerateResponse
from app.services.generation.question import generate_questions_rag

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/generate", tags=["generation"])

@router.post("/questions", response_model=QuestionGenerateResponse, summary="Sinh câu hỏi tự động từ hệ thống RAG")
async def api_generate_questions(req: QuestionGenerateRequest):
    try:
        # Chuyển hướng yêu cầu vào luồng RAG
        result = await generate_questions_rag(req)
        return result
    except ValueError as ve:
        logger.warning(f"Lỗi truy xuất dữ liệu RAG: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Lỗi hệ thống LLM")
        raise HTTPException(status_code=500, detail="Không thể sinh câu hỏi lúc này, vui lòng thử lại.")