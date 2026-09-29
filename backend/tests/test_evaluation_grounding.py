import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from modules.questions.workflow_schemas import EvaluationScores
from modules.questions.workflow_service import EvidenceGateError, QuestionWorkflowService
from modules.rag.search import get_evaluation_evidence


def test_evaluation_retrieval_uses_active_model_scoped_collection():
    class EmptyCollection:
        def query(self, **_kwargs):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    with (
        patch("modules.rag.search._active_vector_snapshot", return_value=("chunk-set", "vector-id", "chunks_model")),
        patch("modules.rag.search.get_collection", return_value=EmptyCollection()) as get_collection,
        patch("modules.rag.search.get_rag_db"),
    ):
        result = get_evaluation_evidence("64b64b64b64b64b64b64b64b", "Hàng đợi FIFO")

    get_collection.assert_called_once_with("chunks_model")
    assert result["collection_name"] == "chunks_model"
    assert result["results"] == []


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


POLICY = {
    "version": 1,
    "weights": {
        "faithfulness": 0.35,
        "contextual_relevancy": 0.20,
        "answer_relevancy": 0.15,
        "bloom_alignment": 0.15,
        "clo_alignment": 0.15,
    },
    "thresholds": {"yellow_min": 0.5, "green_min": 0.75, "pass_min": 0.65},
}
QUEUE_EXCERPT = "Hàng đợi hoạt động theo nguyên tắc vào trước ra trước, còn gọi là FIFO."


def _source():
    return {
        "chunk_id": "64b64b64b64b64b64b64b64b",
        "content_hash": "hash-1",
        "label": "S1",
        "excerpt": QUEUE_EXCERPT,
    }


def _version(assessment_type="DIEN_KHUYET", **question_data):
    return {
        "content": "Hàng đợi hoạt động theo nguyên tắc _____.",
        "classification": {"assessment_type": assessment_type, "bloom": {"level": 1}},
        "clos": [{"code": "CLO1", "description": "Nêu nguyên tắc hoạt động của hàng đợi."}],
        "question_data": {"correct_answer": "LIFO", **question_data},
        "sources": [
            {
                "chunk_id": _source()["chunk_id"],
                "citation_order": 1,
                "context_excerpt": QUEUE_EXCERPT,
            }
        ],
    }


def _raw(action, severity, readiness, *, score=0.5, answer_entailment="CONTRADICTED", **evidence):
    return json.dumps(
        {
            "scores": {
                "faithfulness": score,
                "contextual_relevancy": score,
                "answer_relevancy": score,
                "bloom_alignment": score,
                "clo_alignment": score,
            },
            "feedback": {"summary": "Nhận xét", "missing": [], "action": action, "severity": severity},
            "evidence": {
                "reasoning": "Đối chiếu với nguồn S1.",
                "moodle_readiness": readiness,
                "citations": [
                    {
                        "claim": "Câu hỏi nói về hàng đợi",
                        "claim_type": "QUESTION",
                        "chunk_id": _source()["chunk_id"],
                        "exact_quote": "Hàng đợi hoạt động theo nguyên tắc vào trước ra trước",
                        "entailment": "SUPPORTED",
                    },
                    {
                        "claim": "Đáp án LIFO",
                        "claim_type": "ANSWER",
                        "chunk_id": _source()["chunk_id"],
                        "exact_quote": "vào trước ra trước, còn gọi là FIFO",
                        "entailment": answer_entailment,
                    },
                ],
                **evidence,
            },
        },
        ensure_ascii=False,
    )


