"""Selective PDF OCR with EasyOCR and PDFium (no Poppler or Docling service)."""

from __future__ import annotations

import logging
from pathlib import Path
from statistics import median
from typing import Any

from core.config import resolve_path, settings

logger = logging.getLogger(__name__)


def _line_text(items: list[tuple[list[list[float]], str, float]]) -> str:
    """Restore a readable line order from EasyOCR bounding boxes."""

    if not items:
        return ""
    heights = [max(point[1] for point in box) - min(point[1] for point in box) for box, _, _ in items]
    tolerance = max(8.0, median(heights) * 0.65)
    ordered = sorted(
        items,
        key=lambda item: (
            sum(point[1] for point in item[0]) / len(item[0]),
            min(point[0] for point in item[0]),
        ),
    )
    lines: list[list[tuple[list[list[float]], str, float]]] = []
    line_centers: list[float] = []
    for item in ordered:
        center_y = sum(point[1] for point in item[0]) / len(item[0])
        target = next(
            (index for index, existing_y in enumerate(line_centers) if abs(center_y - existing_y) <= tolerance),
            None,
        )
        if target is None:
            lines.append([item])
            line_centers.append(center_y)
        else:
            lines[target].append(item)
            line_centers[target] = sum(
                sum(point[1] for point in box) / len(box) for box, _, _ in lines[target]
            ) / len(lines[target])
    rendered: list[str] = []
    for line in lines:
        line.sort(key=lambda item: min(point[0] for point in item[0]))
        rendered.append(" ".join(text.strip() for _, text, _ in line if text.strip()))
    return "\n".join(line for line in rendered if line)


def _release_cuda_memory() -> None:
    if not settings.easyocr_unload_after_use:
        return
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception as exc:  # cleanup must not discard a successful OCR result
        logger.debug("Could not release EasyOCR CUDA cache: %s", exc)


def ocr_pdf_pages(
    file_path: str,
    page_numbers: list[int],
    _context: Any = None,
) -> dict[int, dict[str, Any]]:
    """OCR selected one-based PDF pages and return parser-compatible results."""

    if not page_numbers:
        return {}
    try:
        import easyocr
        import numpy as np
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("EasyOCR dependencies are missing; install backend requirements") from exc

    model_dir = resolve_path(settings.easyocr_model_storage_directory)
    model_dir.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(file_path)
    selected = sorted(set(page_numbers))
    if selected[0] < 1 or selected[-1] > len(pdf):
        raise ValueError("Selected OCR page is outside the PDF page range")

    reader = None
    results: dict[int, dict[str, Any]] = {}
    try:
        reader = easyocr.Reader(
            settings.easyocr_languages,
            gpu=settings.easyocr_gpu,
            model_storage_directory=str(model_dir),
            download_enabled=settings.easyocr_download_enabled,
            verbose=False,
        )
        for page_number in selected:
            page = pdf[page_number - 1]
            bitmap = page.render(scale=settings.easyocr_render_scale)
            image = bitmap.to_pil().convert("RGB")
            detections = reader.readtext(
                np.asarray(image),
                detail=1,
                paragraph=False,
                batch_size=settings.easyocr_batch_size,
            )
            accepted = [
                (box, str(text), float(confidence))
                for box, text, confidence in detections
                if str(text).strip() and float(confidence) >= settings.easyocr_min_confidence
            ]
            text = _line_text(accepted)
            results[page_number] = {
                "text": text,
                "original_text": text,
                "formula_blocks": [],
                "structured_blocks": [],
                "diagnostics": {
                    "engine": "easyocr",
                    "device": "cuda" if settings.easyocr_gpu else "cpu",
                    "languages": settings.easyocr_languages,
                    "detections": len(detections),
                    "accepted_detections": len(accepted),
                },
            }
            page.close()
    finally:
        pdf.close()
        if settings.easyocr_unload_after_use:
            del reader
            _release_cuda_memory()
    return results
