import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_CANDIDATES = (
    BASE_DIR / ".env",
    BASE_DIR.parent / ".env",
    BASE_DIR.parent / "rag-ocr-pipeline" / ".env",
)
for env_file in ENV_CANDIDATES:
    if env_file.exists():
        load_dotenv(env_file, override=False)


def _env_first(names: tuple[str, ...], default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "QBankCTU API")
    app_version: str = os.getenv("APP_VERSION", "0.1.0")
    app_env: str = os.getenv("APP_ENV", "production").strip().lower()
    demo_mode: bool = _env_bool(
        "DEMO_MODE",
        os.getenv("APP_ENV", "production").strip().lower() == "demo",
    )
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            os.getenv(
                "ALLOWED_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ),
        ).split(",")
        if origin.strip()
    ]
    allowed_hosts: list[str] = [
        host.strip()
        for host in os.getenv(
            "ALLOWED_HOSTS",
            "localhost,127.0.0.1,testserver",
        ).split(",")
        if host.strip()
    ]
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")

    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    auth_db_name: str = os.getenv("AUTH_DB_NAME", "NCKH")
    rag_db_name: str = os.getenv(
        "RAG_DB_NAME",
        os.getenv("DB_NAME", "rag_database"),
    )
    mongo_connect_timeout_ms: int = int(os.getenv("MONGO_CONNECT_TIMEOUT_MS", "10000"))
    require_mongo_transactions: bool = _env_bool(
        "REQUIRE_MONGO_TRANSACTIONS",
        os.getenv("APP_ENV", "production").strip().lower() in {"production", "staging"},
    )
    job_recovery_timeout_minutes: int = int(os.getenv("JOB_RECOVERY_TIMEOUT_MINUTES", "120"))
    job_worker_poll_seconds: float = float(os.getenv("JOB_WORKER_POLL_SECONDS", "1"))
    job_lease_seconds: int = int(os.getenv("JOB_LEASE_SECONDS", "120"))
    job_heartbeat_seconds: int = int(os.getenv("JOB_HEARTBEAT_SECONDS", "30"))
    job_max_attempts: int = int(os.getenv("JOB_MAX_ATTEMPTS", "3"))
    job_retry_base_seconds: int = int(os.getenv("JOB_RETRY_BASE_SECONDS", "5"))
    job_retry_max_seconds: int = int(os.getenv("JOB_RETRY_MAX_SECONDS", "300"))
    max_active_generation_jobs_per_user: int = int(os.getenv("MAX_ACTIVE_GENERATION_JOBS_PER_USER", "10"))
    worker_shutdown_grace_seconds: int = int(os.getenv("WORKER_SHUTDOWN_GRACE_SECONDS", "30"))
    job_retention_days: int = int(os.getenv("JOB_RETENTION_DAYS", "90"))
    llm_slot_lease_seconds: int = int(os.getenv("LLM_SLOT_LEASE_SECONDS", "90"))
    llm_slot_heartbeat_seconds: int = int(os.getenv("LLM_SLOT_HEARTBEAT_SECONDS", "15"))
    llm_slot_wait_timeout_seconds: int = int(os.getenv("LLM_SLOT_WAIT_TIMEOUT_SECONDS", "600"))
    llm_slot_poll_seconds: float = float(os.getenv("LLM_SLOT_POLL_SECONDS", "0.5"))
    ollama_max_concurrency: int = int(os.getenv("OLLAMA_MAX_CONCURRENCY", "1"))
    gemini_max_concurrency: int = int(os.getenv("GEMINI_MAX_CONCURRENCY", "5"))
    review_lock_timeout_minutes: int = int(os.getenv("REVIEW_LOCK_TIMEOUT_MINUTES", "30"))
    inference_policy: str = os.getenv("INFERENCE_POLICY", "LOCAL_ONLY").strip().upper()
    local_inference_allowed_hosts: list[str] = [
        host.strip().lower()
        for host in os.getenv(
            "LOCAL_INFERENCE_ALLOWED_HOSTS",
            "localhost,127.0.0.1,::1,host.docker.internal,ollama",
        ).split(",")
        if host.strip()
    ]

    firebase_credentials_path: str = os.getenv(
        "FIREBASE_CREDENTIALS_PATH", str(BASE_DIR / "firebase-service-account.json")
    )
    demo_admin_email: str = os.getenv("DEMO_ADMIN_EMAIL", "admin@qbankctu.edu.vn")
    demo_admin_password: str = os.getenv("DEMO_ADMIN_PASSWORD", "")
    demo_reviewer_email: str = os.getenv("DEMO_REVIEWER_EMAIL", "reviewer@qbankctu.edu.vn")
    demo_reviewer_password: str = os.getenv("DEMO_REVIEWER_PASSWORD", "")

    # Provider LLM mặc định (qwen chạy local qua Ollama)
    model_provider: str = os.getenv("MODEL_PROVIDER", "qwen")
    code_generation_model_provider: str = os.getenv(
        "CODE_GENERATION_MODEL_PROVIDER", "deepseek"
    ).strip()
    evaluation_model_provider: str = _env_first(
        ("EVALUATION_MODEL_PROVIDER", "EVALUATOR_MODEL_CODE"),
        "qwen",
    )
    generation_fallback_provider: str = os.getenv("GENERATION_FALLBACK_PROVIDER", "").strip()
    evaluation_fallback_provider: str = os.getenv("EVALUATION_FALLBACK_PROVIDER", "").strip()
    evaluation_num_predict: int = int(os.getenv("EVALUATION_NUM_PREDICT", "900"))
    ollama_generate_url: str = _env_first(
        ("OLLAMA_GENERATE_URL", "OLLAMA_BASE_URL"),
        "http://localhost:11434/api/generate",
    )
    ollama_timeout_seconds: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
    ollama_num_ctx: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    ollama_num_predict: int = int(os.getenv("OLLAMA_NUM_PREDICT", "900"))
    ollama_temperature: float = float(os.getenv("OLLAMA_TEMPERATURE", "0"))
    qwen_model_name: str = os.getenv("QWEN_MODEL_NAME", "qwen2.5:7b").strip()
    deepseek_model_name: str = _env_first(("DEEPSEEK_MODEL_NAME",), "deepseek-r1")
    deepseek_timeout_seconds: float = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "180"))
    deepseek_num_predict: int = int(os.getenv("DEEPSEEK_NUM_PREDICT", "900"))
    deepseek_temperature: float = float(os.getenv("DEEPSEEK_TEMPERATURE", "0"))

    chunk_size_default: int = int(os.getenv("CHUNK_SIZE_DEFAULT", "1000"))
    chunk_size_min: int = int(os.getenv("CHUNK_SIZE_MIN", "200"))
    chunk_size_max: int = int(os.getenv("CHUNK_SIZE_MAX", "4000"))

    chunk_overlap_default: int = int(os.getenv("CHUNK_OVERLAP_DEFAULT", "150"))
    chunk_overlap_min: int = int(os.getenv("CHUNK_OVERLAP_MIN", "0"))
    chunk_overlap_max: int = int(os.getenv("CHUNK_OVERLAP_MAX", "800"))

    chunk_buffer_max_pages: int = int(os.getenv("CHUNK_BUFFER_MAX_PAGES", "30"))
    chunk_buffer_max_chars: int = int(os.getenv("CHUNK_BUFFER_MAX_CHARS", "200000"))
    max_code_block_lines: int = int(os.getenv("MAX_CODE_BLOCK_LINES", "50"))
    chunk_token_budget_default: int = int(os.getenv("CHUNK_TOKEN_BUDGET_DEFAULT", "384"))
    retrieval_context_token_budget: int = int(
        os.getenv("RETRIEVAL_CONTEXT_TOKEN_BUDGET", "2200")
    )
    evaluation_source_token_budget: int = int(
        os.getenv("EVALUATION_SOURCE_TOKEN_BUDGET", "1800")
    )
    code_sandbox_enabled: bool = _env_bool("CODE_SANDBOX_ENABLED", True)
    code_sandbox_cpp_compiler: str = os.getenv("CODE_SANDBOX_CPP_COMPILER", "g++")
    code_sandbox_timeout_seconds: int = int(os.getenv("CODE_SANDBOX_TIMEOUT_SECONDS", "4"))
    code_sandbox_max_source_bytes: int = int(
        os.getenv("CODE_SANDBOX_MAX_SOURCE_BYTES", "12000")
    )
    retrieval_lexical_candidate_limit: int = int(
        os.getenv("RETRIEVAL_LEXICAL_CANDIDATE_LIMIT", "500")
    )

    pdf_max_pages: int = int(os.getenv("PDF_MAX_PAGES", "500"))
    pdf_render_timeout_seconds: int = int(os.getenv("PDF_RENDER_TIMEOUT_SECONDS", "120"))
    ocr_dpi: int = int(os.getenv("OCR_DPI", "300"))
    ocr_max_page_pixels: int = int(os.getenv("OCR_MAX_PAGE_PIXELS", "40000000"))
    ocr_text_layer_min_chars: int = int(os.getenv("OCR_TEXT_LAYER_MIN_CHARS", "80"))
    ocr_text_layer_min_alnum_ratio: float = float(
        os.getenv("OCR_TEXT_LAYER_MIN_ALNUM_RATIO", "0.45")
    )

    chromadb_collection_name: str = os.getenv("CHROMADB_COLLECTION_NAME", "chunks")
    chromadb_batch_size: int = int(os.getenv("CHROMADB_BATCH_SIZE", "50"))
    embedding_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    gpu_scheduling_profile: str = os.getenv(
        "GPU_SCHEDULING_PROFILE", "single_local_inference"
    ).strip()

    chromadb_path: str = os.getenv("CHROMADB_PATH", "./data/chroma_data")
    output_dir: str = os.getenv("OUTPUT_DIR", "./data/outputs")
    metadata_dir: str = os.getenv("METADATA_DIR", "./data/metadata")
    chunk_output_dir: str = os.getenv("CHUNK_OUTPUT_DIR", "./data/chunk_outputs")
    upload_dir: str = os.getenv("UPLOAD_DIR", "./data/uploads")
    ocr_output_dir: str = os.getenv("OCR_OUTPUT_DIR", "./data/ocr_outputs")

    prompts_dir: str = os.getenv("PROMPTS_DIR", "./prompts")
    prompt_source: str = os.getenv("PROMPT_SOURCE", "file").strip().lower()

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model_name: str = _env_first(
        ("GEMINI_MODEL_NAME", "DEFAULT_MODEL"),
        "gemini-2.0-flash",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def resolve_path(relative: str | Path) -> Path:
    """Quy đổi 1 đường dẫn tương đối (trong Settings) thành đường dẫn tuyệt đối, luôn tính từ backend/ (BASE_DIR)."""
    return (BASE_DIR / relative).resolve()
