import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from modules.questions.workflow_schemas import EvaluationScores
from modules.questions.workflow_service import (
    EvidenceGateError,
    QuestionWorkflowService,
    effective_weights,
)
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

    def _mistaken_support_for_declared(self, claim):
        # Declared B is wrong, but the model wrongly marks B SUPPORTED with a
        # quote that does come from the source.
        checks = self._checks({"B"})
        checks[1]["supporting_excerpt"] = "nguyên tắc vào trước ra trước"
        payload = json.loads(_raw(
            "NEEDS_REVISION", "MEDIUM", "READY", question_polarity="POSITIVE",
            option_checks=checks,
        ))
        payload["evidence"]["citations"][1]["claim"] = claim
        return json.dumps(payload, ensure_ascii=False)

    def test_contradiction_naming_declared_answer_still_rejects(self):
        _, feedback, evidence = self.finalize(
            self._mistaken_support_for_declared("Đáp án B (Vào sau ra trước) là đúng"),
            self._mcq("B"),
        )

        self.assertEqual(feedback["action"], "REJECT")
        self.assertFalse(any(c.get("scope") for c in evidence["citations"]))

    def test_contradiction_naming_no_option_still_rejects(self):
        _, feedback, _ = self.finalize(
            self._mistaken_support_for_declared("Đáp án khai báo không khớp nguồn"),
            self._mcq("B"),
        )

        self.assertEqual(feedback["action"], "REJECT")

    def test_claim_scope_detects_option_letters_and_text(self):
        options = {"A": "FIFO", "B": "LIFO", "C": "O(n)", "D": "O(log n)"}
        names_only = QuestionWorkflowService._claim_names_only_distractors

        self.assertTrue(names_only("Đáp án C sai", options, {"A"}))
        self.assertTrue(names_only("Phương án LIFO không đúng với hàng đợi", options, {"A"}))
        self.assertFalse(names_only("Đáp án A sai, C mới đúng", options, {"A"}))
        self.assertFalse(names_only("FIFO là đáp án sai", options, {"A"}))
        self.assertFalse(names_only("Đáp án không đúng", options, {"A"}))


def _raw_scored(action, severity, *, clo, others=0.9, missing=(), **score_overrides):
    """Model output for a correct FIFO answer with explicit per-criterion scores."""
    payload = json.loads(_raw(action, severity, "READY", score=others, answer_entailment="SUPPORTED"))
    payload["scores"].update({"clo_alignment": clo, **score_overrides})
    payload["feedback"]["missing"] = list(missing)
    return json.dumps(payload, ensure_ascii=False)