class EvaluationFinalizeTests(unittest.TestCase):
    def setUp(self):
        self.service = QuestionWorkflowService(None)

    def finalize(self, raw, version=None, llm=None):
        return self.service._finalize_llm_evaluation(
            raw, [_source()], version or _version(), POLICY, llm=llm
        )

    def test_contradicted_answer_is_saved_as_reject_instead_of_failing(self):
        # The model flags the answer as contradicted but still calls the item
        # Moodle READY. Grounding forces REJECT; this used to raise
        # "REJECT nhưng Moodle READY" and the evaluation job dead-lettered.
        scores, feedback, evidence = self.finalize(_raw("NEEDS_REVISION", "MEDIUM", "READY"))

        self.assertEqual(feedback["action"], "REJECT")
        self.assertEqual(feedback["severity"], "HIGH")
        self.assertEqual(evidence["moodle_readiness"], "NEEDS_FIX")
        self.assertLessEqual(scores.faithfulness, 0.20)
        self.assertTrue(evidence["decision_normalization"]["applied"])
        self.assertTrue(evidence["consistency"]["validated"])
        self.assertEqual(evidence["consistency"]["model_contradictions"], [])

    def test_answer_guardrail_does_not_soften_reject(self):
        version = _version(
            "TRAC_NGHIEM",
            options={"A": "FIFO", "B": "LIFO", "C": "Ngẫu nhiên", "D": "Theo độ ưu tiên"},
            correct_answer="B",
        )
        version["content"] = "Hàng đợi hoạt động theo nguyên tắc nào?"
        raw = _raw(
            "REJECT",
            "HIGH",
            "NEEDS_FIX",
            score=0.3,
            question_polarity="POSITIVE",
            option_checks=[
                {"key": "A", "verdict": "SUPPORTED", "source_label": "S1", "supporting_excerpt": "còn gọi là FIFO"},
                {"key": "B", "verdict": "CONTRADICTED", "source_label": "S1", "supporting_excerpt": ""},
                {"key": "C", "verdict": "NOT_IN_SOURCE", "source_label": "", "supporting_excerpt": ""},
                {"key": "D", "verdict": "NOT_IN_SOURCE", "source_label": "", "supporting_excerpt": ""},
            ],
        )

        _, feedback, evidence = self.finalize(raw, version)

        self.assertTrue(evidence["answer_guardrail"]["applied"])
        self.assertEqual(feedback["action"], "REJECT")

    def test_self_contradictory_model_verdict_is_resolved_strictly_and_recorded(self):
        raw = _raw("APPROVE", "LOW", "READY", score=0.5, answer_entailment="SUPPORTED")
        version = _version(correct_answer="FIFO")

        _, feedback, evidence = self.finalize(raw, version)

        self.assertNotEqual(feedback["action"], "APPROVE")
        self.assertIn(
            "APPROVE nhưng tổng điểm dưới ngưỡng đạt",
            evidence["consistency"]["model_contradictions"],
        )

    def test_consistent_approval_is_left_untouched(self):
        raw = _raw("APPROVE", "LOW", "READY", score=0.9, answer_entailment="SUPPORTED")
        version = _version(correct_answer="FIFO")

        _, feedback, evidence = self.finalize(raw, version)

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertNotIn("decision_normalization", evidence)
        self.assertEqual(evidence["consistency"]["model_contradictions"], [])
        self.assertFalse(evidence["model_output"]["hit_output_limit"])

    def test_truncated_output_reports_the_output_limit(self):
        llm = SimpleNamespace(last_response_metadata={"done_reason": "length", "eval_count": 900})

        with self.assertRaisesRegex(ValueError, "num_predict"):
            self.finalize('{"scores": {"faithfulness": 0.8', llm=llm)

    def test_output_metadata_reads_the_provider_that_answered(self):
        primary = SimpleNamespace(last_response_metadata={"done_reason": "stop"})
        fallback = SimpleNamespace(last_response_metadata={"done_reason": "length", "eval_count": 900})
        llm = SimpleNamespace(last_used="fallback", primary=primary, fallback=fallback)

        output = QuestionWorkflowService._llm_output_metadata(llm, "{}")

        self.assertTrue(output["hit_output_limit"])
        self.assertEqual(output["eval_count"], 900)

    def _mcq(self, correct="A"):
        version = _version(
            "NHIEU_LUA_CHON" if "," in correct else "TRAC_NGHIEM",
            options={"A": "Vào trước ra trước", "B": "Vào sau ra trước", "C": "Ngẫu nhiên", "D": "Theo độ ưu tiên"},
            correct_answer=correct,
        )
        version["content"] = "Hàng đợi hoạt động theo nguyên tắc nào?"
        return version

    @staticmethod
    def _checks(supported):
        return [
            {
                "key": key,
                "verdict": "SUPPORTED" if key in supported else "CONTRADICTED",
                "source_label": "S1",
                "supporting_excerpt": "nguyên tắc vào trước ra trước" if key in supported else "",
            }
            for key in "ABCD"
        ]

    def test_contradicted_distractor_citation_does_not_reject_verified_answer(self):
        raw = _raw(
            "APPROVE", "LOW", "READY", score=0.9, answer_entailment="SUPPORTED",
            question_polarity="POSITIVE", option_checks=self._checks({"A"}),
        )
        payload = json.loads(raw)
        payload["evidence"]["citations"].append({
            "claim": "Đáp án B sai",
            "claim_type": "ANSWER",
            "chunk_id": _source()["chunk_id"],
            "exact_quote": "vào trước ra trước, còn gọi là FIFO",
            "entailment": "CONTRADICTED",
        })

        scores, feedback, evidence = self.finalize(json.dumps(payload, ensure_ascii=False), self._mcq("A"))

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertGreater(scores.faithfulness, 0.2)
        scoped = [c for c in evidence["citations"] if c.get("scope") == "DISTRACTOR"]
        self.assertEqual(len(scoped), 1)

    def test_contradicted_citation_still_rejects_when_answer_is_not_verified(self):
        # Declared B, but option checks only confirm A: the contradiction is real.
        raw = _raw(
            "NEEDS_REVISION", "MEDIUM", "READY", question_polarity="POSITIVE",
            option_checks=self._checks({"A"}),
        )

        _, feedback, evidence = self.finalize(raw, self._mcq("B"))

        self.assertEqual(feedback["action"], "REJECT")
        self.assertFalse(any(c.get("scope") for c in evidence["citations"]))

    def test_verified_option_check_counts_as_answer_citation(self):
        payload = json.loads(_raw(
            "APPROVE", "LOW", "READY", score=0.9, answer_entailment="SUPPORTED",
            question_polarity="POSITIVE", option_checks=self._checks({"A"}),
        ))
        # The model labels its only answer citation as EXPLANATION.
        payload["evidence"]["citations"][1]["claim_type"] = "EXPLANATION"

        _, feedback, evidence = self.finalize(json.dumps(payload, ensure_ascii=False), self._mcq("A"))

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertEqual(evidence["unsupported_claims"], [])
        self.assertEqual(evidence["citation_validation"]["answer_support_source"], "OPTION_CHECKS")

    def test_placeholder_unsupported_claim_is_ignored_but_real_claim_is_kept(self):
        evidence = QuestionWorkflowService._validate_model_evidence(
            {
                "citations": json.loads(_raw("APPROVE", "LOW", "READY", answer_entailment="SUPPORTED"))[
                    "evidence"
                ]["citations"],
                "unsupported_claims": [
                    "Không có nhận định trọng yếu nào không được hỗ trợ từ nguồn.",
                    "Không có nguồn hỗ trợ giải thích về độ phức tạp",
                ],
            },
            [_source()],
        )

        self.assertEqual(
            evidence["unsupported_claims"],
            ["Không có nguồn hỗ trợ giải thích về độ phức tạp"],
        )

    def test_only_contradicted_citations_still_record_a_reject(self):
        payload = json.loads(_raw("REJECT", "HIGH", "NEEDS_FIX", score=0.3))
        payload["evidence"]["citations"] = payload["evidence"]["citations"][1:]

        _, feedback, evidence = self.finalize(json.dumps(payload, ensure_ascii=False))

        self.assertEqual(feedback["action"], "REJECT")
        self.assertEqual(evidence["citation_validation"]["verified"], 1)
