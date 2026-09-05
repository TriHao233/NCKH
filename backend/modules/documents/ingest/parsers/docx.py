from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from modules.documents.ingest.base import DocumentConversionError, DocumentParser, UnsupportedDocumentError
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


DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOC_MIME_TYPE = "application/msword"


def _iter_body_blocks(document: Document):
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _paragraph_type(paragraph: Paragraph) -> str:
    style = (paragraph.style.name if paragraph.style else "").strip().lower()
    text = paragraph.text
    if style.startswith("heading") or style in {"title", "subtitle"}:
        return "heading"
    if "list" in style or paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None:
        return "list"
    if "code" in style or "preformatted" in style:
        return "code"
    if paragraph._element.xpath(".//m:oMath | .//m:oMathPara"):
        return "formula"
    stripped = text.lstrip()
    if stripped.startswith(("#include", "#define", "typedef ", "struct ", "class ")):
        return "code"
    return "prose"


def _table_cells(table: Table) -> list[dict]:
    cells: list[dict] = []
    seen_cells: set[int] = set()
    for row_index, row in enumerate(table.rows):
        for column_index, cell in enumerate(row.cells):
            cell_identity = id(cell._tc)
            if cell_identity in seen_cells:
                continue
            seen_cells.add(cell_identity)
            properties = cell._tc.tcPr
            grid_span = properties.gridSpan
            vertical_merge = properties.vMerge
            cells.append(
                {
                    "row": row_index,
                    "column": column_index,
                    "text": cell.text,
                    "column_span": int(grid_span.val) if grid_span is not None else 1,
                    "vertical_merge": str(vertical_merge.val or "continue") if vertical_merge is not None else None,
                }
            )
    return cells


class DocxParser(DocumentParser):
    extensions = frozenset({".docx"})
    mime_types = frozenset({DOCX_MIME_TYPE})

    def parse(self, path: Path, context: ParseContext) -> ParsedDocument:
        document = Document(str(path))
        blocks = []
        assets: list[Asset] = []
        unit_asset_ids: list[str] = []
        raw_parts: list[str] = []
        paragraph_index = 0
        table_index = 0

        for body_index, body_block in enumerate(_iter_body_blocks(document)):
            if isinstance(body_block, Paragraph):
                paragraph_index += 1
                text = body_block.text
                image_ids: list[str] = []
                drawing_properties = body_block._element.xpath(".//wp:docPr")
                for image_index, blip in enumerate(body_block._element.xpath(".//a:blip")):
                    relationship_id = blip.get(qn("r:embed"))
                    relationship = document.part.rels.get(relationship_id) if relationship_id else None
                    target = str(relationship.target_ref) if relationship else None
                    blob = getattr(getattr(relationship, "target_part", None), "blob", None)
                    drawing = drawing_properties[image_index] if image_index < len(drawing_properties) else None
                    source_caption = (drawing.get("descr") or drawing.get("title")) if drawing is not None else None
                    asset_id = stable_asset_id(context, f"paragraph:{paragraph_index}", image_index)
                    provenance = SourceProvenance(
                        source_file_name=context.source_file_name,
                        source_uri=context.source_uri,
                        document_id=context.document_id,
                        document_type=context.document_type,
                        source_location={"paragraph_index": paragraph_index, "body_index": body_index},
                        extractor="python-docx",
                        extraction_method="docx_relationship",
                        raw_ref=f"{context.source_uri}#paragraph={paragraph_index}",
                    )
                    assets.append(
                        Asset(
                            asset_id=asset_id,
                            asset_type="image",
                            status="reference_only",
                            provenance=provenance,
                            storage_uri=f"{context.source_uri}::{target}" if target else None,
                            reason=None if target else "DOCX image relationship target is unavailable",
                            source_caption=source_caption or None,
                            content_sha256=hashlib.sha256(blob).hexdigest() if blob else None,
                            validation_status="passed" if target and blob else "needs_review",
                            validation_notes=[] if target and blob else ["embedded image bytes are unavailable"],
                            metadata={
                                "relationship_id": relationship_id,
                                "package_part": target,
                                "original_or_crop": "original_package_part" if target else None,
                                "caption_source": "docx_drawing_property" if source_caption else None,
                            },
                        )
                    )
                    image_ids.append(asset_id)
                    unit_asset_ids.append(asset_id)
                if text:
                    block_type = _paragraph_type(body_block)
                    structured = None
                    if block_type == "formula":
                        structured = {"omml": body_block._element.xml}
                    blocks.append(
                        make_block(
                            context,
                            location_key=f"docx:paragraph:{paragraph_index}",
                            index=len(blocks),
                            block_type=block_type,
                            content=text,
                            source_location={"paragraph_index": paragraph_index, "body_index": body_index},
                            extractor="python-docx",
                            extraction_method="paragraph",
                            structured_content=structured,
                            asset_ids=image_ids,
                        )
                    )
                    raw_parts.append(text)
                elif image_ids:
                    blocks.append(
                        make_block(
                            context,
                            location_key=f"docx:paragraph:{paragraph_index}",
                            index=len(blocks),
                            block_type="image",
                            content="",
                            source_location={"paragraph_index": paragraph_index, "body_index": body_index},
                            extractor="python-docx",
                            extraction_method="drawing",
                            asset_ids=image_ids,
                        )
                    )
            elif isinstance(body_block, Table):
                table_index += 1
                rows = [[cell.text for cell in row.cells] for row in body_block.rows]
                if not rows:
                    continue
                markdown_lines = ["| " + " | ".join(cell.replace("|", "\\|") for cell in rows[0]) + " |"]
                markdown_lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
                markdown_lines.extend(
                    "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
                    for row in rows[1:]
                )
                content = "\n".join(markdown_lines)
                blocks.append(
                    make_block(
                        context,
                        location_key=f"docx:table:{table_index}",
                        index=len(blocks),
                        block_type="table",
                        content=content,
                        source_location={"table_index": table_index, "body_index": body_index},
                        extractor="python-docx",
                        extraction_method="table_grid",
                        structured_content={
                            "rows": rows,
                            "row_count": len(rows),
                            "column_count": len(rows[0]),
                            "cells": _table_cells(body_block),
                        },
                    )
                )
                raw_parts.append(content)

        raw_text = "\n\n".join(raw_parts)
        if not blocks:
            raise ValueError("DOCX không có nội dung có thể trích xuất")
        unit = DocumentUnit(
            unit_number=1,
            page_number=None,
            source_location={"section_index": 1},
            raw_text=raw_text,
            content_blocks=blocks,
            asset_ids=unit_asset_ids,
            raw_extraction={
                "paragraph_count": paragraph_index,
                "table_count": table_index,
                "page_number_reliable": False,
            },
            quality=text_quality_metrics(raw_text),
        )
        return ParsedDocument(
            document_id=context.document_id,
            document_type=context.document_type,
            source_file_name=context.source_file_name,
            source_uri=context.source_uri,
            units=[unit],
            assets=assets,
            stats={
                "source_format": "docx",
                "unit_count": 1,
                "paragraph_count": paragraph_index,
                "table_count": table_index,
                "asset_count": len(assets),
            },
        )


