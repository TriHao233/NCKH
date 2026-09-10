from __future__ import annotations

from modules.documents.ingest.models import (
    ContentBlock,
    ParseContext,
    SourceProvenance,
    normalize_unicode,
    stable_block_id,
)


def make_block(
    context: ParseContext,
    *,
    location_key: str,
    index: int,
    block_type: str,
    content: str,
    source_location: dict,
    extractor: str,
    extraction_method: str,
    page_number: int | None = None,
    bbox: list[float] | None = None,
    confidence: float = 1.0,
    structured_content=None,
    asset_ids: list[str] | None = None,
    validation_status: str = "passed",
    validation_notes: list[str] | None = None,
) -> ContentBlock:
    normalized, transformation_log = normalize_unicode(content)
    return ContentBlock(
        block_id=stable_block_id(context, location_key, index, normalized),
        block_type=block_type,
        content=normalized,
        structured_content=structured_content,
        provenance=SourceProvenance(
            source_file_name=context.source_file_name,
            source_uri=context.source_uri,
            document_id=context.document_id,
            document_type=context.document_type,
            page_number=page_number,
            source_location=source_location,
            bbox=bbox,
            extractor=extractor,
            extraction_method=extraction_method,
            confidence=confidence,
            raw_ref=f"{context.source_uri}#{location_key}",
        ),
        transformation_log=transformation_log,
        asset_ids=asset_ids or [],
        validation_status=validation_status,
        validation_notes=validation_notes or [],
    )
