from fastapi import APIRouter, Depends, HTTPException

from core.config import settings
import logging
from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.generation.schemas import QuestionGenerateRequest, QuestionGenerateResponse
from modules.generation.question import generate_questions_rag

logger = logging.getLogger(__name__)
router = APIRouter(prefix=f"{settings.api_prefix}/generate", tags=["generation"])

@router.post("/questions", response_model=QuestionGenerateResponse, summary="Sinh câu hỏi tự động từ hệ thống RAG")
async def api_generate_questions(
    req: QuestionGenerateRequest,
    current_user: CurrentUser = Depends(require_teacher_or_admin),
):
    try:
        # Chuyển hướng yêu cầu vào luồng RAG
        result = await generate_questions_rag(req, requested_by_user_id=current_user.id)
        return result
    except ValueError as ve:
        logger.warning(f"Lỗi truy xuất dữ liệu RAG: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Lỗi hệ thống LLM")
        raise HTTPException(status_code=500, detail="Không thể sinh câu hỏi lúc này, vui lòng thử lại.")
