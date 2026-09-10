from pathlib import Path

from modules.documents.ingest.base import DocumentParser
from modules.documents.ingest.models import DocumentUnit, ParsedDocument, ParseContext
from modules.documents.ingest.parsers.common import make_block
from modules.documents.ingest.quality import text_quality_metrics


class TextParser(DocumentParser):
    extensions = frozenset({".txt"})
    mime_types = frozenset({"text/plain"})

    def parse(self, path: Path, context: ParseContext) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8-sig")
        block = make_block(
            context,
            location_key="text:0",
            index=0,
            block_type="prose",
            content=raw,
            source_location={"character_start": 0, "character_end": len(raw)},
            extractor="python-text",
            extraction_method="utf8_decode",
        )
        unit = DocumentUnit(
            unit_number=1,
            page_number=None,
            source_location={"character_start": 0, "character_end": len(raw)},
            raw_text=raw,
            content_blocks=[block],
            raw_extraction={"encoding": "utf-8-sig"},
            quality=text_quality_metrics(raw),
        )
        return ParsedDocument(
            document_id=context.document_id,
            document_type=context.document_type,
            source_file_name=context.source_file_name,
            source_uri=context.source_uri,
            units=[unit],
            stats={"source_format": "txt", "unit_count": 1, "char_count": len(raw)},
        )
