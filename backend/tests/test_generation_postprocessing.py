import sys
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from modules.generation.postprocessing import (  # noqa: E402
    contains_exact_text,
    filter_duplicate_questions,
    question_fingerprint,
    validate_source_grounding,
    validate_true_false_clarity,
)
from modules.generation.schemas import GeneratedQuestion  # noqa: E402


CONTEXT = """
Mục lục: [Ngăn xếp]
Nội dung: Ngăn xếp (Stack) là cấu trúc dữ liệu tuân theo nguyên tắc LIFO (Last In First Out).
""".strip()


def candidate(**overrides):
    item = {
        "question": "Ngăn xếp (Stack) tuân theo nguyên tắc FIFO.",
        "options": {"A": "Đúng", "B": "Sai"},
        "correct_answer": "B",
        "explanation": "Ngăn xếp dùng LIFO, không phải FIFO.",
        "question_type": "dung_sai",
        "bloom_level": "2_hieu",
        "difficulty": "trung_binh",
        "source_context": (
            "Ngăn xếp (Stack) là cấu trúc dữ liệu tuân theo nguyên tắc "
            "LIFO (Last In First Out)."
        ),
        "source_keywords": ["Ngăn xếp (Stack)"],
        "false_mutation": {
            "field": "relation",
            "original": "LIFO",
            "replacement": "FIFO",
        },
    }
    item.update(overrides)
    return item


class GenerationPostProcessingTests(unittest.TestCase):
    def test_exact_matching_preserves_vietnamese_diacritics(self):
        self.assertTrue(contains_exact_text("Cây nhị phân", "cây nhị phân"))
        self.assertFalse(contains_exact_text("Cay nhi phan", "cây nhị phân"))
        self.assertFalse(contains_exact_text("Heapsort", "heap"))

    def test_exact_matching_tolerates_ocr_spacing_only(self):
        context = "Giải thuật n ày đạt tính kết thúc trong trường hợp xấu nhất."
        quote = "Giải thuật nà y đạt tính kết thúc trong trường hợp xấu nhất."

        self.assertTrue(contains_exact_text(context, quote))
        self.assertFalse(contains_exact_text(context, "Giải thuật đạt tính hiệu quả."))

    def test_grounding_accepts_exact_keyword_and_controlled_false_mutation(self):
        errors = validate_source_grounding(
            candidate(),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertEqual(errors, [])

    def test_grounding_rejects_keyword_not_in_reference(self):
        errors = validate_source_grounding(
            candidate(source_keywords=["Hàng đợi"]),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("KEYWORD_NOT_IN_EVIDENCE", {error.code for error in errors})

    def test_grounding_rejects_non_string_keyword(self):
        errors = validate_source_grounding(
            candidate(source_keywords=[123]),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("SOURCE_KEYWORDS_INVALID", {error.code for error in errors})

    def test_grounding_sanitizes_optional_mcq_keywords(self):
        item = candidate(
            question="Ngăn xếp (Stack) tuân theo nguyên tắc nào?",
            options={"A": "LIFO", "B": "FIFO", "C": "LILO", "D": "FILO"},
            correct_answer="A",
            question_type="trac_nghiem",
            source_keywords=["Ngăn xếp (Stack)", "không có trong nguồn", 123],
            false_mutation=None,
        )

        errors = validate_source_grounding(
            item,
            context_text=CONTEXT,
            question_type="trac_nghiem",
            candidate_index=1,
        )

        self.assertEqual(errors, [])
        self.assertEqual(item["source_keywords"], ["Ngăn xếp (Stack)"])

    def test_false_statement_requires_traceable_mutation(self):
        errors = validate_source_grounding(
            candidate(false_mutation=None),
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("FALSE_MUTATION_MISSING", {error.code for error in errors})

    def test_true_statement_must_not_include_false_mutation(self):
        item = candidate(
            question="Ngăn xếp (Stack) tuân theo nguyên tắc LIFO.",
            correct_answer="A",
        )
        errors = validate_source_grounding(
            item,
            context_text=CONTEXT,
            question_type="dung_sai",
            candidate_index=1,
        )
        self.assertIn("TRUE_STATEMENT_HAS_MUTATION", {error.code for error in errors})

    def test_clarity_rejects_question_and_multiple_propositions(self):
        errors = validate_true_false_clarity(
            candidate(question="Ngăn xếp dùng LIFO; nhưng hàng đợi dùng FIFO?"),
            candidate_index=1,
        )
        codes = {error.code for error in errors}
        self.assertIn("STATEMENT_IS_QUESTION", codes)
        self.assertIn("MULTIPLE_PROPOSITIONS", codes)

    def test_duplicate_filter_detects_exact_and_near_duplicates(self):
        first = GeneratedQuestion(**candidate())
        exact = GeneratedQuestion(**candidate())
        near = GeneratedQuestion(
            **candidate(question="Ngăn xếp (Stack) tuân theo nguyên tắc FIFO trong mọi trường hợp.")
        )
        seen = set()
        kept, stats = filter_duplicate_questions([first, exact, near], seen, limit=3)

        self.assertEqual(len(kept), 1)
        self.assertEqual(stats.exact, 1)
        self.assertEqual(stats.near, 1)
        self.assertIn(question_fingerprint(first.question), seen)

    def test_true_false_prompt_contract_declares_grounding_fields(self):
        prompt_root = BASE_DIR / "prompts"
        structure = (prompt_root / "question_structure" / "dung_sai.txt").read_text(
            encoding="utf-8"
        )
        output_format = (prompt_root / "output_format.txt").read_text(encoding="utf-8")

        self.assertIn("source_keywords", structure)
        self.assertIn("false_mutation", structure)
        self.assertIn("source_keywords", output_format)


if __name__ == "__main__":
    unittest.main()
