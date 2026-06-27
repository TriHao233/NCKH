import re
from typing import List
from app.services.ocr.text_cleaner import is_code_line

FORMULA_START, FORMULA_END = "$$", "$$"
VIETNAMESE_CHAR_PATTERN = re.compile(
    r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
    r'ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]'
)

EXCLUSION_KEYWORDS = [
    'nhập', 'xuất', 'in giá trị', 'kết thúc', 'bắt đầu', 'kiểm tra',
    'miền giá trị', 'domain', 'kiểu dữ liệu', 'kích thước', 'ký hiệu', 'ý nghĩa',
    'sau khi gọi', 'trước khi', 'khi gọi', 'kết quả'
]
FORMULA_CONTEXT_KEYWORDS = [
    'công thức', 'biểu thức', 'phương trình', 'bất phương trình', 'hệ thức', 'đẳng thức', 
    'modulo', 'mod', 'tổng', 'tích', 'lũy thừa', 'mũ', 'căn', 'chia hết', 'ước số', 
    'bội số', 'tính', 'tìm', 'giải', 'chứng minh', 'nghiệm', 'phép tính', 'toán tử',
]

MATH_FUNC_PATTERN = re.compile(r'\b(sin|cos|tan|log|ln|sqrt|abs|min|max|sum|pow|mod|exp)\s*\(')
POWER_PATTERN = re.compile(r'[a-zA-Z_0-9]+\s*\^\s*[a-zA-Z_0-9]+')
COMPLEX_ASSIGNMENT_PATTERN = re.compile(r'^[a-zA-Z_]\w*\s*=\s*.*[+\-*/^]')

def _count_math_signals(line: str) -> int:
    score, stripped = 0, line.strip()
    if not stripped: return 0
    if '=' in stripped: score += 2 if any(op in stripped for op in ['+', '*', '/', '^']) else 1
    if MATH_FUNC_PATTERN.search(stripped): score += 3
    if POWER_PATTERN.search(stripped): score += 3
    if COMPLEX_ASSIGNMENT_PATTERN.match(stripped): score += 2
    score += len(re.findall(r'[+*/^]', stripped))
    return score

def is_formula_line(line: str, threshold_short: int = 5, threshold_long: int = 6) -> bool:
    stripped = line.strip()
    if not stripped or is_code_line(stripped) or (stripped.startswith(FORMULA_START) and stripped.endswith(FORMULA_END)): return False
    if len(stripped) > 60 or len(VIETNAMESE_CHAR_PATTERN.findall(stripped)) >= 3: return False
    if any(kw in stripped.lower() for kw in EXCLUSION_KEYWORDS): return False
    
    score = _count_math_signals(stripped)
    return score >= (threshold_short if len(stripped) <= 30 else threshold_long)

def mark_formulas_in_pages(pages: list) -> list:
    result = []
    for page in pages:
        lines = page.get("text", "").split('\n')
        result_lines = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or (stripped.startswith(FORMULA_START) and stripped.endswith(FORMULA_END)):
                result_lines.append(line)
                continue
            
            ctx = ' '.join(lines[max(0, i - 3):i]).lower()
            has_ctx = any(kw in ctx for kw in FORMULA_CONTEXT_KEYWORDS)
            t_short, t_long = (3, 4) if has_ctx else (5, 6)
            
            if is_formula_line(stripped, t_short, t_long):
                result_lines.append(f"{FORMULA_START}{stripped}{FORMULA_END}")
            else:
                result_lines.append(line)
        result.append({**page, "text": '\n'.join(result_lines)})
    return result