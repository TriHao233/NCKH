import unittest

from modules.questions.workflow_schemas import EvaluationScores
from modules.questions.workflow_service import EvidenceGateError, QuestionWorkflowService


class EvaluationGroundingTests(unittest.TestCase):
    def setUp(self):
        self.sources = [
            {
                "chunk_id": "64b64b64b64b64b64b64b64b",
                "content_hash": "hash-1",
                "page_start": 3,
                "page_end": 3,
                "excerpt": "Hàng đợi hoạt động theo nguyên tắc vào trước ra trước, còn gọi là FIFO.",
            }
        ]

    def test_verifies_quote_against_retrieved_chunk(self):
        evidence = QuestionWorkflowService._validate_model_evidence(
            {
                "citations": [
                    {
                        "claim": "Đáp án FIFO được nguồn hỗ trợ",
                        "claim_type": "ANSWER",
                        "chunk_id": self.sources[0]["chunk_id"],
                        "exact_quote": "Hàng đợi hoạt động theo nguyên tắc vào trước ra trước",
                        "entailment": "SUPPORTED",
                    }
                ]
            },
            self.sources,
        )

        self.assertEqual(evidence["citation_validation"]["status"], "VERIFIED")
        self.assertTrue(evidence["citations"][0]["verified"])
        self.assertEqual(evidence["citations"][0]["page_start"], 3)

    def test_rejects_hallucinated_quote(self):
        with self.assertRaises(EvidenceGateError) as context:
            QuestionWorkflowService._validate_model_evidence(
                {
                    "citations": [
                        {
                            "chunk_id": self.sources[0]["chunk_id"],
                            "claim_type": "ANSWER",
                            "exact_quote": "Stack luôn hoạt động theo cơ chế FIFO",
                            "entailment": "SUPPORTED",
                        }
                    ]
                },
                self.sources,
            )

        self.assertEqual(context.exception.code, "EVIDENCE_VALIDATION_FAILED")

    def test_accepts_high_coverage_ocr_paraphrase(self):
        sources = [
            {
                **self.sources[0],
                "excerpt": (
                    "Mảng là một tập hợp các phần tử cố định có cùng một kiểu. "
                    "Kiểu dữ liệu mảng giúp lưu trữ nhiều biến cùng kiểu."
                ),
            }
        ]
        evidence = QuestionWorkflowService._validate_model_evidence(
            {
                "citations": [
                    {
                        "claim": "Đáp án mô tả đúng công dụng của mảng",
                        "claim_type": "ANSWER",
                        "chunk_id": sources[0]["chunk_id"],
                        "exact_quote": "Mảng là một kiểu dữ liệu lưu trữ nhiều biến cùng kiểu như một tập hợp.",
                        "entailment": "SUPPORTED",
                    }
                ]
            },
            sources,
        )

        self.assertEqual(evidence["citations"][0]["match_mode"], "FUZZY_OCR")
        self.assertGreaterEqual(evidence["citations"][0]["match_score"], 0.75)

    def test_missing_answer_support_becomes_a_quality_failure(self):
        evidence = QuestionWorkflowService._validate_model_evidence(
            {
                "citations": [
                    {
                        "claim": "Câu hỏi thuộc chủ đề hàng đợi",
                        "claim_type": "QUESTION",
                        "chunk_id": self.sources[0]["chunk_id"],
                        "exact_quote": "Hàng đợi hoạt động theo nguyên tắc vào trước ra trước",
                        "entailment": "SUPPORTED",
                    }
                ],
                "unsupported_claims": [],
            },
            self.sources,
        )

        self.assertFalse(evidence["citation_validation"]["answer_supported"])
        self.assertIn("Đáp án đúng", evidence["unsupported_claims"][0])

    def test_unsupported_claim_prevents_approval_and_caps_faithfulness(self):
        scores = EvaluationScores(
            faithfulness=0.95,
            contextual_relevancy=0.9,
            answer_relevancy=0.9,
            bloom_alignment=0.9,
            clo_alignment=0.9,
        )
        scores, feedback = QuestionWorkflowService._enforce_grounding_policy(
            scores,
            {"action": "APPROVE", "severity": "LOW"},
            {"unsupported_claims": ["Giải thích chưa có nguồn"]},
        )

        self.assertEqual(scores.faithfulness, 0.4)
        self.assertEqual(feedback["action"], "NEEDS_REVISION")
        self.assertEqual(feedback["severity"], "HIGH")


if __name__ == "__main__":
    unittest.main()
