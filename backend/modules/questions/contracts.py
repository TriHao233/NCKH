from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class QuestionAssessmentType(str, Enum):
    TRAC_NGHIEM = "trac_nghiem"
    DUNG_SAI = "dung_sai"
    DIEN_KHUYET = "dien_khuyet"
    GHEP_COT = "ghep_cot"
    TINH_HUONG = "tinh_huong"
    SAP_XEP = "sap_xep"
    NHIEU_LUA_CHON = "nhieu_lua_chon"


QUESTION_TYPE_ALIASES = {
    "multiple_choice": QuestionAssessmentType.TRAC_NGHIEM.value,
    "single_choice": QuestionAssessmentType.TRAC_NGHIEM.value,
    "true_false": QuestionAssessmentType.DUNG_SAI.value,
    "fill_blank": QuestionAssessmentType.DIEN_KHUYET.value,
    "matching": QuestionAssessmentType.GHEP_COT.value,
    "scenario": QuestionAssessmentType.TINH_HUONG.value,
    "ordering": QuestionAssessmentType.SAP_XEP.value,
    "multiple_response": QuestionAssessmentType.NHIEU_LUA_CHON.value,
}


def normalize_question_type(value: str) -> str:
    normalized = re.sub(r"[\s-]+", "_", str(value or "").strip().lower())
    normalized = QUESTION_TYPE_ALIASES.get(normalized, normalized)
    try:
        return QuestionAssessmentType(normalized).value
    except ValueError as exc:
        raise ValueError(f"Dạng câu hỏi không được hỗ trợ: {value}") from exc


