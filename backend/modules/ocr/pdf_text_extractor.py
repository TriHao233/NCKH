"""Conservative text-layer extraction used before the expensive Docling path."""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from typing import Any

from pypdf import PdfReader

from core.config import settings

logger = logging.getLogger(__name__)


def _resolve_pdf_object(value: Any) -> Any:
    try:
        return value.get_object()
    except (AttributeError, TypeError):
        return value


def _resources_have_images(resources: Any, seen: set[int] | None = None) -> bool:
    resolved = _resolve_pdf_object(resources)
    if not resolved or not hasattr(resolved, "get"):
        return False

    seen = seen or set()
    marker = id(resolved)
    if marker in seen:
        return False
    seen.add(marker)

    xobjects = _resolve_pdf_object(resolved.get("/XObject"))
    if not xobjects or not hasattr(xobjects, "values"):
        return False
    for raw_object in xobjects.values():
        obj = _resolve_pdf_object(raw_object)
        if not obj or not hasattr(obj, "get"):
            continue
        subtype = str(obj.get("/Subtype") or "")
        if subtype == "/Image":
            return True
        if subtype == "/Form" and _resources_have_images(obj.get("/Resources"), seen):
            return True
    return False


def _extract_page_text(page: Any) -> str:
    try:
        text = page.extract_text(extraction_mode="layout")
    except (TypeError, ValueError, NotImplementedError):
        text = page.extract_text()
    return (text or "").strip()


def extract_pdf_text_layer(file_path: str | Path) -> dict[str, Any]:
    """Extract PDF text and decide if it is safe to bypass Docling.

    The fast path is deliberately document-wide. A PDF is accepted only when
    almost every page has useful text, the average text density is sufficient,
    no more than the configured fraction of pages contains images, and decoded
    text has very few replacement characters. Otherwise callers must fall back
    to Docling so scanned/image content is not silently lost.
    """

    started_at = perf_counter()
    path = Path(file_path)
    pages: list[dict[str, Any]] = []
    page_has_image: list[bool] = []
    extraction_errors = 0
    total_pages = 0

    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("PDF is encrypted and cannot be opened without a password")

        total_pages = len(reader.pages)
        maximum_image_pages = int(total_pages * settings.pdf_text_fast_path_max_image_page_ratio)
        image_pages_seen = 0
        for page in reader.pages:
            resources = page.get("/Resources") if hasattr(page, "get") else None
            has_image = _resources_have_images(resources)
            page_has_image.append(has_image)
            image_pages_seen += int(has_image)
            if image_pages_seen > maximum_image_pages:
                elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
                return {
                    "eligible": False,
                    "pages": [],
                    "stats": {
                        "page_count": total_pages,
                        "image_pages": image_pages_seen,
                        "image_page_ratio_lower_bound": round(image_pages_seen / max(total_pages, 1), 4),
                        "image_scan_complete": False,
                        "text_layer_ms": elapsed_ms,
                        "rejection_reasons": ["image_pages_present"],
                    },
                }

        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = _extract_page_text(page)
            except Exception:
                logger.warning("Text-layer extraction failed on page %d of %s", page_number, path.name)
                text = ""
                extraction_errors += 1
            pages.append(
                {
                    "page_number": page_number,
                    "text": text,
                    "original_text": text,
                    "formula_blocks": [],
                }
            )
    except Exception as exc:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
        logger.info("PDF text-layer fast path rejected %s: %s", path.name, exc)
        return {
            "eligible": False,
            "pages": [],
            "stats": {
                "reason": "extract_error",
                "error_type": type(exc).__name__,
                "text_layer_ms": elapsed_ms,
            },
        }

    total_pages = len(pages)
    non_whitespace_counts = [len("".join(page["text"].split())) for page in pages]
    viable_pages = sum(
        count >= settings.pdf_text_fast_path_min_chars_per_page
        for count in non_whitespace_counts
    )
    total_chars = sum(len(page["text"]) for page in pages)
    replacement_chars = sum(page["text"].count("\ufffd") for page in pages)
    image_pages = sum(page_has_image)

    coverage = viable_pages / max(total_pages, 1)
    average_chars = total_chars / max(total_pages, 1)
    image_page_ratio = image_pages / max(total_pages, 1)
    replacement_ratio = replacement_chars / max(total_chars, 1)

    rejection_reasons = []
    if not total_pages:
        rejection_reasons.append("no_pages")
    if coverage < settings.pdf_text_fast_path_min_coverage:
        rejection_reasons.append("insufficient_text_coverage")
    if average_chars < settings.pdf_text_fast_path_min_chars_per_page:
        rejection_reasons.append("insufficient_text_density")
    if image_page_ratio > settings.pdf_text_fast_path_max_image_page_ratio:
        rejection_reasons.append("image_pages_present")
    if replacement_ratio > settings.pdf_text_fast_path_max_replacement_ratio:
        rejection_reasons.append("decode_quality")
    if extraction_errors:
        rejection_reasons.append("page_extract_errors")

    elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
    stats = {
        "page_count": total_pages,
        "viable_text_pages": viable_pages,
        "text_coverage": round(coverage, 4),
        "avg_chars_per_page": round(average_chars, 2),
        "image_pages": image_pages,
        "image_page_ratio": round(image_page_ratio, 4),
        "replacement_ratio": round(replacement_ratio, 6),
        "text_layer_ms": elapsed_ms,
        "rejection_reasons": rejection_reasons,
    }
    return {
        "eligible": not rejection_reasons,
        "pages": pages,
        "stats": stats,
    }