class LegacyDocParser(DocumentParser):
    """Legacy DOC adapter using an optional LibreOffice conversion boundary."""

    extensions = frozenset({".doc"})
    mime_types = frozenset({DOC_MIME_TYPE})

    def parse(self, path: Path, context: ParseContext) -> ParsedDocument:
        converter = shutil.which("soffice") or shutil.which("libreoffice")
        if not converter:
            raise UnsupportedDocumentError(
                "DOC legacy cần LibreOffice/soffice để chuyển đổi an toàn sang DOCX; tài liệu không được index"
            )
        with path.open("rb") as source_stream:
            signature = source_stream.read(8)
        if not (signature.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") or signature.lstrip().startswith(b"{\\rtf")):
            raise DocumentConversionError(
                "File .doc không có chữ ký OLE/RTF hợp lệ; tài liệu không được index",
                converter=Path(converter).name,
                detail="invalid_legacy_doc_signature",
            )
        with tempfile.TemporaryDirectory(prefix="qbank-doc-") as temp_dir:
            profile_dir = Path(temp_dir) / "profile"
            output_dir = Path(temp_dir) / "output"
            profile_dir.mkdir()
            output_dir.mkdir()
            try:
                completed = subprocess.run(
                    [
                        converter,
                        "--headless",
                        "--nologo",
                        "--nodefault",
                        "--nolockcheck",
                        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
                        "--convert-to",
                        "docx:Office Open XML Text",
                        "--outdir",
                        str(output_dir),
                        str(path.resolve()),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise DocumentConversionError(
                    "Chuyển đổi DOC quá thời hạn 120 giây; tài liệu không được index",
                    converter=Path(converter).name,
                    detail="timeout",
                ) from exc
            converted = output_dir / f"{path.stem}.docx"
            if completed.returncode or not converted.exists():
                raise DocumentConversionError(
                    "Không thể chuyển DOC sang DOCX; tài liệu không được index",
                    converter=Path(converter).name,
                    detail=(completed.stderr or completed.stdout or "no converter output")[-1000:],
                )
            try:
                parsed = DocxParser().parse(converted, context)
            except Exception as exc:
                raise DocumentConversionError(
                    "DOC sau chuyển đổi không phải DOCX hợp lệ; tài liệu không được index",
                    converter=Path(converter).name,
                    detail=type(exc).__name__,
                ) from exc
            parsed.document_type = "doc"
            parsed.stats["conversion"] = "libreoffice_doc_to_docx"
            parsed.raw_engine_outputs["conversion_log"] = {
                "return_code": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-2000:],
            }
            return parsed