def _option_map(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = {chr(65 + index): item for index, item in enumerate(value)}
    if not isinstance(value, dict):
        raise ValueError("options phải là object hoặc danh sách tương thích dữ liệu cũ")
    normalized = {
        str(key).strip().upper(): str(item or "").strip()
        for key, item in value.items()
        if str(key).strip()
    }
    if not normalized or any(not item for item in normalized.values()):
        raise ValueError("options không được có phương án rỗng")
    return normalized


class BaseQuestionData(BaseModel):
    model_config = ConfigDict(extra="allow")

    options: dict[str, str] | None = None
    correct_answer: str = Field(..., min_length=1)
    explanation: str = ""
    model_source_context: str = ""
    source_keywords: list[str] = Field(default_factory=list)
    false_mutation: dict[str, Any] | None = None
    post_processing: dict[str, Any] = Field(default_factory=dict)

    @field_validator("options", mode="before")
    @classmethod
    def normalize_options(cls, value):
        return _option_map(value)

    @field_validator("correct_answer", "explanation", "model_source_context")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return str(value or "").strip()

    @field_validator("source_keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


class SingleChoiceData(BaseQuestionData):
    options: dict[str, str]

    @model_validator(mode="after")
    def validate_choice(self):
        if set(self.options) != {"A", "B", "C", "D"}:
            raise ValueError("Câu một đáp án phải có đúng options A/B/C/D")
        if self.correct_answer.upper() not in self.options:
            raise ValueError("correct_answer không tồn tại trong options")
        self.correct_answer = self.correct_answer.upper()
        return self


class TrueFalseData(BaseQuestionData):
    options: dict[str, str]

    @model_validator(mode="after")
    def validate_true_false(self):
        normalized_values = {key: value.casefold() for key, value in self.options.items()}
        if set(self.options) != {"A", "B"} or normalized_values != {"A": "đúng", "B": "sai"}:
            raise ValueError('Đúng/Sai bắt buộc options = {"A": "Đúng", "B": "Sai"}')
        self.correct_answer = self.correct_answer.upper()
        if self.correct_answer not in self.options:
            raise ValueError("Đáp án Đúng/Sai phải là A hoặc B")
        return self


class FillBlankData(BaseQuestionData):
    options: None = None


class MultipleResponseData(BaseQuestionData):
    options: dict[str, str]

    @model_validator(mode="after")
    def validate_multiple(self):
        expected = [chr(65 + index) for index in range(len(self.options))]
        if not 4 <= len(expected) <= 6 or list(self.options) != expected:
            raise ValueError("Nhiều lựa chọn phải có 4–6 options liên tiếp từ A")
        keys = [item.strip().upper() for item in re.split(r"[,;|]", self.correct_answer) if item.strip()]
        if len(set(keys)) < 2 or len(set(keys)) >= len(self.options):
            raise ValueError("Nhiều lựa chọn cần 2 đáp án trở lên nhưng không được chọn tất cả")
        if any(key not in self.options for key in keys):
            raise ValueError("correct_answer có khóa không tồn tại trong options")
        self.correct_answer = ",".join(dict.fromkeys(keys))
        return self


class MatchingData(BaseQuestionData):
    options: dict[str, str]

    @model_validator(mode="after")
    def validate_matching(self):
        numeric = {key for key in self.options if key.isdigit()}
        alpha = {key for key in self.options if key.isalpha()}
        if len(numeric) < 3 or len(alpha) < len(numeric) + 1:
            raise ValueError("Ghép cột cần ít nhất 3 vế số và thêm ít nhất 1 phương án nhiễu chữ")
        grammar = r"\s*\d+\s*-\s*[A-Za-z](?:\s*[,;|]\s*\d+\s*-\s*[A-Za-z])*\s*"
        if not re.fullmatch(grammar, self.correct_answer):
            raise ValueError("Đáp án ghép cột không đúng định dạng 1-A,2-B,...")
        pairs = re.findall(r"(\d+)\s*-\s*([A-Za-z])", self.correct_answer)
        left_keys = [left for left, _ in pairs]
        if len(left_keys) != len(set(left_keys)) or set(left_keys) != numeric:
            raise ValueError("Ghép cột phải ánh xạ đủ mọi vế số")
        if any(right.upper() not in alpha for _, right in pairs):
            raise ValueError("Ghép cột có đáp án không tồn tại")
        self.correct_answer = ",".join(f"{left}-{right.upper()}" for left, right in pairs)
        return self


class OrderingData(BaseQuestionData):
    options: dict[str, str]

    @model_validator(mode="after")
    def validate_ordering(self):
        if len(self.options) < 4:
            raise ValueError("Sắp xếp cần ít nhất 4 bước")
        keys = [item.strip().upper() for item in re.split(r"[,;|]", self.correct_answer) if item.strip()]
        if len(keys) != len(set(keys)) or set(keys) != set(self.options):
            raise ValueError("Đáp án sắp xếp phải liệt kê đúng một lần toàn bộ khóa options")
        self.correct_answer = ",".join(keys)
        return self


QUESTION_DATA_MODELS: dict[str, type[BaseQuestionData]] = {
    QuestionAssessmentType.TRAC_NGHIEM.value: SingleChoiceData,
    QuestionAssessmentType.TINH_HUONG.value: SingleChoiceData,
    QuestionAssessmentType.DUNG_SAI.value: TrueFalseData,
    QuestionAssessmentType.DIEN_KHUYET.value: FillBlankData,
    QuestionAssessmentType.NHIEU_LUA_CHON.value: MultipleResponseData,
    QuestionAssessmentType.GHEP_COT.value: MatchingData,
    QuestionAssessmentType.SAP_XEP.value: OrderingData,
}


def validate_question_contract(content: str, question_type: str, question_data: dict) -> tuple[str, dict]:
    normalized_type = normalize_question_type(question_type)
    normalized_content = re.sub(r"\s+", " ", str(content or "")).strip()
    if not normalized_content:
        raise ValueError("Nội dung câu hỏi không được rỗng")
    if normalized_type == QuestionAssessmentType.DIEN_KHUYET.value and "_____" not in normalized_content:
        raise ValueError("Câu điền khuyết phải chứa placeholder _____")
    try:
        typed = QUESTION_DATA_MODELS[normalized_type].model_validate(question_data or {})
    except ValidationError as exc:
        first = exc.errors()[0]
        raise ValueError(f"QUESTION_DATA_INVALID[{normalized_type}]: {first['msg']}") from exc
    return normalized_type, typed.model_dump(mode="python")
