import asyncio
import hashlib
import os
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
        os.environ["MONGO_URI"] = "mongodb://localhost:27017/"


def ensure_data_dirs() -> None:
    for path in OUTPUT_DIRS:
        path.mkdir(parents=True, exist_ok=True)


def clean_mongo(filename: str) -> None:
    from core.database import get_rag_db

    db = get_rag_db()
    docs = list(
        db["documents"].find(
            {
                "$or": [
                    {"original_filename": filename},
                    {"filename": filename},
                ]
            }
        )
    )
    if not docs:
        return

    doc_oids = [d["_id"] for d in docs]
    doc_ids = [str(d["_id"]) for d in docs]

    versions = list(db["question_versions"].find({"document_id": {"$in": doc_oids}}))
    question_oids = list({version["question_id"] for version in versions})
    chunk_sets = list(db["chunk_sets"].find({"document_id": {"$in": doc_oids}}))
    chunk_set_oids = [chunk_set["_id"] for chunk_set in chunk_sets]
    chunks = list(db["document_chunks"].find({"document_id": {"$in": doc_oids}}))
    chunk_oids = [chunk["_id"] for chunk in chunks]

    if question_oids:
        db["question_evaluations"].delete_many({"question_id": {"$in": question_oids}})
        db["question_reviews"].delete_many({"question_id": {"$in": question_oids}})
        db["moodle_publications"].delete_many({"question_id": {"$in": question_oids}})
        db["audit_logs"].delete_many({"entity.id": {"$in": question_oids}})
        db["questions"].delete_many({"_id": {"$in": question_oids}})
        db["question_versions"].delete_many({"question_id": {"$in": question_oids}})

    if chunk_set_oids or chunk_oids:
        db["chunk_embeddings"].delete_many(
            {
                "$or": [
                    {"chunk_set_id": {"$in": chunk_set_oids}},
                    {"chunk_id": {"$in": chunk_oids}},
                ]
            }
        )
    db["document_chunks"].delete_many({"document_id": {"$in": doc_oids}})
    db["chunk_sets"].delete_many({"document_id": {"$in": doc_oids}})
    db["document_pages"].delete_many({"document_id": {"$in": doc_oids}})
    db["document_jobs"].delete_many({"document_id": {"$in": doc_oids}})
    db["generation_jobs"].delete_many({"request.document_id": {"$in": doc_ids}})
    db["generation_runs"].delete_many({"document_id": {"$in": doc_oids}})
    db["pages"].delete_many({"document_id": {"$in": doc_ids}})
    db["documents"].delete_many({"_id": {"$in": doc_oids}})


async def generate_questions(document_id: str, model_provider: str) -> None:
    from bson import ObjectId
    from core.database import get_database
    from modules.generation.generate import process_generate_background
    from modules.generation.mongodb import create_generation_job, get_generation_job
    from modules.generation.schemas import BloomLevel, QuestionGenerateRequest, QuestionType

    question_type = QuestionType(os.environ.get("E2E_QUESTION_TYPE", QuestionType.DUNG_SAI.value))
    bloom_level = BloomLevel(os.environ.get("E2E_BLOOM_LEVEL", BloomLevel.HIEU.value))
    num_questions = max(1, min(10, int(os.environ.get("E2E_NUM_QUESTIONS", "2"))))
    instruction = (
        f"Tạo câu hỏi dạng {question_type.value} bám sát nội dung trong tài liệu test, "
        "tránh câu hỏi ngoài ngữ cảnh."
    )
    req = QuestionGenerateRequest(
        document_id=document_id,
        target_heading=instruction,
        instruction=instruction,
        bloom_level=bloom_level,
        question_type=question_type,
        num_questions=num_questions,
        model_provider=model_provider,
    )
    job_id = create_generation_job(req.model_dump(mode="json"))
    await process_generate_background(job_id)

    job = get_generation_job(job_id)
    if not job or job["status"] != "completed":
        error = job.get("error_message") if job else "Job not found"
        raise RuntimeError(f"Generation failed: {error}")

    result_data = job["result"]["data"]
    if not result_data:
        raise RuntimeError("Generation completed but returned no questions")

    db = get_database()
    question_oids = [ObjectId(item["question_id"]) for item in result_data if item.get("question_id")]
    saved_questions = list(db.questions.find({"_id": {"$in": question_oids}}))
    saved_versions = list(db.question_versions.find({"question_id": {"$in": question_oids}}))
    if len(saved_questions) != len(result_data) or len(saved_versions) != len(result_data):
        raise RuntimeError("Generated questions were not fully persisted in V2 collections")
    if any(question.get("review_status") != "DRAFT" for question in saved_questions):
        raise RuntimeError("Generated AI questions must start as DRAFT")
    if any(not version.get("sources") for version in saved_versions):
        raise RuntimeError("Generated AI question versions must keep source chunk snapshots")

    print("Questions generated:")
    for idx, item in enumerate(result_data, 1):
        print(f"\n[{idx}] {item['question']}")
        options = item.get("options")
        if options:
            if isinstance(options, dict):
                for key, value in options.items():
                    print(f"  {key}. {value}")
            else:
                print(f"  Options: {options}")
        print(f"Answer: {item['correct_answer']}")
        print(f"Bloom: {item['bloom_level']} | Type: {item['question_type']}")


def main() -> int:
    ensure_env()

    if not INPUT_PDF.exists():
        print(f"Input PDF not found: {INPUT_PDF}")
        return 1

    print("Ensuring data directories...")
    ensure_data_dirs()

    print("Cleaning MongoDB records for test file...")
    from core.bootstrap import bootstrap_database
    from core.database import ping_database

    ping_database()
    bootstrap_database()
    clean_mongo(INPUT_PDF.name)

    from core.config import settings
    from modules.ocr.mongodb import (
        attach_original_artifact,
        create_document_record,
        create_ocr_job,
        save_document_pages,
        update_document_status,
    )
    from modules.ocr.pipeline import run_ocr_pipeline
    from modules.rag.chunking import chunk_document_and_store

    title = INPUT_PDF.stem.replace("_", " ")
    document_id = create_document_record(filename=INPUT_PDF.name, title=title)
    ocr_job_id = create_ocr_job(document_id)
    digest = hashlib.sha256(INPUT_PDF.read_bytes()).hexdigest()
    attach_original_artifact(
        document_id,
        uri=str(INPUT_PDF),
        size_bytes=INPUT_PDF.stat().st_size,
        sha256=digest,
    )

    output_path = DATA_DIR / "ocr_outputs" / f"{document_id}_result.md"
    print("Running OCR pipeline...")
    update_document_status(document_id, ocr_job_id, status="processing")
    result = run_ocr_pipeline(
        pdf_path=str(INPUT_PDF),
        output_path=str(output_path),
        document_title=title,
        languages=["vi", "en"],
        gpu=None,
        poppler_path=os.environ.get("POPPLER_PATH"),
    )

    save_document_pages(document_id, ocr_job_id, result["pages"])
    update_document_status(document_id, ocr_job_id, status="completed", stats=result["stats"])

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

    model_provider = os.environ.get("MODEL_PROVIDER", settings.model_provider)
    print(f"Generating questions using provider: {model_provider}")
    asyncio.run(generate_questions(document_id, model_provider))

    print("E2E test completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
