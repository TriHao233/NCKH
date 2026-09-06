from __future__ import annotations

import base64
import html
import re
from typing import Any

from markupsafe import Markup


MAX_INLINE_IMAGE_BYTES = 5 * 1024 * 1024
_DATA_IMAGE_RE = re.compile(
    r"^data:image/(?P<format>png|jpe?g|gif|webp);base64,(?P<data>[A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)
_INLINE_RE = re.compile(
    r"(!\[(?P<alt>[^\]]*)\]\((?P<src>data:image/[^)]+)\)"
    r"|`(?P<code>[^`\n]+)`"
    r"|\$(?P<math>[^$\n]+)\$"
    r"|\*\*(?P<strong>.+?)\*\*)"
)
_FORMULA_BLOCK_RE = re.compile(
    r"<FORMULA_BLOCK\b[^>]*>.*?<LATEX>(?P<latex>.*?)</LATEX>.*?</FORMULA_BLOCK>",
    re.IGNORECASE | re.DOTALL,
)


def decode_data_image(source: str) -> bytes | None:
    match = _DATA_IMAGE_RE.fullmatch(source.strip())
    if not match:
        return None
    try:
        payload = base64.b64decode(match.group("data"), validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    if not payload or len(payload) > MAX_INLINE_IMAGE_BYTES:
        return None
    return payload


def latex_to_readable(value: str) -> str:
    """Convert the common OCR/generated LaTeX subset to readable Unicode text."""
    text = html.unescape(str(value or "").strip())
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", text)
        text = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", text)
    replacements = {
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\delta": "δ",
        r"\theta": "θ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\pi": "π",
        r"\sigma": "σ",
        r"\phi": "φ",
        r"\omega": "ω",
        r"\times": "×",
        r"\div": "÷",
        r"\pm": "±",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\neq": "≠",
        r"\approx": "≈",
        r"\infty": "∞",
        r"\sum": "∑",
        r"\int": "∫",
        r"\rightarrow": "→",
        r"\left": "",
        r"\right": "",
        r"\,": " ",
        r"\;": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\\(sin|cos|tan|cot|log|ln|lim|exp|min|max|mod)\b", r"\1", text)
    text = re.sub(r"\^\{([^{}]+)\}", r"^(\1)", text)
    text = re.sub(r"_\{([^{}]+)\}", r"_(\1)", text)
    text = text.replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", text).strip()


def parse_inline(text: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    cursor = 0
    for match in _INLINE_RE.finditer(str(text or "")):
        if match.start() > cursor:
            values.append({"kind": "text", "text": text[cursor : match.start()]})
        if match.group("code") is not None:
            values.append({"kind": "code", "text": match.group("code")})
        elif match.group("math") is not None:
            values.append({"kind": "math", "text": latex_to_readable(match.group("math"))})
        elif match.group("strong") is not None:
            values.append({"kind": "strong", "text": match.group("strong")})
        else:
            source = match.group("src") or ""
            image = decode_data_image(source)
            values.append(
                {
                    "kind": "image" if image else "text",
                    "text": match.group("alt") or "Hình minh họa",
                    "source": source if image else "",
                    "image": image,
                }
            )
        cursor = match.end()
    if cursor < len(text):
        values.append({"kind": "text", "text": text[cursor:]})
    return values or [{"kind": "text", "text": ""}]


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def parse_rich_text(value: Any) -> list[dict[str, Any]]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _FORMULA_BLOCK_RE.sub(lambda match: f"\n$$\n{match.group('latex').strip()}\n$$\n", text)
    lines = text.split("\n")
    blocks: list[dict[str, Any]] = []
    index = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append({"kind": "paragraph", "inlines": parse_inline("\n".join(paragraph))})
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append({"kind": "code", "language": language, "text": "\n".join(code_lines)})
            continue
        if stripped == "$$":
            flush_paragraph()
            formula_lines = []
            index += 1
            while index < len(lines) and lines[index].strip() != "$$":
                formula_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append({"kind": "math", "text": latex_to_readable(" ".join(formula_lines))})
            continue
        if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
            flush_paragraph()
            blocks.append({"kind": "math", "text": latex_to_readable(stripped[2:-2])})
            index += 1
            continue
        if index + 1 < len(lines) and "|" in line and _is_table_separator(lines[index + 1]):
            flush_paragraph()
            header = _table_cells(line)
            rows = []
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                row = _table_cells(lines[index])
                rows.append((row + [""] * len(header))[: len(header)])
                index += 1
            blocks.append({"kind": "table", "header": header, "rows": rows})
            continue
        paragraph.append(line)
        index += 1
    flush_paragraph()
    return blocks


def _inline_html(inlines: list[dict[str, Any]]) -> str:
    rendered = []
    for item in inlines:
        kind = item["kind"]
        text = html.escape(str(item.get("text") or "")).replace("\n", "<br>")
        if kind == "code":
            rendered.append(f'<code class="inline-code">{text}</code>')
        elif kind == "math":
            rendered.append(f'<math class="inline-math"><mtext>{text}</mtext></math>')
        elif kind == "strong":
            rendered.append(f"<strong>{text}</strong>")
        elif kind == "image":
            source = html.escape(str(item["source"]), quote=True)
            rendered.append(f'<img class="inline-image" src="{source}" alt="{text}">')
        else:
            rendered.append(text)
    return "".join(rendered)


def render_rich_html(value: Any) -> Markup:
    rendered = []
    for block in parse_rich_text(value):
        kind = block["kind"]
        if kind == "paragraph":
            rendered.append(f'<p class="rich-paragraph">{_inline_html(block["inlines"])}</p>')
        elif kind == "code":
            language = html.escape(str(block.get("language") or ""), quote=True)
            code = html.escape(str(block.get("text") or ""))
            rendered.append(f'<pre class="code-block" data-language="{language}"><code>{code}</code></pre>')
        elif kind == "math":
            formula = html.escape(str(block.get("text") or ""))
            rendered.append(f'<div class="math-block"><math display="block"><mtext>{formula}</mtext></math></div>')
        elif kind == "table":
            headers = "".join(f"<th>{_inline_html(parse_inline(cell))}</th>" for cell in block["header"])
            rows = "".join(
                "<tr>" + "".join(f"<td>{_inline_html(parse_inline(cell))}</td>" for cell in row) + "</tr>"
                for row in block["rows"]
            )
            rendered.append(f'<table class="rich-table"><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>')
    return Markup("".join(rendered))
