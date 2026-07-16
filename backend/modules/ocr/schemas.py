from typing import List, Optional
from pydantic import BaseModel, Field

class OCRPage(BaseModel):
    page_number: int
    text: str
    original_text: Optional[str] = None
    formula_blocks: Optional[List[str]] = Field(default_factory=list)

class OCRStats(BaseModel):
    total_pages: int
    total_chars: int
    avg_chars_per_page: int
    processing_time: Optional[float] = None

class OCRRunRequest(BaseModel):
    pdf_path: str
    output_path: Optional[str] = None
    document_title: Optional[str] = None
    languages: Optional[List[str]] = Field(default_factory=lambda: ["vi", "en"])
    gpu: Optional[bool] = None
    poppler_path: Optional[str] = None

class OCRRunResponse(BaseModel):
    pages: List[OCRPage]
    output_file: str
    stats: OCRStats

class OCRUploadResponse(BaseModel):
    filename: str
    download_filename: str
    stats: OCRStats
    pages: List[OCRPage]
    text: str

class OCRChunkRequest(BaseModel):
    pdf_path: str
    chunk_size: int = 500
    chunk_overlap: int = 100
    enable_ner: bool = True
    source: str = "unknown"
    splitting_strategy: str = "auto"

class OCRChunkResponse(BaseModel):
    ocr: OCRRunResponse
    chunking: dict  # Sẽ map với ChunkingResponse sau
