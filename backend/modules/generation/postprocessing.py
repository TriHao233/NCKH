from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from modules.generation.schemas import GeneratedQuestion, GenerationRejection


POSTPROCESSOR_VERSION = "question-post-v7"
MAX_TRUE_FALSE_LENGTH = 320
MAX_SOURCE_KEYWORDS = 6


@dataclass(frozen=True)
class DuplicateStats:
    exact: int = 0
    near: int = 0

    @property
    def total(self) -> int:
        return self.exact + self.near


def normalize_exact_text(value: str) -> str:
    """Normalize only representation details; accents and punctuation stay intact."""
    normalized = unicodedata.normalize("NFC", str(value or "")).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def contains_exact_text(container: str, expected: str) -> bool:
    return find_source_span(container, expected) is not None


def find_source_span(container: str, expected: str) -> tuple[int, int] | None:
    """Locate a quote while retaining offsets into the original OCR text.

    Fold case/Unicode and presentation separators only. Never drop words,
    negations, numbers, or mathematical operators.
    """
    def compact(value: str):
        chars, offsets = [], []
        for match in re.finditer(r"[^\u0300-\u036f][\u0300-\u036f]*", value):
            token = unicodedata.normalize("NFC", match.group()).casefold()
            for char in token:
                if char.isspace():
                    continue
                if char in "•◦▪●\"'`“”‘’":
                    continue
                if char in "-*" and (
                    not value[:match.start()].rsplit("\n", 1)[-1].strip()
                    and value[match.end():match.end() + 1].isspace()
                ):
                    continue
                # EasyOCR frequently emits the round list marker as a plain
                # lowercase `o`. Ignore it only at the beginning of a line;
                # letters inside prose, identifiers and formulas remain exact.
                if char == "o" and (
                    not value[:match.start()].rsplit("\n", 1)[-1].strip()
                    and value[match.end():match.end() + 1].isspace()
                ):
                    continue
                if char in '.,;:!?' and (match.end() == len(value) or value[match.end()].isspace()):
                    continue
                chars.append(char)
                offsets.append((match.start(), match.end()))
        return "".join(chars), offsets

    if not expected.strip():
        return None
    source, offsets = compact(container)
    quote, _ = compact(expected)
    if not quote:
        return None
    start = source.find(quote)
    while start >= 0:
        left, right = offsets[start][0], offsets[start + len(quote) - 1][1]
        if (left == 0 or not container[left - 1].isalnum()) and (
            right == len(container) or not container[right].isalnum()
        ):
            # Preserve a terminal full stop when both texts include it.
            if expected.rstrip().endswith('.') and container[right:right + 1] == '.':
                right += 1
            return left, right
        start = source.find(quote, start + 1)
    return None


def contains_source_keyword(container: str, expected: str) -> bool:
    def normalized(value: str) -> str:
        value = normalize_exact_text(value)
        value = re.sub(r"\bsẽ\b", " ", value)
        value = re.sub(r"[,.;:()“”\"‘’]", " ", value)
        return re.sub(r"\s+", " ", value).strip()

    keyword = normalized(expected)
    return bool(keyword) and re.search(
        rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized(container)
    ) is not None


