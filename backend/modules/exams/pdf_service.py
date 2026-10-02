from __future__ import annotations

import base64
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Mm, Pt, RGBColor
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

VALID_EXPORT_TYPES = {"de", "dapan", "de_dapan"}
EXAM_FONT_NAME = "Times New Roman"
EXAM_FONT_SIZE_PT = 13
EXAM_LINE_SPACING = 1.3
EXAM_FONT_FILES = {
    ("normal", "normal"): "times.ttf",
    ("bold", "normal"): "timesbd.ttf",
    ("normal", "italic"): "timesi.ttf",
    ("bold", "italic"): "timesbi.ttf",
}


def _pdf_font_faces() -> str:
    """Embed locally supplied Times fonts so Chromium does not silently substitute them."""
    font_dir = Path(os.environ.get("EXAM_FONT_DIR") or Path(__file__).resolve().parents[2] / "data" / "exam_fonts")
    if not all((font_dir / filename).is_file() for filename in EXAM_FONT_FILES.values()):
        return ""
    return "\n".join(
        f'@font-face {{ font-family: "Exam Times New Roman"; font-style: {style}; '
        f'font-weight: {weight}; src: url(data:font/ttf;base64,'
        f'{base64.b64encode((font_dir / filename).read_bytes()).decode("ascii")}) format("truetype"); }}'
        for (weight, style), filename in EXAM_FONT_FILES.items()
    )


def _split_answer_keys(correct_answer: Any) -> list[str]:
    if correct_answer is None or correct_answer == "":
        return []
    if isinstance(correct_answer, list):
        return [str(item).strip() for item in correct_answer]
    return [part.strip() for part in str(correct_answer).split(",") if part.strip()]


def _option_sort_key(item: tuple[str, Any]) -> tuple[int, int | str]:
    key = str(item[0])
    return (0, int(key)) if key.isdigit() else (1, key.casefold())


def _build_context(
    header: dict,
    exam_code: str,
    questions: list[dict],
    export_type: str,
) -> dict:
    show_questions = export_type in {"de", "de_dapan"}
    show_answers = export_type == "de_dapan"
    show_answer_table = export_type in {"dapan", "de_dapan"}

    rendered_questions = []
    answer_rows = []
    for entry in sorted(questions, key=lambda item: item["order"]):
        snapshot = entry["content_snapshot"]
        question_data = snapshot.get("question_data") or {}
        options = question_data.get("options") or {}
        correct_answer = question_data.get("correct_answer")
        answer_parts = _split_answer_keys(correct_answer)
        correct_keys = set(answer_parts)
        question_type = str((snapshot.get("classification") or {}).get("assessment_type") or "").lower()
        structured = question_type in {"sap_xep", "ghep_cot"}
        rendered_options = [
            {"label": key, "text": value, "correct": not structured and key in correct_keys}
            for key, value in sorted(options.items(), key=_option_sort_key)
        ]
        rendered_questions.append(
            {
                "number": entry["order"],
                "content": snapshot.get("content", ""),
                "question_type": question_type,
                "options": rendered_options,
                "numbered_options": [option for option in rendered_options if str(option["label"]).isdigit()],
                "lettered_options": [option for option in rendered_options if str(option["label"]).isalpha()],
            }
        )
        answer_rows.append(
            {
                "number": entry["order"],
                "answer": ", ".join(answer_parts),
            }
        )

    return {
        "header": header,
        "exam_code": exam_code,
        "questions": rendered_questions,
        "answer_rows": answer_rows,
        "answer_groups": [answer_rows[index:index + 10] for index in range(0, len(answer_rows), 10)],
        "show_questions": show_questions,
        "show_answers": show_answers,
        "show_answer_table": show_answer_table,
    }


def render_exam_html(
    header: dict,
    exam_code: str,
    questions: list[dict],
    export_type: str,
) -> str:
    if export_type not in VALID_EXPORT_TYPES:
        raise ValueError(f"export_type không hợp lệ: {export_type}")
    template = _env.get_template("exam_pdf.html")
    context = _build_context(header, exam_code, questions, export_type)
    context["font_faces"] = _pdf_font_faces()
    return template.render(**context)


