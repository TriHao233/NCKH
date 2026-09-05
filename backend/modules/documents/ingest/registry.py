from __future__ import annotations

from pathlib import Path

from modules.documents.ingest.base import DocumentParser
from modules.documents.ingest.parsers import DocxParser, LegacyDocParser, MarkdownParser, PdfParser, TextParser


class DocumentParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[DocumentParser] = []

    def register(self, parser: DocumentParser) -> None:
        self._parsers.append(parser)

    def resolve(self, path: str | Path, mime_type: str | None = None) -> DocumentParser:
        resolved = Path(path)
        for parser in self._parsers:
            if parser.supports(resolved, mime_type):
                return parser
        raise ValueError(f"Không có parser cho định dạng {resolved.suffix.lower() or mime_type or 'unknown'}")

    @property
    def parsers(self) -> tuple[DocumentParser, ...]:
        return tuple(self._parsers)


def build_default_registry(*, pdf_ocr_enabled: bool = True) -> DocumentParserRegistry:
    registry = DocumentParserRegistry()
    registry.register(PdfParser() if pdf_ocr_enabled else PdfParser(ocr_page_extractor=None))
    registry.register(DocxParser())
    registry.register(LegacyDocParser())
    registry.register(MarkdownParser())
    registry.register(TextParser())
    return registry