class EvaluationWithoutCloTests(unittest.TestCase):
    """Không phải câu hỏi nào cũng gắn CLO; thiếu CLO không được làm câu rớt."""

    def setUp(self):
        self.service = QuestionWorkflowService(None)

    def finalize(self, raw, *, clos=(), **version_changes):
        version = _version(correct_answer="FIFO")
        version["clos"] = list(clos)
        version.update(version_changes)
        return self.service._finalize_llm_evaluation(raw, [_source()], version, POLICY)

    def test_effective_weights_drop_the_clo_criterion_and_keep_the_total(self):
        weights = effective_weights(POLICY, {"metadata_guardrail": {"not_applicable": ["clo_alignment"]}})

        self.assertEqual(weights["clo_alignment"], 0.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["faithfulness"], 0.35 / 0.85)
        self.assertEqual(effective_weights(POLICY, {}), POLICY["weights"])
        self.assertEqual(effective_weights(POLICY, None), POLICY["weights"])

    def test_question_without_clo_is_approved_and_clo_is_left_out_of_the_score(self):
        scores, feedback, evidence = self.finalize(_raw_scored("APPROVE", "LOW", clo=0.0))

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertFalse(evidence["metadata_guardrail"]["applied"])
        self.assertEqual(evidence["metadata_guardrail"]["not_applicable"], ["clo_alignment"])
        self.assertEqual(evidence["metadata_guardrail"]["missing_fields"], [])
        self.assertAlmostEqual(evidence["consistency"]["calculated_overall"], 0.9)
        self.assertNotIn("clo_alignment", evidence["consistency"]["weak_criteria"])
        self.assertNotIn("decision_normalization", evidence)
        self.assertEqual(scores.clo_alignment, 0.0)

    def test_revision_asked_only_because_clo_is_missing_is_cleared(self):
        raw = _raw_scored(
            "NEEDS_REVISION", "MEDIUM", clo=0.3, others=0.8,
            missing=["Thiếu CLO", "Câu hỏi chưa gắn chuẩn đầu ra"],
        )

        _, feedback, evidence = self.finalize(raw)

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertEqual(feedback["severity"], "LOW")
        self.assertEqual(feedback["missing"], [])
        self.assertEqual(
            evidence["metadata_guardrail"]["cleared_missing"],
            ["Thiếu CLO", "Câu hỏi chưa gắn chuẩn đầu ra"],
        )

    def test_revision_with_another_stated_problem_is_kept(self):
        raw = _raw_scored(
            "NEEDS_REVISION", "MEDIUM", clo=0.3, others=0.8,
            missing=["Thiếu CLO", "Giải thích chưa nêu lý do chọn đáp án"],
        )

        _, feedback, evidence = self.finalize(raw)

        self.assertEqual(feedback["action"], "NEEDS_REVISION")
        self.assertEqual(feedback["missing"], ["Giải thích chưa nêu lý do chọn đáp án"])
        self.assertEqual(evidence["metadata_guardrail"]["cleared_missing"], ["Thiếu CLO"])

    def test_missing_clo_note_is_dropped_from_an_approval(self):
        raw = _raw_scored("APPROVE", "LOW", clo=0.0, missing=["Thiếu gắn CLO"])

        _, feedback, evidence = self.finalize(raw)

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertEqual(feedback["missing"], [])
        self.assertEqual(evidence["metadata_guardrail"]["cleared_missing"], ["Thiếu gắn CLO"])

    def test_clo_note_is_kept_when_the_question_has_a_clo(self):
        clos = [{"code": "CLO1", "description": "Nêu nguyên tắc hoạt động của hàng đợi."}]
        raw = _raw_scored("NEEDS_REVISION", "MEDIUM", clo=0.4, others=0.8, missing=["Câu hỏi chưa đo được CLO đã gắn"])

        _, feedback, evidence = self.finalize(raw, clos=clos)

        self.assertEqual(feedback["action"], "NEEDS_REVISION")
        self.assertEqual(feedback["missing"], ["Câu hỏi chưa đo được CLO đã gắn"])
        self.assertNotIn("cleared_missing", evidence["metadata_guardrail"])

    def test_revision_is_kept_when_another_criterion_is_below_the_minimum(self):
        raw = _raw_scored(
            "NEEDS_REVISION", "MEDIUM", clo=0.3, others=0.8,
            missing=["Thiếu CLO"], bloom_alignment=0.5,
        )

        _, feedback, _ = self.finalize(raw)

        self.assertEqual(feedback["action"], "NEEDS_REVISION")

    def test_revision_without_a_stated_reason_or_with_high_severity_is_kept(self):
        _, no_reason, _ = self.finalize(_raw_scored("NEEDS_REVISION", "MEDIUM", clo=0.3, others=0.8))
        _, severe, _ = self.finalize(
            _raw_scored("NEEDS_REVISION", "HIGH", clo=0.3, others=0.8, missing=["Thiếu CLO"])
        )

        self.assertEqual(no_reason["action"], "NEEDS_REVISION")
        self.assertEqual(severe["action"], "NEEDS_REVISION")

    def test_attached_clo_that_the_question_does_not_measure_still_counts(self):
        clos = [{"code": "CLO1", "description": "Nêu nguyên tắc hoạt động của hàng đợi."}]

        _, feedback, evidence = self.finalize(_raw_scored("APPROVE", "LOW", clo=0.0), clos=clos)

        self.assertEqual(evidence["metadata_guardrail"]["not_applicable"], [])
        self.assertAlmostEqual(evidence["consistency"]["calculated_overall"], 0.765)
        self.assertIn("clo_alignment", evidence["consistency"]["weak_criteria"])
        self.assertEqual(feedback["action"], "APPROVE")

    def test_missing_bloom_still_blocks_a_question_without_clo(self):
        _, feedback, evidence = self.finalize(
            _raw_scored("APPROVE", "LOW", clo=0.0),
            classification={"assessment_type": "DIEN_KHUYET", "bloom": {}},
        )

        self.assertEqual(feedback["action"], "NEEDS_REVISION")
        self.assertEqual(evidence["metadata_guardrail"]["missing_fields"], ["bloom"])
        self.assertTrue(evidence["metadata_guardrail"]["applied"])