async def render_exam_pdf(
    header: dict,
    exam_code: str,
    questions: list[dict],
    export_type: str,
) -> bytes:
    if not questions:
        raise ValueError("Đề thi chưa có câu hỏi, không thể xuất PDF")
    html = render_exam_html(header, exam_code, questions, export_type)
    font_faces = _pdf_font_faces()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="load")
            pdf_bytes = await page.pdf(
                format="A4",
                prefer_css_page_size=True,
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=(
                    f'<style>{font_faces}</style>'
                    '<div style="width:100%;font-family:Exam Times New Roman,Times New Roman,Liberation Serif,serif;'
                    'font-size:13pt;line-height:1.3;text-align:center;color:#000;">'
                    'Trang <span class="pageNumber"></span>/<span class="totalPages"></span></div>'
                ),
            )
        finally:
            await browser.close()
    return pdf_bytes


def _add_labeled_line(document: Document, label: str, value: Any) -> None:
    if value in (None, ""):
        return
    paragraph = document.add_paragraph()
    paragraph.add_run(f"{label}: ").bold = True
    paragraph.add_run(str(value))


def render_exam_docx(
    header: dict,
    exam_code: str,
    questions: list[dict],
    export_type: str,
) -> bytes:
    if export_type not in VALID_EXPORT_TYPES:
        raise ValueError(f"export_type không hợp lệ: {export_type}")
    if not questions:
        raise ValueError("Đề thi chưa có câu hỏi, không thể xuất DOCX")

    context = _build_context(header, exam_code, questions, export_type)
    document = Document()
    section = document.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(20)
    section.bottom_margin = Mm(20)
    section.left_margin = Mm(30)
    section.right_margin = Mm(20)
    for style_name in ("Normal", "Heading 1", "Heading 2", "Table Grid"):
        style = document.styles[style_name]
        style.font.name = EXAM_FONT_NAME
        style.font.size = Pt(EXAM_FONT_SIZE_PT)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.line_spacing = EXAM_LINE_SPACING

    if header.get("school_name"):
        document.add_paragraph(str(header["school_name"]))
    if header.get("faculty_name"):
        document.add_paragraph(str(header["faculty_name"]))

    title = document.add_heading(header.get("exam_name") or "Đề thi", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    _add_labeled_line(document, "Mã đề", exam_code)
    _add_labeled_line(document, "Môn học", header.get("subject_name"))
    if header.get("duration_minutes"):
        _add_labeled_line(document, "Thời gian", f"{header.get('duration_minutes')} phút")
    _add_labeled_line(document, "Lớp", header.get("class_name"))
    _add_labeled_line(document, "Phòng", header.get("room"))
    _add_labeled_line(document, "Ngày thi", header.get("exam_date"))

    if context["show_questions"]:
        document.add_paragraph()
        for question in context["questions"]:
            paragraph = document.add_paragraph()
            paragraph.add_run(f"Câu {question['number']}. ").bold = True
            paragraph.add_run(str(question["content"]))
            if question["question_type"] == "ghep_cot":
                numbered = question["numbered_options"]
                lettered = question["lettered_options"]
                table = document.add_table(rows=1 + max(len(numbered), len(lettered)), cols=2)
                table.style = "Table Grid"
                table.cell(0, 0).text = "Cột số"
                table.cell(0, 1).text = "Cột chữ"
                for index, option in enumerate(numbered, start=1):
                    table.cell(index, 0).text = f"{option['label']}. {option['text']}"
                for index, option in enumerate(lettered, start=1):
                    table.cell(index, 1).text = f"{option['label']}. {option['text']}"
                continue
            if question["question_type"] == "sap_xep":
                document.add_paragraph("Các bước cần sắp xếp:")
            for option in question["options"]:
                option_paragraph = document.add_paragraph(style=None)
                option_paragraph.paragraph_format.left_indent = Pt(18)
                run = option_paragraph.add_run(f"{option['label']}. {option['text']}")
                if context["show_answers"] and option["correct"]:
                    run.bold = True

    if context["show_answer_table"]:
        document.add_paragraph()
        document.add_heading("Đáp án", level=2)
        table = document.add_table(rows=1, cols=2)
        table.style = "Table Grid"
        header_cells = table.rows[0].cells
        header_cells[0].text = "Câu"
        header_cells[1].text = "Đáp án"
        for row in context["answer_rows"]:
            cells = table.add_row().cells
            cells[0].text = str(row["number"])
            cells[1].text = str(row["answer"])

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
