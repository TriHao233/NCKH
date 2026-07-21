from datetime import datetime
from enum import Enum
from typing import List, Optional, Any
from pydantic import BaseModel, Field

from core.config import settings

class BloomLevel(str, Enum):
    NHO = "nho"
    HIEU = "hieu"
    VAN_DUNG = "van_dung"
    PHAN_TICH = "phan_tich"
    DANH_GIA = "danh_gia"
    SANG_TAO = "sang_tao"

class QuestionType(str, Enum):
    TRAC_NGHIEM = "trac_nghiem"
    DUNG_SAI = "dung_sai"
    DIEN_KHUYET = "dien_khuyet"
    GHEP_COT = "ghep_cot"
    TINH_HUONG = "tinh_huong"
    SAP_XEP = "sap_xep"
    NHIEU_LUA_CHON = "nhieu_lua_chon"

class QuestionGenerateRequest(BaseModel):
    # Xóa context: str, thay bằng document_id để gọi ChromaDB
    document_id: str = Field(..., description="ID của giáo trình trong DB")
    collection_name: str = "chunks"
    target_heading: Optional[str] = Field(None, description="Tên mục lục muốn giới hạn sinh câu hỏi")
    bloom_level: BloomLevel
    question_type: QuestionType = QuestionType.TRAC_NGHIEM
    num_questions: int = Field(default=1, ge=1, le=10)
    model_provider: str = Field(default_factory=lambda: settings.model_provider)

class GeneratedQuestion(BaseModel):
    question: str
    # Đổi sang Any để hỗ trợ JSON linh hoạt cho câu Ghép cột/Sắp xếp
    options: Optional[Any] = None
    correct_answer: str
    explanation: str
    question_type: str
    bloom_level: str
    source_context: str

class QuestionGenerateResponse(BaseModel):
    status: str
    data: List[GeneratedQuestion]


class GenerationJobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: GenerationJobStatus = GenerationJobStatus.QUEUED
    message: Optional[str] = None


class GenerationJobStatusResponse(BaseModel):
    job_id: str
    status: GenerationJobStatus
    data: Optional[List[GeneratedQuestion]] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