class EvaluationOutputRepairTests(unittest.TestCase):
    def test_punctuation_typo_in_an_option_check_field_name_is_read(self):
        # qwen3:8b writes "ver,dict" for the fourth option; that typo used to
        # block a correct question with "option_checks không hợp lệ: D".
        payload = json.loads(_raw("APPROVE", "LOW", "READY", score=0.9, answer_entailment="SUPPORTED"))
        payload["evidence"]["option_checks"] = [
            {"key": "A", "verdict": "SUPPORTED", "source_label": "S1", "supporting_excerpt": "còn gọi là FIFO"},
            {"key": "B", "ver,dict": "NOT_IN_SOURCE", "source_label": "S1", "supporting_excerpt": ""},
        ]

        _, _, evidence = QuestionWorkflowService._parse_llm_evaluation(json.dumps(payload, ensure_ascii=False))

        self.assertEqual(
            [(item["key"], item["verdict"]) for item in evidence["option_checks"]],
            [("A", "SUPPORTED"), ("B", "NOT_IN_SOURCE")],
        )

    def test_evaluation_payload_states_whether_a_clo_is_attached(self):
        service = QuestionWorkflowService(None)
        question = {"_id": "q-1", "question_code": "Q-1"}

        with_clo, _, _ = service._build_evaluation_prompt(
            question, _version(correct_answer="FIFO"), POLICY, source_chunks=[_source()]
        )
        version = _version(correct_answer="FIFO")
        version["clos"] = []
        without_clo, _, _ = service._build_evaluation_prompt(question, version, POLICY, source_chunks=[_source()])

        self.assertIn('"clo_status": "ATTACHED"', with_clo)
        self.assertIn('"clo_status": "NOT_ATTACHED"', without_clo)


