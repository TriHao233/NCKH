from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

VALID_EXPORT_TYPES = {"de", "dapan", "de_dapan"}


def _split_answer_keys(correct_answer: Any) -> list[str]:
    if not correct_answer:
        return []
    if isinstance(correct_answer, list):
        return [str(item).strip() for item in correct_answer]
    return [part.strip() for part in str(correct_answer).split(",") if part.strip()]


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
        correct_keys = set(_split_answer_keys(correct_answer))
        rendered_options = [
            {"label": key, "text": value, "correct": key in correct_keys}
            for key, value in options.items()
        ]
        rendered_questions.append(
            {
                "number": entry["order"],
                "content": snapshot.get("content", ""),
                "options": rendered_options,
            }
        )
        answer_rows.append(
            {
                "number": entry["order"],
                "answer": ", ".join(sorted(correct_keys)) if correct_keys else (correct_answer or ""),
            }
        )

    return {
        "header": header,
        "exam_code": exam_code,
        "questions": rendered_questions,
        "answer_rows": answer_rows,
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
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="load")
            pdf_bytes = await page.pdf(format="A4", print_background=True)
        finally:
            await browser.close()
    return pdf_bytes
