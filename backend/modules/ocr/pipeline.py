import os
import re
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from modules.ocr.docling_engine import is_docling_available, ocr_pdf
from modules.ocr.text_cleaner import clean_ocr_pages

logger = logging.getLogger(__name__)

def remove_headers_footers(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Tự động phát hiện và xóa Header/Footer (tiêu đề đầu/cuối trang lặp lại).
    Dùng thuật toán đếm tần suất (Counter): Nếu một chuỗi xuất hiện ở đầu/cuối
    trên 30% số trang, nó sẽ bị coi là header/footer và bị xóa bỏ.
    """
    if len(pages) < 3:
        return pages

    first_prefixes = []
    last_prefixes = []
    max_prefix_len = 50

    for page in pages:
        lines = page["text"].strip().split("\n")
        if len(lines) >= 2:
            for line in lines[:3]:
                stripped = line.strip()
                if stripped:
                    first_prefixes.append(stripped[:max_prefix_len].strip())
            for line in lines[-3:]:
                stripped = line.strip()
                if stripped:
                    last_prefixes.append(stripped[:max_prefix_len].strip())

    threshold = max(3, len(pages) * 0.3)
    common_headers = {prefix for prefix, count in Counter(first_prefixes).items() if count >= threshold}
    common_footers = {prefix for prefix, count in Counter(last_prefixes).items() if count >= threshold}

    page_number_pattern = re.compile(r"^\s*\d+\s*$")
    cleaned_pages: list[dict[str, Any]] = []

    for page in pages:
        lines = page["text"].strip().split("\n")
        filtered_lines = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Xử lý 3 dòng đầu (Header)
            if i < 3:
                skip = False
                modified_line = None
                for header in common_headers:
                    if line_stripped == header:
                        skip = True
                        break
                    if line_stripped.startswith(header) and len(line_stripped) > len(header) + 3:
                        modified_line = line_stripped[len(header) :].strip()
                        break
                if skip: continue
                if modified_line is not None:
                    filtered_lines.append(modified_line)
                    continue

            # Xử lý 3 dòng cuối (Footer)
            if i >= len(lines) - 3:
                skip_footer = False
                for footer in common_footers:
                    if line_stripped == footer or line_stripped.startswith(footer):
                        skip_footer = True
                        break
                if skip_footer: continue

            # Bỏ số trang đứng đơn độc
            if page_number_pattern.match(line_stripped): continue

            # Bỏ dòng bản quyền
            if any(keyword in line_stripped.lower() for keyword in ["bản quyền", "copyright", "©", "all rights reserved"]):
                continue

            filtered_lines.append(line)

        cleaned_pages.append({"page_number": page["page_number"], "text": "\n".join(filtered_lines)})

    return cleaned_pages


def save_markdown(pages: list[dict[str, Any]], output_path: str, document_title: str) -> None:
    """Lưu kết quả cuối cùng ra file Markdown để dùng cho Chunking hoặc người dùng đọc"""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"# OCR Result - {document_title}\n\n")
        f.write(f"**Tổng số trang:** {len(pages)}\n\n---\n\n")

        for page in pages:
            f.write(f"## Page {page['page_number']}\n\n")
            if page["text"].strip():
                f.write(page["text"] + "\n\n")
            else:
                f.write("*(Trang trống hoặc không có nội dung văn bản)*\n\n")

            formula_blocks = page.get("formula_blocks", [])
            if formula_blocks:
                f.write("### Formula Blocks\n\n")
                f.write("\n\n".join(formula_blocks) + "\n\n")

            f.write("---\n\n")


def run_ocr_pipeline(
    pdf_path: str,
    output_path: str,
    document_title: str | None = None,
    # Legacy params — ignored (kept for backward compatibility with callers)
    languages: list[str] | None = None,
    gpu: bool | None = None,
    poppler_path: str | None = None,
) -> dict[str, Any]:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"File not found: {pdf_path}")

    if not is_docling_available():
        raise RuntimeError(
            "Docling service không khả dụng. "
            "Hãy chắc chắn container 'nckh-docling' đang chạy: "
            "docker compose up docling -d"
        )

    title = document_title or Path(pdf_path).stem.replace("_", " ")
    logger.info(f"====== BẮT ĐẦU TIẾN TRÌNH OCR (Docling): {title} ======")

    # Gọi Docling API — nhận về Markdown có cấu trúc
    result = ocr_pdf(pdf_path)
    raw_pages = result["pages"]

    logger.info("[Filter 1/2] Đang xóa Header/Footer trùng lặp...")
    no_header_footer_pages = remove_headers_footers(raw_pages)

    # Docling đã output Markdown sạch, chỉ cần clean nhẹ
    logger.info("[Filter 2/2] Đang làm sạch văn bản...")
    final_pages = clean_ocr_pages(no_header_footer_pages)

    total_chars = sum(len(p["text"]) for p in final_pages)

    stats_data = {
        "total_pages": len(final_pages),
        "total_chars": total_chars,
        "avg_chars_per_page": round(total_chars / max(len(final_pages), 1)),
        "ocr_engine": "docling",
    }

    logger.info(f"Đang lưu kết quả Markdown tại: {output_path}")
    save_markdown(final_pages, output_path=output_path, document_title=title)

    logger.info(f"====== HOÀN TẤT OCR: {len(final_pages)} trang, {total_chars} ký tự ======")

    return {
        "pages": final_pages,
        "output_file": output_path,
        "stats": stats_data,
    }