class EvaluatorIncompleteOutputTests(unittest.TestCase):
    """Thiếu sót của kết quả chấm không được tính là lỗi của câu hỏi."""

    OPTIONS = {"A": "FIFO", "B": "LIFO", "C": "Ngẫu nhiên", "D": "Theo độ ưu tiên"}

    def setUp(self):
        self.service = QuestionWorkflowService(None)

    def version(self):
        version = _version("TRAC_NGHIEM", options=dict(self.OPTIONS), correct_answer="A")
        version["content"] = "Hàng đợi hoạt động theo nguyên tắc nào?"
        return version

    def raw(self, option_checks):
        return _raw(
            "APPROVE", "LOW", "READY", score=0.9, answer_entailment="SUPPORTED",
            question_polarity="POSITIVE", option_checks=option_checks,
        )

    def finalize(self, option_checks):
        return self.service._finalize_llm_evaluation(
            self.raw(option_checks), [_source()], self.version(), POLICY
        )

    @staticmethod
    def checks(**overrides):
        checks = {
            "A": {"key": "A", "verdict": "SUPPORTED", "source_label": "S1", "supporting_excerpt": "còn gọi là FIFO"},
            "B": {"key": "B", "verdict": "NOT_IN_SOURCE", "source_label": "", "supporting_excerpt": ""},
            "C": {"key": "C", "verdict": "NOT_IN_SOURCE", "source_label": "", "supporting_excerpt": ""},
            "D": {"key": "D", "verdict": "NOT_IN_SOURCE", "source_label": "", "supporting_excerpt": ""},
        }
        for key, value in overrides.items():
            if value is None:
                checks.pop(key)
            else:
                checks[key] = {**checks[key], **value}
        return list(checks.values())

    def test_complete_option_checks_are_approved(self):
        _, feedback, evidence = self.finalize(self.checks())

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertEqual(evidence["answer_guardrail"]["evaluator_incomplete"], [])
        self.assertEqual(evidence["answer_guardrail"]["verified_by_option_text"], [])

    def test_unchecked_option_is_a_retryable_error_not_a_verdict(self):
        with self.assertRaisesRegex(ValueError, "chưa kiểm tra đủ các phương án.*AI chưa kiểm tra phương án: D"):
            self.finalize(self.checks(D=None))

    def test_invalid_verdict_is_a_retryable_error_not_a_verdict(self):
        with self.assertRaisesRegex(ValueError, "option_checks không hợp lệ: D"):
            self.finalize(self.checks(D={"verdict": "MAYBE"}))

    def test_guardrail_alone_still_reports_the_gap_for_the_heuristic_path(self):
        scores = EvaluationScores(
            faithfulness=0.9, contextual_relevancy=0.9, answer_relevancy=0.9,
            bloom_alignment=0.9, clo_alignment=0.9,
        )
        feedback = {"summary": "Đạt", "missing": [], "action": "APPROVE", "severity": "LOW"}
        evidence = {"moodle_readiness": "READY", "question_polarity": "POSITIVE", "option_checks": self.checks(D=None)}

        _, guarded, guarded_evidence = QuestionWorkflowService._apply_answer_guardrail(
            scores, feedback, evidence, self.version()
        )

        self.assertEqual(guarded["action"], "NEEDS_REVISION")
        self.assertEqual(
            guarded_evidence["answer_guardrail"]["evaluator_incomplete"],
            ["AI chưa kiểm tra phương án: D"],
        )

    def test_missing_excerpt_is_checked_against_the_source_text(self):
        _, feedback, evidence = self.finalize(self.checks(A={"supporting_excerpt": ""}))

        self.assertEqual(feedback["action"], "APPROVE")
        self.assertEqual(evidence["answer_guardrail"]["verified_by_option_text"], ["A"])
        self.assertFalse(evidence["answer_guardrail"]["applied"])

    def test_missing_excerpt_still_blocks_when_the_option_is_not_in_the_source(self):
        version = self.version()
        version["question_data"]["options"]["A"] = "Vào sau ra trước hoàn toàn"
        raw = self.raw(self.checks(A={"supporting_excerpt": ""}))

        _, feedback, evidence = self.service._finalize_llm_evaluation(raw, [_source()], version, POLICY)

        self.assertEqual(feedback["action"], "NEEDS_REVISION")
        self.assertIn("Phương án A thiếu trích dẫn nguồn", evidence["answer_guardrail"]["issues"])
        self.assertEqual(evidence["answer_guardrail"]["verified_by_option_text"], [])

    def test_fabricated_excerpt_or_unknown_source_label_still_blocks(self):
        _, wrong_quote, wrong_quote_evidence = self.finalize(
            self.checks(A={"supporting_excerpt": "ngăn xếp dùng con trỏ đỉnh để quản lý phần tử"})
        )
        _, wrong_label, wrong_label_evidence = self.finalize(self.checks(A={"source_label": "S9"}))

        self.assertEqual(wrong_quote["action"], "NEEDS_REVISION")
        self.assertIn("Trích dẫn của phương án A không khớp nguồn S1", wrong_quote_evidence["answer_guardrail"]["issues"])
        self.assertEqual(wrong_label["action"], "NEEDS_REVISION")
        self.assertIn("Phương án A không trỏ tới nguồn S hợp lệ", wrong_label_evidence["answer_guardrail"]["issues"])


class EvaluationOutputBudgetTests(unittest.TestCase):
    def test_thinking_evaluator_gets_thinking_budget_and_context(self):
        from core.config import settings
        from modules.questions.workflow_service import _limit_evaluation_output, _prepare_evaluation_attempt

        snapshot = _limit_evaluation_output({
            "model_code": "deepseek",
            "model_name": "deepseek-r1",
            "runtime": "OLLAMA",
            "parameters": {"num_predict": 900, "num_ctx": 8192},
        })

        self.assertEqual(snapshot["parameters"]["num_predict"], settings.evaluation_thinking_num_predict)
        self.assertEqual(snapshot["parameters"]["num_ctx"], settings.evaluation_thinking_num_ctx)
        _, _, retry = _prepare_evaluation_attempt("p", {}, snapshot, 2)
        self.assertGreaterEqual(retry["parameters"]["num_predict"], settings.evaluation_thinking_num_predict)

    def test_thinking_disabled_model_keeps_its_budget(self):
        from modules.questions.workflow_service import _limit_evaluation_output

        snapshot = _limit_evaluation_output({
            "model_code": "deepseek",
            "model_name": "deepseek-r1",
            "runtime": "OLLAMA",
            "parameters": {"num_predict": 900, "think": False},
        })

        self.assertEqual(snapshot["parameters"]["num_predict"], 900)
