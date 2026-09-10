from __future__ import annotations

import re
import hashlib
from pathlib import Path

from modules.documents.ingest.base import DocumentParser
from modules.documents.ingest.models import (
    Asset,
    DocumentUnit,
    ParsedDocument,
    ParseContext,
    SourceProvenance,
    stable_asset_id,
)
from modules.documents.ingest.parsers.common import make_block
from modules.documents.ingest.quality import text_quality_metrics


FENCE_START = re.compile(r"^\s*(```|~~~)")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
LIST_ITEM = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")
IMAGE = re.compile(r"!\[([^]]*)\]\(([^)\s]+)(?:\s+['\"][^'\"]*['\"])?\)")
TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


class MarkdownParser(DocumentParser):
    extensions = frozenset({".md", ".markdown"})
    mime_types = frozenset({"text/markdown", "text/x-markdown"})

    def parse(self, path: Path, context: ParseContext) -> ParsedDocument:
        raw = path.read_text(encoding="utf-8-sig")
        lines = raw.splitlines(keepends=True)
        blocks = []
        assets: list[Asset] = []
        asset_ids: list[str] = []
        index = 0
        cursor = 0

        def add_block(block_type: str, start: int, end: int, structured=None) -> None:
            nonlocal index
            content = "".join(lines[start:end]).rstrip("\r\n")
            if not content:
                return
            line_assets: list[str] = []
            for image_index, match in enumerate(IMAGE.finditer(content)):
                asset_id = stable_asset_id(context, f"markdown:{start + 1}", image_index)
                provenance = SourceProvenance(
                    source_file_name=context.source_file_name,
                    source_uri=context.source_uri,
                    document_id=context.document_id,
                    document_type=context.document_type,
                    source_location={"line_start": start + 1, "line_end": end},
                    extractor="python-markdown",
                    extraction_method="markdown_image_reference",
                    raw_ref=f"{context.source_uri}#L{start + 1}",
                )
                assets.append(
                    Asset(
                        asset_id=asset_id,
                        asset_type="image",
                        status="reference_only",
                        provenance=provenance,
                        storage_uri=match.group(2),
                        source_content=match.group(0),
                        source_caption=match.group(1) or None,
                        content_sha256=(
                            hashlib.sha256((path.parent / match.group(2)).read_bytes()).hexdigest()
                            if not Path(match.group(2)).is_absolute() and (path.parent / match.group(2)).is_file()
                            else None
                        ),
                        validation_status="passed" if match.group(1).strip() else "needs_review",
                        validation_notes=[] if match.group(1).strip() else ["image has no source caption/alt text"],
                        metadata={
                            "alt_text": match.group(1),
                            "caption_source": "markdown_alt_text" if match.group(1).strip() else None,
                            "original_or_crop": "referenced_file",
                        },
                    )
                )
                line_assets.append(asset_id)
                asset_ids.append(asset_id)
            blocks.append(
                make_block(
                    context,
                    location_key=f"markdown:{start + 1}-{end}",
                    index=index,
                    block_type=block_type,
                    content=content,
                    source_location={"line_start": start + 1, "line_end": end},
                    extractor="python-markdown",
                    extraction_method="markdown_structure",
                    structured_content=structured,
                    asset_ids=line_assets,
                )
            )
            index += 1

        while cursor < len(lines):
            stripped = lines[cursor].rstrip("\r\n")
            if not stripped.strip():
                cursor += 1
                continue
            fence = FENCE_START.match(stripped)
            if fence:
                start = cursor
                marker = fence.group(1)
                cursor += 1
                while cursor < len(lines) and not lines[cursor].lstrip().startswith(marker):
                    cursor += 1
                cursor = min(cursor + 1, len(lines))
                add_block("code", start, cursor)
                continue
            if stripped.strip().startswith("$$"):
                start = cursor
                cursor += 1
                while cursor < len(lines) and "$$" not in lines[cursor]:
                    cursor += 1
                cursor = min(cursor + 1, len(lines))
                formula_content = "".join(lines[start:cursor]).rstrip("\r\n")
                add_block("formula", start, cursor, {"raw": formula_content, "latex": formula_content.strip("$\n")})
                continue
            if HEADING.match(stripped):
                add_block("heading", cursor, cursor + 1)
                cursor += 1
                continue
            if cursor + 1 < len(lines) and "|" in stripped and TABLE_SEPARATOR.match(lines[cursor + 1].rstrip()):
                start = cursor
                cursor += 2
                while cursor < len(lines) and "|" in lines[cursor] and lines[cursor].strip():
                    cursor += 1
                rows = [line.strip().strip("|").split("|") for line in lines[start:cursor]]
                normalized_rows = [[cell.strip() for cell in row] for row in rows]
                add_block(
                    "table",
                    start,
                    cursor,
                    {
                        "rows": normalized_rows,
                        "row_count": len(normalized_rows),
                        "column_count": len(normalized_rows[0]),
                        "cells": [
                            {"row": row_index, "column": column_index, "text": cell}
                            for row_index, row in enumerate(normalized_rows)
                            for column_index, cell in enumerate(row)
                        ],
                    },
                )
                continue
            if LIST_ITEM.match(stripped):
                start = cursor
                cursor += 1
                while cursor < len(lines) and LIST_ITEM.match(lines[cursor].rstrip("\r\n")):
                    cursor += 1
                add_block("list", start, cursor)
                continue
            if IMAGE.fullmatch(stripped.strip()):
                add_block("image", cursor, cursor + 1)
                cursor += 1
                continue
            start = cursor
            cursor += 1
            while cursor < len(lines):
                candidate = lines[cursor].rstrip("\r\n")
                if not candidate.strip() or FENCE_START.match(candidate) or HEADING.match(candidate):
                    break
                if LIST_ITEM.match(candidate) or candidate.strip().startswith("$$"):
                    break
                if cursor + 1 < len(lines) and "|" in candidate and TABLE_SEPARATOR.match(lines[cursor + 1].rstrip()):
                    break
                cursor += 1
            add_block("prose", start, cursor)

        unit = DocumentUnit(
            unit_number=1,
            page_number=None,
            source_location={"line_start": 1, "line_end": max(len(lines), 1)},
            raw_text=raw,
            content_blocks=blocks,
            asset_ids=asset_ids,
            raw_extraction={"encoding": "utf-8-sig", "parser": "markdown_state_machine"},
            quality=text_quality_metrics(raw),
        )
        return ParsedDocument(
            document_id=context.document_id,
            document_type=context.document_type,
            source_file_name=context.source_file_name,
            source_uri=context.source_uri,
            units=[unit],
            assets=assets,
            stats={"source_format": "md", "unit_count": 1, "block_count": len(blocks)},
        )
