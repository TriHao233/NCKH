import json
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

from core.config import resolve_path, settings

logger = logging.getLogger(__name__)

class ChunkMarkdownExporter:
    def __init__(self, document_id: str, output_dir: str | Path):
        self._document_id = document_id
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._path = self._output_dir / f"{document_id}_chunks_{timestamp}.md"
        self._file = self._path.open("w", encoding="utf-8")
        self._chunk_count = 0

        self._file.write("# Chunk Export\n\n")
        self._file.write(f"- Document ID: {document_id}\n")
        self._file.write(f"- Created (UTC): {timestamp}\n\n")
        self._file.write("---\n\n")

    @property
    def path(self) -> str:
        return str(self._path)

    def write_chunk(self, chunk_id: str, content: str, metadata: dict) -> None:
        self._chunk_count += 1
        heading = metadata.get("heading") or ""
        content_type = metadata.get("content_type") or "text"
        page_start = metadata.get("page_start")
        page_end = metadata.get("page_end")
        info_density = metadata.get("information_density")
        token_count = metadata.get("token_count")

        if page_start is None and page_end is None:
            page_range = "-"
        elif page_start == page_end:
            page_range = str(page_start)
        else:
            page_range = f"{page_start}-{page_end}"

        self._file.write(f"## Chunk {self._chunk_count}\n\n")
        self._file.write(f"- Chunk ID: {chunk_id}\n")
        self._file.write(f"- Page Range: {page_range}\n")
        if heading:
            self._file.write(f"- Heading: {heading}\n")
        self._file.write(f"- Content Type: {content_type}\n")
        if token_count is not None:
            self._file.write(f"- Token Count: {token_count}\n")
        if info_density is not None:
            self._file.write(f"- Info Density: {info_density}\n")

        self._file.write("\n")
        self._file.write(content.strip())
        self._file.write("\n\n---\n\n")

    def finalize(self, total_chunks: int, stored_chunks: int, status: str = "completed") -> None:
        self._file.write("# Summary\n\n")
        self._file.write(f"- Status: {status}\n")
        self._file.write(f"- Total Chunks: {total_chunks}\n")
        self._file.write(f"- Stored Chunks: {stored_chunks}\n")
        self._file.close()
        logger.info("Chunk export written: %s", self._path)

def export_chunks_to_file(document_id: str, chunks: list[dict]):
    """
    Xuất JSON metadata vao data/metadata va Markdown vao data/chunk_outputs.
    """
    metadata_dir = resolve_path(settings.metadata_dir)
    chunk_dir = resolve_path(settings.chunk_output_dir)
    os.makedirs(metadata_dir, exist_ok=True)
    os.makedirs(chunk_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. TẠO FILE JSON
    json_filename = f"{document_id}_chunks_{timestamp}.json"
    json_filepath = metadata_dir / json_filename

    json_payload = {
        "document_id": document_id,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "total_chunks": len(chunks),
        "chunks": chunks
    }

    try:
        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, ensure_ascii=False, indent=4)
        logger.info(f"Đã xuất file JSON Metadata thành công: {json_filepath}")
    except Exception as e:
        logger.error(f"Lỗi khi xuất file JSON: {e}")

    # 2. TẠO FILE MARKDOWN
    md_filename = f"{document_id}_chunks_{timestamp}.md"
    md_filepath = chunk_dir / md_filename

    try:
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write("# Chunk Export\n\n")
            f.write(f"- Document ID: {document_id}\n")
            f.write(f"- Created (UTC): {timestamp}\n")
            f.write(f"- Total Chunks: {len(chunks)}\n\n")
            f.write("---\n\n")

            for i, chunk in enumerate(chunks, 1):
                meta = chunk.get("metadata", {})
                f.write(f"## Chunk {i}\n\n")
                f.write(f"- Chunk ID: {chunk.get('chunk_id', 'N/A')}\n")
                f.write(f"- Page Range: {meta.get('page_start', '?')}-{meta.get('page_end', '?')}\n")
                f.write(f"- Content Type: {meta.get('content_type', 'unknown')}\n")
                f.write(f"- Token Count: {meta.get('token_count', 0)}\n")
                f.write(f"- Info Density: {meta.get('information_density', 0.0)}\n")
                if meta.get('heading_path'):
                    f.write(f"- Heading Path: {' > '.join(meta['heading_path'])}\n")
                f.write(f"\n{chunk.get('content', '')}\n\n")
                f.write("---\n\n")

        logger.info(f"Đã xuất file Markdown thành công: {md_filepath}")
    except Exception as e:
        logger.error(f"Lỗi khi xuất file MD: {e}")

    return json_filepath, md_filepath
