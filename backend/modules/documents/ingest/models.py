from __future__ import annotations

import hashlib
import unicodedata
from typing import Any, Literal

from pydantic import BaseModel, Field


BlockType = Literal[
    "prose",
    "heading",
    "list",
    "table",
    "code",
    "formula",
    "image",
    "diagram",
    "caption",
    "page_break",
]
AssetStatus = Literal["stored", "reference_only", "unsupported", "failed"]
ValidationStatus = Literal["passed", "needs_review", "failed"]


class DerivedDescription(BaseModel):
    """Optional model-generated description, kept separate from source content."""

    text: str
    model: str
    model_version: str
    confidence: float = Field(ge=0.0, le=1.0)
    generated_at: str | None = None


class ParseContext(BaseModel):
    document_id: str
    source_file_name: str
    source_uri: str
    mime_type: str
    document_type: str


class SourceProvenance(BaseModel):
    source_file_name: str
    source_uri: str
    document_id: str
    document_type: str
    page_number: int | None = None
    source_location: dict[str, Any] = Field(default_factory=dict)
    bbox: list[float] | None = None
    extractor: str
    extraction_method: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    raw_ref: str | None = None


class ContentBlock(BaseModel):
    block_id: str
    block_type: BlockType
    content: str = ""
    structured_content: dict[str, Any] | list[Any] | None = None
    provenance: SourceProvenance
    transformation_log: list[dict[str, Any]] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    continuation_of: str | None = None
    part_index: int | None = None
    part_count: int | None = None
    validation_status: ValidationStatus = "passed"
    validation_notes: list[str] = Field(default_factory=list)


class Asset(BaseModel):
    asset_id: str
    asset_type: Literal["image", "diagram", "embedded_file"]
    status: AssetStatus
    provenance: SourceProvenance
    storage_uri: str | None = None
    reason: str | None = None
    source_content: str | None = None
    source_caption: str | None = None
    content_sha256: str | None = None
    validation_status: ValidationStatus = "passed"
    validation_notes: list[str] = Field(default_factory=list)
    derived_description: DerivedDescription | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentUnit(BaseModel):
    unit_number: int
    page_number: int | None = None
    source_location: dict[str, Any] = Field(default_factory=dict)
    raw_text: str = ""
    content_blocks: list[ContentBlock] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    raw_extraction: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)

    def rendered_text(self) -> str:
        return "\n\n".join(block.content for block in self.content_blocks if block.content).strip()


class ParsedDocument(BaseModel):
    document_id: str
    document_type: str
    source_file_name: str
    source_uri: str
    units: list[DocumentUnit]
    assets: list[Asset] = Field(default_factory=list)
    raw_engine_outputs: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)

    def to_page_records(self) -> list[dict[str, Any]]:
        asset_by_id = {asset.asset_id: asset.model_dump(mode="json") for asset in self.assets}
        records: list[dict[str, Any]] = []
        for unit in self.units:
            blocks = [block.model_dump(mode="json") for block in unit.content_blocks]
            records.append(
                {
                    "unit_number": unit.unit_number,
                    "page_number": unit.page_number,
                    "source_location": unit.source_location,
                    "original_text": unit.raw_text,
                    "text": unit.rendered_text(),
                    "content_blocks": blocks,
                    "assets": [asset_by_id[asset_id] for asset_id in unit.asset_ids if asset_id in asset_by_id],
                    "raw_extraction": unit.raw_extraction,
                    "quality": unit.quality,
                    "formula_blocks": [
                        block.structured_content or {"content": block.content}
                        for block in unit.content_blocks
                        if block.block_type == "formula"
                    ],
                }
            )
        return records


def normalize_unicode(value: str) -> tuple[str, list[dict[str, Any]]]:
    normalized = unicodedata.normalize("NFC", value)
    if normalized == value:
        return value, []
    return normalized, [{"operation": "unicode_nfc", "semantic_change": False}]


def stable_block_id(context: ParseContext, location: str, index: int, content: str) -> str:
    payload = f"{context.document_id}:{location}:{index}:{content}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def stable_asset_id(context: ParseContext, location: str, index: int) -> str:
    payload = f"{context.document_id}:asset:{location}:{index}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]