def question_fingerprint(question: str) -> str:
    normalized = normalize_exact_text(question)
    normalized = re.sub(r"[_\W]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _near_duplicate(first: str, second: str) -> bool:
    if not first or not second:
        return False
    if first == second:
        return True

    first_tokens = set(first.split())
    second_tokens = set(second.split())
    union = first_tokens | second_tokens
    jaccard = len(first_tokens & second_tokens) / len(union) if union else 0.0
    containment = (
        len(first_tokens & second_tokens) / min(len(first_tokens), len(second_tokens))
        if first_tokens and second_tokens
        else 0.0
    )
    sequence_ratio = SequenceMatcher(None, first, second).ratio()

    # Short statements share many generic words, so use the stricter sequence gate.
    if min(len(first_tokens), len(second_tokens)) < 5:
        return sequence_ratio >= 0.96
    return (
        jaccard >= 0.88
        or sequence_ratio >= 0.94
        or (
            containment >= 0.92
            and abs(len(first_tokens) - len(second_tokens)) <= 4
        )
    )


def _plausible_near_duplicate(first: str, second: str) -> bool:
    """Cheap prefilter before the more expensive SequenceMatcher comparison."""
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    if not first_tokens or not second_tokens:
        return False
    length_ratio = min(len(first), len(second)) / max(len(first), len(second))
    if length_ratio < 0.55:
        return False
    overlap = len(first_tokens & second_tokens) / min(len(first_tokens), len(second_tokens))
    return overlap >= 0.5


def filter_duplicate_questions(
    questions: list[GeneratedQuestion],
    seen_question_fingerprints: set[str],
    *,
    limit: int,
) -> tuple[list[GeneratedQuestion], DuplicateStats]:
    kept: list[GeneratedQuestion] = []
    exact_count = 0
    near_count = 0

    for question in questions:
        fingerprint = question_fingerprint(question.question)
        if not fingerprint or fingerprint in seen_question_fingerprints:
            exact_count += 1
            continue
        if any(
            _near_duplicate(fingerprint, seen)
            for seen in seen_question_fingerprints
            if _plausible_near_duplicate(fingerprint, seen)
        ):
            near_count += 1
            continue
        seen_question_fingerprints.add(fingerprint)
        kept.append(question)
        if len(kept) >= limit:
            break

    return kept, DuplicateStats(exact=exact_count, near=near_count)


def _rejection(
    code: str,
    message: str,
    *,
    item: dict,
    candidate_index: int,
    repairable: bool,
) -> GenerationRejection:
    return GenerationRejection(
        code=code,
        message=message,
        candidate_index=candidate_index,
        question_excerpt=str(item.get("question") or "")[:180],
        repairable=repairable,
    )


def validate_source_grounding(
    item: dict,
    *,
    context_text: str,
    question_type: str,
    candidate_index: int,
) -> list[GenerationRejection]:
    errors: list[GenerationRejection] = []
    source_context = str(item.get("source_context") or "").strip()
    statement = str(item.get("question") or "").strip()

    if not source_context:
        errors.append(
            _rejection(
                "SOURCE_CONTEXT_MISSING",
                "Thiếu trích dẫn source_context để đối chiếu với ngữ cảnh RAG.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
        return errors
    if find_source_span(context_text, source_context) is None:
        errors.append(
            _rejection(
                "SOURCE_CONTEXT_NOT_FOUND",
                "source_context không phải trích dẫn nguyên văn trong context snapshot.",
                item=item,
                candidate_index=candidate_index,
                repairable=False,
            )
        )

    raw_keywords = item.get("source_keywords")
    keywords = raw_keywords if isinstance(raw_keywords, list) else []
    invalid_keyword_types = [keyword for keyword in keywords if not isinstance(keyword, str)]
    keywords = [keyword.strip() for keyword in keywords if isinstance(keyword, str) and keyword.strip()]
    mutation = item.get("false_mutation")
    if question_type == "dung_sai" and item.get("correct_answer") == "B" and isinstance(mutation, dict):
        original = str(mutation.get("original") or "")
        replacement = str(mutation.get("replacement") or "")
        if contains_exact_text(source_context, original) and contains_exact_text(statement, replacement):
            # A controlled false mutation necessarily removes its original text.
            # Such text is not an unchanged anchor; retain the other grounded anchors.
            keywords = [keyword for keyword in keywords if not (
                contains_source_keyword(original, keyword)
                and not contains_source_keyword(statement, keyword)
            )]
            item["source_keywords"] = keywords
    if question_type != "dung_sai":
        # Keywords are optional highlighting metadata for non true/false
        # questions. Keep only grounded values instead of rejecting an
        # otherwise traceable question because the model returned noisy tags.
        keywords = [
            keyword
            for keyword in keywords
            if contains_source_keyword(source_context, keyword)
        ][:MAX_SOURCE_KEYWORDS]
        item["source_keywords"] = keywords
        invalid_keyword_types = []
    if invalid_keyword_types:
        errors.append(
            _rejection(
                "SOURCE_KEYWORDS_INVALID",
                "source_keywords chỉ được chứa chuỗi không rỗng.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
    if question_type == "dung_sai" and not keywords:
        errors.append(
            _rejection(
                "SOURCE_KEYWORDS_MISSING",
                "Câu Đúng/Sai phải khai báo ít nhất một keyword neo từ nguồn.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
    if question_type == "dung_sai" and len(keywords) > MAX_SOURCE_KEYWORDS:
        errors.append(
            _rejection(
                "TOO_MANY_SOURCE_KEYWORDS",
                f"Chỉ cho phép tối đa {MAX_SOURCE_KEYWORDS} keyword nguồn.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )

    for keyword in keywords[:MAX_SOURCE_KEYWORDS]:
        if not contains_source_keyword(source_context, keyword):
            errors.append(
                _rejection(
                    "KEYWORD_NOT_IN_EVIDENCE",
                    f"Keyword '{keyword}' không đối chiếu được trong source_context sau chuẩn hóa.",
                    item=item,
                    candidate_index=candidate_index,
                    repairable=False,
                )
            )
        elif question_type == "dung_sai" and not contains_source_keyword(statement, keyword):
            errors.append(
                _rejection(
                    "KEYWORD_NOT_IN_STATEMENT",
                    f"Keyword '{keyword}' không đối chiếu được trong mệnh đề Đúng/Sai sau chuẩn hóa.",
                    item=item,
                    candidate_index=candidate_index,
                    repairable=True,
                )
            )

    if question_type == "dung_sai":
        answer = str(item.get("correct_answer") or "").strip()
        mutation = item.get("false_mutation")
        if answer == "B":
            if not isinstance(mutation, dict):
                errors.append(
                    _rejection(
                        "FALSE_MUTATION_MISSING",
                        "Câu Sai phải mô tả một phép biến đổi có kiểm soát từ evidence.",
                        item=item,
                        candidate_index=candidate_index,
                        repairable=True,
                    )
                )
            else:
                original = str(mutation.get("original") or "").strip()
                replacement = str(mutation.get("replacement") or "").strip()
                field = str(mutation.get("field") or "").strip()
                if not field or not original or not replacement or normalize_exact_text(original) == normalize_exact_text(replacement):
                    errors.append(
                        _rejection(
                            "FALSE_MUTATION_INVALID",
                            "false_mutation phải có field, original và replacement khác nhau.",
                            item=item,
                            candidate_index=candidate_index,
                            repairable=True,
                        )
                    )
                else:
                    if not contains_exact_text(source_context, original):
                        errors.append(
                            _rejection(
                                "MUTATION_ORIGINAL_NOT_IN_EVIDENCE",
                                "Giá trị original của câu Sai không có trong source_context.",
                                item=item,
                                candidate_index=candidate_index,
                                repairable=False,
                            )
                        )
                    if not contains_exact_text(statement, replacement):
                        errors.append(
                            _rejection(
                                "MUTATION_REPLACEMENT_NOT_IN_STATEMENT",
                                "Giá trị replacement của câu Sai không có trong mệnh đề.",
                                item=item,
                                candidate_index=candidate_index,
                                repairable=True,
                            )
                        )
        elif mutation not in (None, {}):
            errors.append(
                _rejection(
                    "TRUE_STATEMENT_HAS_MUTATION",
                    "Câu có đáp án Đúng không được khai báo false_mutation.",
                    item=item,
                    candidate_index=candidate_index,
                    repairable=True,
                )
            )

    return errors


def validate_true_false_clarity(
    item: dict,
    *,
    candidate_index: int,
) -> list[GenerationRejection]:
    statement = re.sub(r"\s+", " ", str(item.get("question") or "")).strip()
    normalized = normalize_exact_text(statement)
    errors: list[GenerationRejection] = []

    if len(statement) > MAX_TRUE_FALSE_LENGTH:
        errors.append(
            _rejection(
                "STATEMENT_TOO_LONG",
                f"Mệnh đề Đúng/Sai vượt quá {MAX_TRUE_FALSE_LENGTH} ký tự.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
    if statement.endswith("?"):
        errors.append(
            _rejection(
                "STATEMENT_IS_QUESTION",
                "Dạng Đúng/Sai phải là mệnh đề, không phải câu nghi vấn.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
    if ";" in statement or re.search(r"\b(đồng thời|trong khi|tuy nhiên|nhưng)\b", normalized):
        errors.append(
            _rejection(
                "MULTIPLE_PROPOSITIONS",
                "Mệnh đề có dấu hiệu gộp nhiều nhận định độc lập.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
    if len(re.findall(r"\b(không|chưa|chẳng)\b", normalized)) >= 2:
        errors.append(
            _rejection(
                "DOUBLE_NEGATION",
                "Mệnh đề chứa nhiều lớp phủ định và có thể gây mơ hồ.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
    if re.search(
        r"\b(theo tài liệu|theo giáo trình|nội dung trên|đoạn trên|điều này|như đã nêu|ở trên)\b",
        normalized,
    ):
        errors.append(
            _rejection(
                "CONTEXT_DEPENDENT_STATEMENT",
                "Mệnh đề phụ thuộc vào cách gọi nguồn hoặc ngữ cảnh bên ngoài.",
                item=item,
                candidate_index=candidate_index,
                repairable=True,
            )
        )
    return errors


def validate_question_quality(
    item: dict, *, question_type: str, candidate_index: int,
) -> list[GenerationRejection]:
    """Conservative, deterministic guards; pedagogical review remains human-owned."""
    errors = []

    def reject(code: str, message: str):
        errors.append(_rejection(
            code, message, item=item, candidate_index=candidate_index, repairable=True,
        ))

    statement = normalize_exact_text(item.get("question") or "")
    if item.get("question_type") not in (None, "", question_type):
        reject("QUESTION_TYPE_MISMATCH", "question_type phải đúng dạng được yêu cầu; không được đổi dạng.")
    if re.search(
        r"\b(theo (?:tài liệu|giáo trình)|(?:trong|ở|theo) ngữ cảnh|"
        r"(?:theo|trong) văn bản|được nêu trong (?:văn bản|nguồn)|"
        r"(?:nội dung|đoạn|thông tin) (?:trên|đã nêu)|như đã nêu ở trên)\b",
        statement,
    ):
        reject(
            "CONTEXT_DEPENDENT_QUESTION",
            "Câu hỏi phải tự đủ nghĩa, không được tham chiếu 'ngữ cảnh', 'đoạn trên' hoặc tài liệu bên ngoài.",
        )
    if question_type != "dien_khuyet" and re.search(r"\.{3,}|…", statement):
        reject(
            "QUESTION_PLACEHOLDER_ARTIFACT",
            "Câu hỏi chứa dấu chấm lửng như placeholder; phải viết câu dẫn hoàn chỉnh.",
        )
    if question_type in {"trac_nghiem", "tinh_huong", "nhieu_lua_chon"}:
        options = item.get("options") or {}
        correct_keys = [
            key.strip()
            for key in str(item.get("correct_answer") or "").split(",")
            if key.strip()
        ]
        for key in correct_keys:
            option = str(options.get(key) or "") if isinstance(options, dict) else ""
            if len(normalize_exact_text(option)) >= 20 and contains_source_keyword(statement, option):
                reject(
                    "CORRECT_OPTION_REPEATED_IN_STEM",
                    f"Thân câu đã chép nguyên nội dung đáp án đúng {key}, làm lộ đáp án.",
                )
                break
        if question_type == "nhieu_lua_chon" and isinstance(options, dict):
            for key, option in options.items():
                if len(normalize_exact_text(option)) >= 20 and contains_source_keyword(statement, option):
                    reject(
                        "OPTION_REPEATED_IN_STEM",
                        f"Thân câu đã chép nguyên nội dung lựa chọn {key}; các lựa chọn chỉ được đặt trong options.",
                    )
                    break
            source_context = str(item.get("source_context") or "")
            for key in correct_keys:
                option = str(options.get(key) or "")
                if len(re.findall(r"[^\W_]+", option, flags=re.UNICODE)) < 4:
                    reject(
                        "MULTIPLE_RESPONSE_CORRECT_OPTION_TOO_SHORT",
                        f"Phương án đúng {key} phải là một mệnh đề nguồn đủ nghĩa, không chỉ là nhãn/thuật ngữ ngắn.",
                    )
                    break
                if find_source_span(source_context, option) is None:
                    reject(
                        "MULTIPLE_RESPONSE_CORRECT_OPTION_UNGROUNDED",
                        f"Phương án đúng {key} phải xuất hiện nguyên văn trong source_context để kiểm chứng độc lập.",
                    )
                    break
    if question_type == "ghep_cot":
        options = item.get("options") or {}
        pairs = re.findall(r"(\d+)\s*-\s*([A-Za-z])", str(item.get("correct_answer") or ""))
        matched_right_keys = {right_key.upper() for _left_key, right_key in pairs}
        if not re.search(r"\bghép\b", statement):
            reject(
                "MATCHING_INSTRUCTION_MISSING",
                "Thân câu ghép cột phải yêu cầu người học ghép hai nhóm, không được viết thành câu hỏi một đáp án.",
            )
        source_context = str(item.get("source_context") or "")
        for right_key in matched_right_keys:
            description = str(options.get(right_key) or "").strip()
            without_leading_connector = re.sub(
                r"^(?:vì|do)\s+", "", description, flags=re.IGNORECASE,
            )
            if not any(
                find_source_span(source_context, candidate) is not None
                for candidate in (description, without_leading_connector)
                if candidate
            ):
                reject(
                    "MATCHING_DESCRIPTION_UNGROUNDED",
                    f"Mô tả đúng {right_key} phải xuất hiện nguyên vẹn trong source_context.",
                )
                break
        for left_key, right_key in pairs:
            left = question_fingerprint(str(options.get(left_key) or ""))
            right = question_fingerprint(str(options.get(right_key.upper()) or ""))
            left = re.sub(r"^(?:mục|bước)\s*\d+\s*", "", left).strip()
            right = re.sub(r"^(?:mục|bước)\s*\d+\s*", "", right).strip()
            if left and right and _near_duplicate(left, right):
                reject(
                    "MATCHING_PAIR_DUPLICATED",
                    f"Cặp {left_key}-{right_key.upper()} lặp cùng mô tả ở cả hai cột, làm lộ phép ghép.",
                )
                break
        used_descriptions = [
            question_fingerprint(str(options.get(key) or ""))
            for key in matched_right_keys
        ]
        for distractor_key in (
            key for key in options if key.isalpha() and key not in matched_right_keys
        ):
            distractor_tokens = question_fingerprint(
                str(options.get(distractor_key) or "")
            ).split()
            distractor_ngrams = {
                tuple(distractor_tokens[index:index + 4])
                for index in range(max(0, len(distractor_tokens) - 3))
            }
            if any(
                distractor_ngrams
                & {
                    tuple(answer_tokens[index:index + 4])
                    for index in range(max(0, len(answer_tokens) - 3))
                }
                for answer in used_descriptions
                if (answer_tokens := answer.split())
            ):
                reject(
                    "MATCHING_DISTRACTOR_OVERLAPS_ANSWER",
                    f"Phương án nhiễu {distractor_key} lặp một mệnh đề của mô tả đúng, làm phép ghép mơ hồ.",
                )
                break
    if question_type == "tinh_huong":
        actor = re.search(
            r"\b(sinh viên|học sinh|giảng viên|lập trình viên|kỹ sư|nhóm|người dùng|"
            r"bạn|hệ thống|chương trình|ứng dụng|máy chủ|quản trị viên|nhân viên)\b", statement,
        )
        context = re.search(
            r"\b(đang|cần|muốn|gặp|phải|nhận|yêu cầu|mục tiêu|bị|khi|giả sử)\b", statement,
        )
        decision = re.search(
            r"\b(nên|chọn|xử lý|khắc phục|giải pháp|thao tác|hành động|triển khai|"
            r"đề xuất|áp dụng|phù hợp|nguyên nhân|kết quả|thay đổi|thiết kế)\b", statement,
        )
        if not (actor and context and decision and "?" in statement):
            reject("SCENARIO_INCOMPLETE", "Tình huống cần chủ thể, bối cảnh cụ thể và câu hỏi quyết định/hành động áp dụng kiến thức.")
    if question_type == "dien_khuyet":
        if len(statement) > 320:
            reject("FILL_BLANK_TOO_LONG", "Thân câu điền khuyết tối đa 320 ký tự; chỉ giữ dữ kiện cần thiết.")
        answer = str(item.get("correct_answer") or "")
        if contains_source_keyword(statement.replace("_____", " "), answer):
            reject("FILL_BLANK_ANSWER_LEAK", "Thân câu điền khuyết đã nêu đáp án ở ngoài chỗ trống.")
    if question_type == "nhieu_lua_chon" and not re.search(
        r"\b(chọn\s+(?:tất cả|nhiều|mọi|các)|nhiều đáp án|những\b.+\bnào)\b", statement,
    ):
        reject("MULTIPLE_RESPONSE_INSTRUCTION_MISSING", "Câu nhiều lựa chọn phải báo rõ 'Chọn tất cả đáp án đúng' để người học biết cần chọn nhiều phương án.")
    if question_type == "sap_xep":
        source = str(item.get("source_context") or "")
        # Require an explicit source sequence, not merely unrelated mentions.
        markers = list(re.finditer(
            r"(?:(?:(?:^|\n)\s*(?:[-*•o]\s+)?|\b)(?:bước|step)\s+(\d+)\s*[:.)-]|(?:^|\n)\s*(\d+)\s*[.)])\s*",
            source, flags=re.IGNORECASE,
        ))
        numbers = [int(match.group(1) or match.group(2)) for match in markers]
        if len(numbers) < 4 or numbers != list(range(numbers[0], numbers[0] + len(numbers))):
            reject("ORDERING_SOURCE_UNVERIFIABLE", "Nguồn phải có ít nhất 4 bước đánh số liên tiếp; trích nguyên trình tự, không tự bịa thuật toán.")
            return errors
        if re.search(
            r"\b(quay lại|lặp lại|ngược lại|nếu|go to|goto|repeat|if|else|otherwise)\b",
            source,
            flags=re.IGNORECASE,
        ):
            reject("ORDERING_SOURCE_UNVERIFIABLE", "Nguồn có vòng lặp/rẽ nhánh, không chứng minh được một thứ tự thực hiện tuyến tính duy nhất.")
            return errors
        steps = [
            source[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(source)].strip()
            for index, marker in enumerate(markers)
        ]
        positions = {}
        for key, option in (item.get("options") or {}).items():
            matches = []
            for index, step in enumerate(steps):
                span = find_source_span(step, option)
                if span is not None and not (step[:span[0]] + step[span[1]:]).strip(" \n\r\t.,;:"):
                    matches.append(index)
            if len(matches) != 1:
                reject("ORDERING_STEP_NOT_GROUNDED", f"Bước {key} phải chép hành động từ đúng một bước trong nguồn, không thêm nội dung ngoài nguồn.")
            else:
                positions[key] = matches[0]
        keys = [key.strip() for key in str(item.get("correct_answer") or "").split(",")]
        if len(positions) == len(item.get("options") or {}):
            order = [positions[key] for key in keys if key in positions]
            if len(order) != len(positions) or len(set(order)) != len(order) or order != sorted(order):
                reject("ORDERING_INCORRECT", "correct_answer không theo trình tự các bước được đánh số trong source_context.")
    return errors


def rejection_counts(rejections: Iterable[GenerationRejection]) -> dict[str, int]:
    counts = {"format": 0, "grounding": 0, "clarity": 0}
    for rejection in rejections:
        if rejection.code.startswith(("SOURCE_", "KEYWORD_", "FALSE_", "MUTATION_", "TRUE_STATEMENT_", "ORDERING_")):
            counts["grounding"] += 1
        elif rejection.code in {
            "STATEMENT_TOO_LONG",
            "STATEMENT_IS_QUESTION",
            "MULTIPLE_PROPOSITIONS",
            "DOUBLE_NEGATION",
            "CONTEXT_DEPENDENT_STATEMENT",
            "SCENARIO_INCOMPLETE",
            "FILL_BLANK_TOO_LONG",
            "FILL_BLANK_ANSWER_LEAK",
            "MULTIPLE_RESPONSE_INSTRUCTION_MISSING",
            "CONTEXT_DEPENDENT_QUESTION",
            "QUESTION_PLACEHOLDER_ARTIFACT",
            "CORRECT_OPTION_REPEATED_IN_STEM",
            "OPTION_REPEATED_IN_STEM",
            "MATCHING_PAIR_DUPLICATED",
            "MULTIPLE_RESPONSE_CORRECT_OPTION_UNGROUNDED",
        }:
            counts["clarity"] += 1
        else:
            counts["format"] += 1
    return counts
