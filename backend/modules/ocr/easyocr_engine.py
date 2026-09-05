import os
import gc
import shutil
import sys
import numpy as np
import logging
from threading import Lock
from pathlib import Path

from typing import Any, Callable
from pdf2image import pdfinfo_from_path, convert_from_path

from core.config import settings

logger = logging.getLogger(__name__)

_readers_cache = {}
_cache_lock = Lock()


def _prepare_easyocr_runtime() -> None:
    # On Windows/Anaconda, importing cv2 before torch avoids duplicate OpenMP DLL initialization.
    import cv2  # noqa: F401


def _import_easyocr():
    _prepare_easyocr_runtime()
    import easyocr

    return easyocr


def _resolve_poppler_path(poppler_path: str | None = None) -> str | None:
    candidates = [
        poppler_path,
        os.environ.get("POPPLER_PATH"),
        r"C:\poppler\Library\bin",
        str(Path(sys.prefix) / "Library" / "bin"),
        str(
            Path.home()
            / ".cache"
            / "codex-runtimes"
            / "codex-primary-runtime"
            / "dependencies"
            / "native"
            / "poppler"
            / "Library"
            / "bin"
        ),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate.strip("\"'"))
        if (path / "pdfinfo.exe").exists() and (path / "pdftoppm.exe").exists():
            return str(path)

    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo and Path(pdfinfo).suffix.lower() == ".exe":
        return str(Path(pdfinfo).resolve().parent)
    return None


def is_easyocr_available() -> bool:
    try:
        _import_easyocr()
        return True
    except ImportError:
        return False


def detect_gpu() -> bool:
    try:
        _prepare_easyocr_runtime()
        import torch
        return torch.cuda.is_available()
    except Exception:
        return False


def get_reader(languages: list[str], gpu: bool | None = None):
    global _readers_cache

    # Tối ưu khóa (Key): Sắp xếp ngôn ngữ để tránh trùng lặp model
    # Ví dụ: ['vi', 'en'] và ['en', 'vi'] sẽ cùng tạo ra tuple ('en', 'vi')
    lang_key = tuple(sorted(languages))

    if gpu is None:
        gpu = detect_gpu()

    # Tạo chữ ký cấu hình làm chìa khóa Cache
    cache_key = (lang_key, gpu)

    reader = _readers_cache.get(cache_key)
    if reader is not None:
        logger.info(f"⚡ Sử dụng lại mô hình EasyOCR từ Cache: Languages={languages}, GPU={gpu}")
        return reader

    with _cache_lock:
        reader = _readers_cache.get(cache_key)
        if reader is None:
            easyocr = _import_easyocr()

            logger.info(f"⚙️ Khởi tạo mô hình EasyOCR mới vào VRAM: Languages={languages}, GPU={gpu}")
            reader = easyocr.Reader(languages, gpu=gpu, verbose=False)
            _readers_cache[cache_key] = reader
        else:
            logger.info(f"⚡ Sử dụng lại mô hình EasyOCR từ Cache: Languages={languages}, GPU={gpu}")

    return reader


