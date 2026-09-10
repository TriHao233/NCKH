from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from modules.documents.ingest.models import ParsedDocument, ParseContext


class DocumentParser(ABC):
    extensions: frozenset[str] = frozenset()
    mime_types: frozenset[str] = frozenset()

    def supports(self, path: Path, mime_type: str | None = None) -> bool:
        return path.suffix.lower() in self.extensions or bool(mime_type and mime_type in self.mime_types)

    @abstractmethod
    def parse(self, path: Path, context: ParseContext) -> ParsedDocument:
        raise NotImplementedError


class UnsupportedDocumentError(ValueError):
    """Raised when a registered adapter cannot run in the current environment."""

    code = "UNSUPPORTED_DOCUMENT"
    remediation = "Cài LibreOffice headless hoặc chuyển tài liệu sang DOCX rồi tải lại."

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self), "remediation": self.remediation}


class DocumentConversionError(UnsupportedDocumentError):
    """Fail-closed error for a legacy conversion that produced no trusted output."""

    code = "DOCUMENT_CONVERSION_FAILED"
    remediation = "Mở và Save As DOCX bằng LibreOffice/Microsoft Word, kiểm tra file không hỏng rồi tải lại."

    def __init__(self, message: str, *, converter: str | None = None, detail: str | None = None):
        super().__init__(message)
        self.converter = converter
        self.detail = detail

    def to_dict(self) -> dict[str, str]:
        payload = super().to_dict()
        if self.converter:
            payload["converter"] = self.converter
        if self.detail:
            payload["detail"] = self.detail
        return payload
