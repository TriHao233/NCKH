from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from core.config import settings

StrategyLiteral = Literal["auto", "recursive", "semantic"]

class CourseMetadata(BaseModel):
    course_id: str
    course_name: Optional[str] = None
    module_id: Optional[str] = None
    module_name: Optional[str] = None
    lesson_id: Optional[str] = None

class ChunkItem(BaseModel):
    index: int
    chunk_id: str
    content: str
    metadata: Dict[str, Any]
    char_count: int

class ChunkingStats(BaseModel):
    original_length: int
    total_chunks: int
    junk_removed: int
    avg_chunk_size: float
    min_chunk_size: int
    max_chunk_size: int
    content_type_distribution: Dict[str, int]

class ChunkingResponse(BaseModel):
    document_id: str
    source: str
    total_chunks: int
    chunk_size: int
    chunk_overlap: int
    splitting_strategy: str
    chunks: List[ChunkItem]
    stats: ChunkingStats

class ChromaDBOutput(BaseModel):
    document_id: str
    ids: List[str]
    documents: List[str]
    metadatas: List[Dict[str, Any]]

class IngestFileResult(BaseModel):
    filename: Optional[str]
    document_id: str
    source: str
    collection_name: str
    course_id: str
    chapter_id: str
    chapter_name: Optional[str]
    lesson_id: str
    total_chunks: int
    total_chunks_stored: int
    splitting_strategy: str
    stats: ChunkingStats

class IngestFilesResponse(BaseModel):
    total_files: int
    processed_files: int
    failed_files: List[str]
    results: List[IngestFileResult]

class SearchRequest(BaseModel):
    query: str
    collection_name: str = "chunks"
    n_results: int = 5
    where: Optional[Dict[str, Any]] = None
    course_id: Optional[str] = None
    include_context: bool = False
    rerank_enabled: bool = True
    retrieval_k: Optional[int] = None

class SearchResult(BaseModel):
    ids: List[str]
    documents: List[str]
    metadatas: List[Dict[str, Any]]
    distances: List[float]
    normalized_query: Optional[str] = None
    retrieval_info: Optional[Dict[str, Any]] = None
    context_blocks: Optional[List[Dict[str, Any]]] = None

class CollectionInfo(BaseModel):
    name: str
    count: int
    documents: List[Dict[str, Any]]


class DocumentChunkRequest(BaseModel):
    document_id: str = Field(..., description="Document ID from MongoDB")
    collection_name: Optional[str] = Field(default=None, description="Target ChromaDB collection")
    chunk_size: int = Field(
        default=settings.chunk_size_default,
        ge=settings.chunk_size_min,
        le=settings.chunk_size_max,
    )
    chunk_overlap: int = Field(
        default=settings.chunk_overlap_default,
        ge=settings.chunk_overlap_min,
        le=settings.chunk_overlap_max,
    )
    buffer_max_pages: int = Field(default=settings.chunk_buffer_max_pages, ge=1, le=200)
    buffer_max_chars: int = Field(default=settings.chunk_buffer_max_chars, ge=1000, le=2000000)
    max_code_block_lines: int = Field(default=settings.max_code_block_lines, ge=10, le=500)
    chunk_token_budget: int = Field(
        default=settings.chunk_token_budget_default,
        ge=64,
        le=2048,
        description="Soft token budget; protected code/table/formula blocks are never truncated.",
    )
    dry_run: bool = Field(default=False, description="Skip embedding and storage")


class DocumentChunkResponse(BaseModel):
    document_id: str
    chunk_job_id: Optional[str] = None
    chunk_set_id: Optional[str] = None
    vector_collection_id: Optional[str] = None
    collection_name: str
    total_chunks: int
    stored_chunks: int
    stats: ChunkingStats


class IndexRollbackRequest(BaseModel):
    expected_manifest_id: str = Field(..., min_length=24, max_length=24)


class IndexRollbackResponse(BaseModel):
    document_id: str
    active_manifest_id: str
    vector_collection_id: str
    rolled_back_manifest_id: str