def _ocr_page_numbers(
    pdf_path: str,
    languages: list[str],
    page_numbers: list[int],
    *,
    gpu: bool | None = None,
    poppler_path: str | None = None,
    dpi: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    if not page_numbers:
        return []
    if not is_easyocr_available():
        raise RuntimeError("EasyOCR is required for pages without a usable text layer")

    poppler = _resolve_poppler_path(poppler_path)
    resolved_dpi = dpi or settings.ocr_dpi
    reader = get_reader(languages=languages, gpu=gpu)
    pages: list[dict[str, Any]] = []

    for page_num in page_numbers:
        logger.info("Đang OCR trang %s...", page_num)
        images = convert_from_path(
            pdf_path,
            dpi=resolved_dpi,
            fmt="png",
            first_page=page_num,
            last_page=page_num,
            poppler_path=poppler,
            timeout=settings.pdf_render_timeout_seconds,
        )
        if not images:
            raise RuntimeError(f"Không render được trang PDF {page_num}")
        img = images[0]
        if img.width * img.height > settings.ocr_max_page_pixels:
            raise ValueError(
                f"Trang {page_num} vượt giới hạn {settings.ocr_max_page_pixels} pixels"
            )
        img_array = np.array(img)
        results = reader.readtext(img_array, detail=1, paragraph=False, batch_size=4)
        results.sort(
            key=lambda item: (
                min(point[1] for point in item[0]),
                min(point[0] for point in item[0]),
            )
        )
        lines = [str(item[1]) for item in results]
        page_text = "\n".join(lines)
        pages.append(
            {
                "page_number": page_num,
                "text": page_text,
                "original_text": page_text,
                "extraction_method": "OCR",
                "quality_flags": [],
                "layout_blocks": [
                    {
                        "type": "TEXT",
                        "bbox": [[float(x), float(y)] for x, y in item[0]],
                        "text": str(item[1]),
                        "confidence": float(item[2]),
                    }
                    for item in results
                ],
            }
        )
        if progress_callback:
            progress_callback(
                {"stage": "OCR", "page_number": page_num, "pages_in_batch": len(page_numbers)}
            )
        del images, img, img_array, results
        gc.collect()
    return pages


def stream_and_ocr_pdf(
    pdf_path: str,
    languages: list[str],
    gpu: bool | None = None,
    poppler_path: str | None = None,
    *,
    page_numbers: list[int] | None = None,
    max_pages: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """
    Đọc PDF và OCR cuốn chiếu từng trang để tối ưu hóa tối đa RAM/VRAM.
    """
    poppler = _resolve_poppler_path(poppler_path)

    # 1. Trích xuất thông tin PDF để lấy tổng số trang (Chỉ tốn vài KB RAM)
    info = pdfinfo_from_path(pdf_path, poppler_path=poppler)
    total_pages = int(info["Pages"])
    resolved_max_pages = max_pages or settings.pdf_max_pages
    if total_pages > resolved_max_pages:
        raise ValueError(f"PDF có {total_pages} trang, vượt giới hạn {resolved_max_pages} trang")
    logger.info(f"Tài liệu có tổng cộng {total_pages} trang. Bắt đầu xử lý cuốn chiếu...")
    selected = page_numbers or list(range(1, total_pages + 1))
    if any(page < 1 or page > total_pages for page in selected):
        raise ValueError("Danh sách trang OCR nằm ngoài phạm vi PDF")
    pages = _ocr_page_numbers(
        pdf_path,
        languages,
        selected,
        gpu=gpu,
        poppler_path=poppler,
        progress_callback=progress_callback,
    )
    logger.info("Hoàn tất tiến trình OCR toàn bộ tài liệu!")
    return pages


def _text_layer_is_usable(text: str) -> bool:
    normalized = "".join(text.split())
    if len(normalized) < settings.ocr_text_layer_min_chars:
        return False
    meaningful = sum(character.isalnum() for character in normalized)
    return meaningful / max(len(normalized), 1) >= settings.ocr_text_layer_min_alnum_ratio


def extract_pdf_text_pages(
    pdf_path: str,
    *,
    max_pages: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Read the native text layer and layout without rasterizing the PDF."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for extraction-first PDF processing") from exc

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise ValueError("PDF bị hỏng hoặc không thể mở") from exc

    try:
        if document.needs_pass:
            raise ValueError("PDF được mã hóa và cần mật khẩu")
        resolved_max_pages = max_pages or settings.pdf_max_pages
        if document.page_count > resolved_max_pages:
            raise ValueError(
                f"PDF có {document.page_count} trang, vượt giới hạn {resolved_max_pages} trang"
            )
        pages: list[dict[str, Any]] = []
        for index in range(document.page_count):
            page = document.load_page(index)
            text = page.get_text("text", sort=True) or ""
            blocks = []
            for block in page.get_text("blocks", sort=True) or []:
                if len(block) < 7 or int(block[6]) != 0:
                    continue
                block_text = str(block[4] or "")
                if not block_text.strip():
                    continue
                blocks.append(
                    {
                        "type": "TEXT",
                        "bbox": [float(value) for value in block[:4]],
                        "text": block_text,
                    }
                )
            drawings = page.get_drawings() or []
            images = page.get_images(full=True) or []
            visual_blocks = []
            if len(drawings) >= 3 or images:
                visual_blocks.append(
                    {
                        "id": f"VISUAL-P{index + 1}-1",
                        "type": "FLOWCHART_OR_DIAGRAM",
                        "page_number": index + 1,
                        "bbox": [
                            float(page.rect.x0),
                            float(page.rect.y0),
                            float(page.rect.x1),
                            float(page.rect.y1),
                        ],
                        "drawing_count": len(drawings),
                        "image_count": len(images),
                        "needs_review": True,
                    }
                )
            usable = _text_layer_is_usable(text)
            quality_flags = [] if usable else ["TEXT_LAYER_INSUFFICIENT"]
            if visual_blocks:
                quality_flags.append("VISUAL_REVIEW_REQUIRED")
            pages.append(
                {
                    "page_number": index + 1,
                    "text": text,
                    "original_text": text,
                    "extraction_method": "TEXT" if usable else "OCR_PENDING",
                    "quality_flags": quality_flags,
                    "layout_blocks": blocks,
                    "visual_blocks": visual_blocks,
                }
            )
            if progress_callback:
                progress_callback(
                    {
                        "stage": "TEXT_EXTRACTION",
                        "page_number": index + 1,
                        "total_pages": document.page_count,
                    }
                )
        return pages
    finally:
        document.close()


def extract_text_or_ocr_pdf(
    pdf_path: str,
    languages: list[str],
    gpu: bool | None = None,
    poppler_path: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Use native text per page and OCR only pages whose text layer is unusable."""
    pages = extract_pdf_text_pages(pdf_path, progress_callback=progress_callback)
    fallback_pages = [
        page["page_number"] for page in pages if page["extraction_method"] == "OCR_PENDING"
    ]
    if not fallback_pages:
        return pages
    ocr_by_page = {
        page["page_number"]: page
        for page in stream_and_ocr_pdf(
            pdf_path,
            languages,
            gpu=gpu,
            poppler_path=poppler_path,
            page_numbers=fallback_pages,
            progress_callback=progress_callback,
        )
    }
    merged = []
    for page in pages:
        replacement = ocr_by_page.get(page["page_number"])
        if replacement:
            replacement["quality_flags"] = list(page.get("quality_flags") or [])
            replacement["visual_blocks"] = list(page.get("visual_blocks") or [])
            replacement["layout_blocks"] = [
                *replacement.get("layout_blocks", []),
                *page.get("visual_blocks", []),
            ]
            merged.append(replacement)
        else:
            merged.append(page)
    return merged
