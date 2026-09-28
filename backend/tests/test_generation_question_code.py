import unittest

from modules.generation.postprocessing import validate_question_code


class QuestionCodeTests(unittest.TestCase):
    def validate(self, question, **extra):
        return validate_question_code({"question": question, **extra}, candidate_index=1)

    def test_reference_without_code_is_rejected_even_with_source(self):
        errors = self.validate(
            "Trong đoạn mã sau, câu lệnh nào được thực hiện khi điều kiện 'so1 > 0' không đúng?",
            source_context="if (so1 > 0) { a = so2; } else { a = so3; }",
        )
        self.assertEqual([error.code for error in errors], ["QUESTION_CODE_MISSING"])

    def test_short_complete_code_is_accepted(self):
        self.assertEqual(self.validate(
            "Trong đoạn mã sau, nhánh nào chạy khi so1 <= 0?\n"
            "```c\nif (so1 > 0) {\n  a = so2;\n} else {\n  a = so3;\n}\n```"
        ), [])

    def test_conceptual_programming_question_does_not_require_code(self):
        self.assertEqual(self.validate("Cấu trúc if-else có vai trò gì?"), [])

    def test_empty_code_is_rejected(self):
        self.assertEqual(self.validate("Cho đoạn mã sau:\n```c\n\n```")[0].code, "QUESTION_CODE_MISSING")

    def test_code_limit_applies_to_all_blocks_together(self):
        code = "\n".join("x++;" for _ in range(7))
        question = f"Đoạn mã sau cho kết quả gì?\n```c\n{code}\n```\n```c\n{code}\n```"
        self.assertEqual(self.validate(question)[0].code, "QUESTION_CODE_TOO_LONG")

    def test_character_limit_and_english_reference(self):
        self.assertEqual(self.validate("Đoạn code sau trả về gì?")[0].code, "QUESTION_CODE_MISSING")
        self.assertEqual(self.validate("```c\n" + "x" * 801 + "\n```")[0].code, "QUESTION_CODE_TOO_LONG")
