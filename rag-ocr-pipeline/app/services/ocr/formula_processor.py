import re
from typing import List, Dict, Any
from app.services.ocr.text_cleaner import is_code_line

try:
    from sympy import SympifyError, sympify
    HAS_SYMPY = True
except ImportError:
    HAS_SYMPY = False

def _raw_to_latex(raw: str) -> str:
    latex = raw.strip()
    latex = re.sub(r"\^(\d{2,}|[+-]\d+|[a-zA-Z]{2,})", r"^{\1}", latex)
    latex = re.sub(r"_(\d{2,}|[a-zA-Z]{2,})", r"_{\1}", latex)
    latex = re.sub(r"\b(\w+)\s*/\s*(\w+)\b", lambda m: f"\\frac{{{m.group(1)}}}{{{m.group(2)}}}" if len(m.group(1)) <= 5 and len(m.group(2)) <= 5 else m.group(0), latex)
    latex = re.sub(r"(?<![a-zA-Z])sqrt\(([^)]+)\)|√\(([^)]+)\)|√(\w+)", r"\\sqrt{\1\2\3}", latex, flags=re.IGNORECASE)
    
    for func in ["sin", "cos", "tan", "cot", "log", "ln", "lim", "exp", "min", "max", "mod"]:
        latex = re.sub(rf"(?<![a-zA-Z]){func}(?![a-zA-Z])", rf"\\{func}", latex, flags=re.IGNORECASE)
        
    replacements = {"±": "\\pm", "×": "\\times", "÷": "\\div", "∑": "\\sum", "∫": "\\int", "∞": "\\infty", "≤": "\\leq", "≥": "\\geq", "≠": "\\neq", "≈": "\\approx"}
    for k, v in replacements.items(): latex = latex.replace(k, v)
    return latex

def _make_formula_block(formula_id: int, raw_ocr: str, context_before: str = "", context_after: str = "", formula_name: str = "") -> str:
    latex = _raw_to_latex(raw_ocr)
    name_line = f"  <NAME>{formula_name.strip()}</NAME>\n" if formula_name.strip() else ""
    return f"""<FORMULA_BLOCK id="F{formula_id}">
{name_line}  <RAW_OCR>{raw_ocr.strip()}</RAW_OCR>
  <LATEX>{latex}</LATEX>
  <CONTEXT_BEFORE>{context_before.strip()}</CONTEXT_BEFORE>
  <CONTEXT_AFTER>{context_after.strip()}</CONTEXT_AFTER>
</FORMULA_BLOCK>"""

def process_pages_with_formula_blocks(pages: list) -> list:
    """
    Quét qua các page, nếu thấy dòng nào bị kẹp giữa $$...$$ (hoặc có dấu hiệu toán học),
    chuyển nó thành cấu trúc <FORMULA_BLOCK> rõ ràng.
    """
    result = []
    formula_counter = 1
    for page in pages:
        text = page.get("text", "")
        lines = text.split("\n") if text else []
        blocks = []
        new_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("$$") and stripped.endswith("$$"):
                raw_formula = stripped.replace("$$", "").strip()
                ctx_before = lines[i-1].strip() if i > 0 else ""
                ctx_after = lines[i+1].strip() if i < len(lines)-1 else ""
                
                # Cố gắng đoán tên định lý/công thức
                name = ""
                if "công thức" in ctx_before.lower() or "định lý" in ctx_before.lower():
                    name = ctx_before
                
                block = _make_formula_block(formula_counter, raw_formula, ctx_before, ctx_after, name)
                blocks.append(block)
                formula_counter += 1
                # Thay dòng cũ bằng tham chiếu block
                new_lines.append(block)
            else:
                new_lines.append(line)
                
        result.append({
            **page,
            "text": "\n".join(new_lines),
            "formula_blocks": blocks,
        })
    return result