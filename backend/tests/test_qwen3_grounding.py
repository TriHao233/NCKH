import unittest

from modules.generation.postprocessing import validate_source_grounding


class SourceWrapperGroundingTests(unittest.TestCase):
    def test_rag_content_label_is_removed_before_grounding(self):
        evidence = "Lý do vì chương trình máy tính của một bài toán cụ thể được tạo ra từ các biểu diễn của giải thuật."
        item = {
            "question": "Chương trình máy tính được tạo ra từ đâu?",
            "source_context": f"Nội dung: ... {evidence}",
            "source_keywords": [],
        }
        errors = validate_source_grounding(
            item,
            context_text=f"Mục lục: Chương 1\nNội dung: {evidence}",
            question_type="trac_nghiem",
            candidate_index=1,
        )
        self.assertEqual(errors, [])
        self.assertEqual(item["source_context"], evidence)

    def test_unrelated_quote_remains_rejected(self):
        item = {
            "question": "Chương trình máy tính được tạo ra từ đâu?",
            "source_context": "Nội dung: Câu này không hề có trong đoạn tài liệu đã truy xuất.",
            "source_keywords": [],
        }
        errors = validate_source_grounding(
            item,
            context_text="Mục lục: Chương 1\nNội dung: Giải thuật mô tả các bước giải bài toán.",
            question_type="trac_nghiem",
            candidate_index=1,
        )
        self.assertIn("SOURCE_CONTEXT_NOT_IN_CONTENT", [error.code for error in errors])
