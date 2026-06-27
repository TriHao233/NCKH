import os
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "RAG API")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # Thêm cấu hình Provider mặc định (mặc định là 'qwen' nếu không set trong .env)
    model_provider: str = os.getenv("MODEL_PROVIDER", "qwen")

    chunk_size_default: int = int(os.getenv("CHUNK_SIZE_DEFAULT", "1000"))
    chunk_size_min: int = int(os.getenv("CHUNK_SIZE_MIN", "200"))
    chunk_size_max: int = int(os.getenv("CHUNK_SIZE_MAX", "4000"))

    chunk_overlap_default: int = int(os.getenv("CHUNK_OVERLAP_DEFAULT", "150"))
    chunk_overlap_min: int = int(os.getenv("CHUNK_OVERLAP_MIN", "0"))
    chunk_overlap_max: int = int(os.getenv("CHUNK_OVERLAP_MAX", "800"))

    chunk_buffer_max_pages: int = int(os.getenv("CHUNK_BUFFER_MAX_PAGES", "30"))
    chunk_buffer_max_chars: int = int(os.getenv("CHUNK_BUFFER_MAX_CHARS", "200000"))
    max_code_block_lines: int = int(os.getenv("MAX_CODE_BLOCK_LINES", "50"))

    chromadb_collection_name: str = os.getenv("CHROMADB_COLLECTION_NAME", "chunks")
    chromadb_batch_size: int = int(os.getenv("CHROMADB_BATCH_SIZE", "50"))
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    
    chromadb_path: str = os.getenv("CHROMADB_PATH", "./data/chroma_data")
    output_dir: str = os.getenv("OUTPUT_DIR", "./data/outputs")
    metadata_dir: str = os.getenv("METADATA_DIR", "./data/metadata")
    chunk_output_dir: str = os.getenv("CHUNK_OUTPUT_DIR", "./data/chunk_outputs")
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gemini-2.0-flash")

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()