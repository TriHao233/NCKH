import asyncio
import os
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
DATA_DIR = BASE_DIR / "data"
INPUT_PDF = DATA_DIR / "inputs" / "Lap_Trinh_Can_Ban_TestOCR.pdf"

OUTPUT_DIRS = [
    DATA_DIR / "ocr_outputs",
    DATA_DIR / "chunk_outputs",
    DATA_DIR / "metadata",
    DATA_DIR / "uploads",
    DATA_DIR / "chroma_data",
]


def ensure_env() -> None:
    if "MONGO_URI" not in os.environ:
        # OLD: os.environ["MONGO_URI"] = "mongodb://localhost:27017/"
        if Path("/.dockerenv").exists():
            return
        os.environ["MONGO_URI"] = "mongodb://localhost:27017/"


def clean_data_dirs() -> None:
    for path in OUTPUT_DIRS:
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def clean_mongo(filename: str) -> None:
    from app.db.mongodb import get_db

    db = get_db()
    docs = list(db["documents"].find({"filename": filename}))
    if not docs:
        return

    doc_ids = [str(d["_id"]) for d in docs]
    db["pages"].delete_many({"document_id": {"$in": doc_ids}})
    db["questions"].delete_many({"document_id": {"$in": doc_ids}})
    db["documents"].delete_many({"_id": {"$in": [d["_id"] for d in docs]}})


async def generate_questions(document_id: str, model_provider: str) -> None:
    from app.models.schemas import BloomLevel, QuestionGenerateRequest, QuestionType
    from app.services.question_service import generate_questions_rag

    req = QuestionGenerateRequest(
        document_id=document_id,
        target_heading=None,
        bloom_level=BloomLevel.HIEU,
        question_type=QuestionType.TRAC_NGHIEM,
        num_questions=3,
        model_provider=model_provider,
    )
    result = await generate_questions_rag(req)
    print("Questions generated:")
    for idx, item in enumerate(result.data, 1):
        print(f"\n[{idx}] {item.question}")
        if item.options:
            for key, value in item.options.items():
                print(f"  {key}. {value}")
        print(f"Answer: {item.correct_answer}")
        print(f"Bloom: {item.bloom_level} | Type: {item.question_type}")


def main() -> int:
    ensure_env()

    if not INPUT_PDF.exists():
        print(f"Input PDF not found: {INPUT_PDF}")
        return 1

    print("Cleaning data directories...")
    clean_data_dirs()

    print("Cleaning MongoDB records for test file...")
    clean_mongo(INPUT_PDF.name)

    from app.core.config import settings
    from app.db.mongodb import create_document_record, save_document_pages, update_document_status
    from app.services.ocr_pipeline_service import run_ocr_pipeline
    from app.services.chunking_service import chunk_document_and_store

    title = INPUT_PDF.stem.replace("_", " ")
    document_id = create_document_record(filename=INPUT_PDF.name, title=title)

    output_path = DATA_DIR / "ocr_outputs" / f"{document_id}_result.md"
    print("Running OCR pipeline...")
    result = run_ocr_pipeline(
        pdf_path=str(INPUT_PDF),
        output_path=str(output_path),
        document_title=title,
        languages=["vi", "en"],
        gpu=None,
        poppler_path=os.environ.get("POPPLER_PATH"),
    )

    save_document_pages(document_id, result["pages"])
    update_document_status(document_id, status="completed", stats=result["stats"])

    print("Running chunking...")
    chunk_document_and_store(
        document_id=document_id,
        chunk_size=settings.chunk_size_default,
        chunk_overlap=settings.chunk_overlap_default,
        collection_name=settings.chromadb_collection_name,
        buffer_max_pages=settings.chunk_buffer_max_pages,
        buffer_max_chars=settings.chunk_buffer_max_chars,
        max_code_block_lines=settings.max_code_block_lines,
        dry_run=False,
    )

    model_provider = os.environ.get("MODEL_PROVIDER", "gemini")
    print(f"Generating questions using provider: {model_provider}")
    asyncio.run(generate_questions(document_id, model_provider))

    print("E2E test completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
