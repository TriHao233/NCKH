from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from modules.generation.schemas import GeneratedQuestion, GenerationRejection


POSTPROCESSOR_VERSION = "question-post-v2"
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
    normalized_expected = normalize_exact_text(expected)
    if not normalized_expected:
        return False
    normalized_container = normalize_exact_text(container)
    pattern = rf"(?<!\w){re.escape(normalized_expected)}(?!\w)"
    return re.search(pattern, normalized_container, flags=re.UNICODE) is not None


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
        if any(_near_duplicate(fingerprint, seen) for seen in seen_question_fingerprints):
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
    if not contains_exact_text(context_text, source_context):
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
    if len(keywords) > MAX_SOURCE_KEYWORDS:
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
        if not contains_exact_text(source_context, keyword):
            errors.append(
                _rejection(
                    "KEYWORD_NOT_IN_EVIDENCE",
                    f"Keyword '{keyword}' không xuất hiện chính xác trong source_context.",
                    item=item,
                    candidate_index=candidate_index,
                    repairable=False,
                )
            )
        elif question_type == "dung_sai" and not contains_exact_text(statement, keyword):
            errors.append(
                _rejection(
                    "KEYWORD_NOT_IN_STATEMENT",
                    f"Keyword '{keyword}' chưa được dùng nguyên dạng trong mệnh đề Đúng/Sai.",
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


def rejection_counts(rejections: Iterable[GenerationRejection]) -> dict[str, int]:
    counts = {"format": 0, "grounding": 0, "clarity": 0}
    for rejection in rejections:
        if rejection.code.startswith(("SOURCE_", "KEYWORD_", "FALSE_", "MUTATION_", "TRUE_STATEMENT_")):
            counts["grounding"] += 1
        elif rejection.code in {
            "STATEMENT_TOO_LONG",
            "STATEMENT_IS_QUESTION",
            "MULTIPLE_PROPOSITIONS",
            "DOUBLE_NEGATION",
            "CONTEXT_DEPENDENT_STATEMENT",
        }:
            counts["clarity"] += 1
        else:
            counts["format"] += 1
    return counts
