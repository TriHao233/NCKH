"""
Docling OCR Engine — gọi Docling container qua HTTP API.

Thay thế hoàn toàn EasyOCR. Output: Markdown có cấu trúc
(heading, table, code block, formula).
"""

import logging
from pathlib import Path
from typing import Any

import requests

from core.config import settings

logger = logging.getLogger(__name__)


def is_docling_available() -> bool:
    """Kiểm tra Docling service có hoạt động."""
    try:
        resp = requests.get(f"{settings.docling_url}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def ocr_pdf(file_path: str) -> dict[str, Any]:
    """
    Gửi PDF tới Docling, nhận về Markdown có cấu trúc.

    Returns
    -------
    dict với keys:
        - ``markdown``: toàn bộ nội dung dạng Markdown
        - ``pages``: list[dict] với ``page_number`` và ``text`` cho mỗi trang
        - ``metadata``: thông tin bổ sung từ Docling (nếu có)
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    logger.info("Gửi tài liệu tới Docling: %s", path.name)

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{settings.docling_url}/v1/convert",
            files={"file": (path.name, f, "application/pdf")},
            data={"output_format": "markdown"},
            timeout=settings.docling_timeout,
        )
    response.raise_for_status()
    result = response.json()

    markdown = result.get("markdown") or result.get("text") or ""

    # Docling có thể trả pages hoặc không — nếu không, tách từ markdown
    pages = result.get("pages")
    if not pages:
        pages = _split_markdown_to_pages(markdown)

    logger.info(
        "Docling hoàn tất: %d trang, %d ký tự",
        len(pages),
        len(markdown),
    )

    return {
        "markdown": markdown,
        "pages": pages,
        "metadata": result.get("metadata") or {},
    }


def _split_markdown_to_pages(markdown: str) -> list[dict[str, Any]]:
    """
    Nếu Docling trả markdown nguyên khối (không chia trang),
    tạo 1 page duy nhất chứa toàn bộ nội dung.
    """
    if not markdown.strip():
        return []
    return [
        {
            "page_number": 1,
            "text": markdown.strip(),
            "original_text": markdown.strip(),
            "formula_blocks": [],
        }
    ]
