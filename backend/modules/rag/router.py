import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool

from modules.dictionary.service import run_dictionary_auto_learning
from modules.rag.repository import get_document_record, update_chunking_status
from modules.rag.schemas import DocumentChunkRequest, DocumentChunkResponse
from modules.rag.service import chunk_document_and_store

router = APIRouter(prefix="/api/v1/chunk", tags=["chunking"])
logger = logging.getLogger(__name__)


@router.post("/document", response_model=DocumentChunkResponse, summary="Chunk OCR document and store to ChromaDB")
async def chunk_document(req: DocumentChunkRequest, background_tasks: BackgroundTasks):
    doc = get_document_record(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        result = await run_in_threadpool(
            chunk_document_and_store,
            document_id=req.document_id,
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
            collection_name=req.collection_name,
            buffer_max_pages=req.buffer_max_pages,
            buffer_max_chars=req.buffer_max_chars,
            max_code_block_lines=req.max_code_block_lines,
            dry_run=req.dry_run,
        )

        if not req.dry_run and result.total_chunks > 0:
            logger.info("Đang kích hoạt tiến trình AI học từ khóa ngầm...")
            background_tasks.add_task(
                run_dictionary_auto_learning,
                document_id=req.document_id,
                course_id="it_fundamentals"
            )

        return result
    except Exception as ex:
        logger.exception("Chunking failed: %s", ex)
        update_chunking_status(req.document_id, status="failed", error_message=str(ex))
        raise HTTPException(status_code=500, detail=str(ex)) from ex
