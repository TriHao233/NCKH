import os
import gc
import shutil
import sys
import numpy as np
import logging
from threading import Lock
from pathlib import Path

from typing import Any
from pdf2image import pdfinfo_from_path, convert_from_path

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


def stream_and_ocr_pdf(pdf_path: str, languages: list[str], gpu: bool | None = None, poppler_path: str | None = None) -> list[dict[str, Any]]:
    """
    Đọc PDF và OCR cuốn chiếu từng trang để tối ưu hóa tối đa RAM/VRAM.
    """
    poppler = _resolve_poppler_path(poppler_path)

    # 1. Trích xuất thông tin PDF để lấy tổng số trang (Chỉ tốn vài KB RAM)
    info = pdfinfo_from_path(pdf_path, poppler_path=poppler)
    total_pages = info["Pages"]
    logger.info(f"Tài liệu có tổng cộng {total_pages} trang. Bắt đầu xử lý cuốn chiếu...")

    reader = get_reader(languages=languages, gpu=gpu)
    pages = []

    # 2. Vòng lặp cắt ảnh và OCR ngay lập tức
    for page_num in range(1, total_pages + 1):
        logger.info(f"Đang xử lý trang {page_num}/{total_pages}...")

        # TỐI ƯU 2: Chỉ cắt đúng 1 trang hiện tại
        images = convert_from_path(
            pdf_path,
            dpi=300,
            fmt="png",
            first_page=page_num,
            last_page=page_num,
            poppler_path=poppler
        )

        img = images[0]
        img_array = np.array(img)

        # TỐI ƯU 3: Tắt paragraph=True để tự kiểm soát cấu trúc layout
        results = reader.readtext(
            img_array,
            detail=1,
            paragraph=False,
            batch_size=4
        )

        # Tự Sort Bounding Box: Ưu tiên trục Y (dọc), sau đó trục X (ngang)
        # Giúp bảo toàn cấu trúc tài liệu nhiều cột
        results.sort(
            key=lambda item: (
                min(point[1] for point in item[0]),
                min(point[0] for point in item[0]),
            )
        )

        lines = [item[1] for item in results]
        page_text = "\n".join(lines)
        pages.append({"page_number": page_num, "text": page_text, "original_text": page_text})

        # TỐI ƯU 4: Xóa triệt để rác trong RAM trước khi sang trang mới
        del images
        del img
        del img_array
        del results
        gc.collect() # Ép Python dọn dẹp bộ nhớ ngay lập tức

    logger.info("Hoàn tất tiến trình OCR toàn bộ tài liệu!")
    return pages
