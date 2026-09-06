import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId
from pydantic import ValidationError

from modules.generation.mongodb import derive_question_evidence
from modules.generation.question import generate_questions_rag
from modules.generation.schemas import QuestionGenerateRequest
from modules.questions.code_sandbox import validate_code_question
from modules.questions.contracts import validate_question_contract
from modules.questions.schemas import QuestionCreateRequest
from modules.questions.service import QuestionService
from modules.questions.workflow_service import (
    QuestionWorkflowService,
    build_evaluation_fingerprint,
)


VALID_OPTIONS = {"A": "Một", "B": "Hai", "C": "Ba", "D": "Bốn"}


class StageEContractTests(unittest.IsolatedAsyncioTestCase):
    def test_matching_rejects_duplicate_left_and_trailing_garbage(self):
        base = {
            "options": {
                "1": "Một",
                "2": "Hai",
                "3": "Ba",
                "A": "A",
                "B": "B",
                "C": "C",
                "D": "Nhiễu",
            }
        }
        for answer in ("1-A,1-B,2-B,3-C", "1-A,2-B,3-C,garbage"):
            with self.assertRaisesRegex(ValueError, "QUESTION_DATA_INVALID"):
                validate_question_contract(
                    "Ghép các phần tử",
                    "ghep_cot",
                    {**base, "correct_answer": answer},
                )

    def test_shared_typed_contract_covers_all_question_types(self):
        valid = {
            "trac_nghiem": ("Chọn đáp án", {"options": VALID_OPTIONS, "correct_answer": "A"}),
            "tinh_huong": ("Xử lý tình huống", {"options": VALID_OPTIONS, "correct_answer": "B"}),
            "dung_sai": ("Stack là LIFO.", {"options": {"A": "Đúng", "B": "Sai"}, "correct_answer": "A"}),
            "dien_khuyet": ("Queue tuân theo _____", {"options": None, "correct_answer": "FIFO"}),
            "nhieu_lua_chon": ("Chọn nhiều", {"options": VALID_OPTIONS, "correct_answer": "A,C"}),
            "ghep_cot": (
                "Ghép các cặp",
                {
                    "options": {"1": "Stack", "2": "Queue", "3": "Tree", "A": "FIFO", "B": "LIFO", "C": "Node", "D": "Nhiễu"},
                    "correct_answer": "1-B,2-A,3-C",
                },
            ),
            "sap_xep": ("Sắp xếp", {"options": VALID_OPTIONS, "correct_answer": "B,A,D,C"}),
        }
        for question_type, (content, data) in valid.items():
            with self.subTest(question_type=question_type):
                normalized_type, normalized_data = validate_question_contract(
                    content, question_type, data
                )
                self.assertEqual(normalized_type, question_type)
                self.assertTrue(normalized_data["correct_answer"])

    def test_legacy_option_list_is_adapted_but_invalid_shape_is_rejected(self):
        _, data = validate_question_contract(
            "Chọn đáp án",
            "multiple_choice",
            {"options": ["Một", "Hai", "Ba", "Bốn"], "correct_answer": "A"},
        )
        self.assertEqual(list(data["options"]), ["A", "B", "C", "D"])
        with self.assertRaisesRegex(ValueError, "QUESTION_DATA_INVALID"):
            validate_question_contract(
                "Chọn đáp án",
                "trac_nghiem",
                {"options": {"A": "Một", "B": "Hai"}, "correct_answer": "A"},
            )

    def test_generation_evidence_is_exact_and_question_scoped(self):
        evidence = derive_question_evidence(
            {"source_context": "Queue tuân theo FIFO."},
            [
                {"chunk_id": "stack", "content": "Stack tuân theo LIFO."},
                {"chunk_id": "queue", "content": "Khái niệm. Queue tuân theo FIFO. Kết thúc."},
            ],
        )
        self.assertEqual(evidence[0]["chunk_id"], "queue")
        self.assertEqual(evidence[0]["char_start"], 11)
        with self.assertRaisesRegex(ValueError, "QUESTION_EVIDENCE_NOT_IN_CHUNK"):
            derive_question_evidence(
                {"source_context": "Không có"},
                [{"chunk_id": "queue", "content": "Queue"}],
            )

    def test_service_verifies_evidence_span_against_chunk_content(self):
        chunk_id = ObjectId()
        document_id = ObjectId()
        chunk_set_id = ObjectId()

        class References:
            def find_chunk(self, _chunk_id):
                return {
                    "_id": chunk_id,
                    "document_id": document_id,
                    "chunk_set_id": chunk_set_id,
                    "content": "Queue tuân theo FIFO.",
                    "content_hash": "chunk-hash",
                    "page_range": {"start": 2, "end": 2},
                }

        service = QuestionService(repository=object(), references=References())
        sources, resolved_document_id = service._sources(
            [str(chunk_id)],
            evidence_spans=[
                {
                    "chunk_id": str(chunk_id),
                    "quote": "Queue tuân theo FIFO.",
                    "char_start": 0,
                    "char_end": 21,
                }
            ],
        )
        self.assertEqual(resolved_document_id, document_id)
        self.assertEqual(sources[0]["evidence"]["status"], "VERIFIED")
        self.assertTrue(sources[0]["evidence"]["quote_hash"])
        with self.assertRaisesRegex(ValueError, "EVIDENCE_SPAN_MISMATCH"):
            service._sources(
                [str(chunk_id)],
                evidence_spans=[
                    {
                        "chunk_id": str(chunk_id),
                        "quote": "LIFO",
                        "char_start": 0,
                        "char_end": 4,
                    }
                ],
            )

    def test_source_viewer_reads_pages_from_snapshotted_ocr_job(self):
        question_id = ObjectId()
        version_id = ObjectId()
        document_id = ObjectId()
        chunk_id = ObjectId()
        source_ocr_job_id = ObjectId()
        current_ocr_job_id = ObjectId()

        class Repository:
            def find_pair(self, _question_id):
                return (
                    {
                        "_id": question_id,
                        "question_code": "Q-EVIDENCE",
                        "created_by_user_id": None,
                    },
                    {
                        "_id": version_id,
                        "version": 1,
                        "document_id": document_id,
                        "sources": [
                            {
                                "chunk_id": chunk_id,
                                "source_ocr_job_id": source_ocr_job_id,
                                "citation_order": 1,
                                "context_excerpt": "Nguồn cũ đã xác minh",
                            }
                        ],
                    },
                )

        class References:
            used_ocr_job_id = None

            def find_document(self, _document_id):
                return {
                    "_id": document_id,
                    "title": "Tài liệu",
                    "original_filename": "source.pdf",
                    "current_processing": {
                        "ocr_job_id": current_ocr_job_id,
                        "chunk_set_id": ObjectId(),
                    },
                }

            def find_chunk(self, _chunk_id):
                return {
                    "_id": chunk_id,
                    "document_id": document_id,
                    "page_range": {"start": 1, "end": 1},
                    "content": "Nguồn cũ đã xác minh",
                }

            def find_pages(self, _document_id, ocr_job_id, _page_numbers):
                self.used_ocr_job_id = ocr_job_id
                return [{"page_number": 1, "cleaned_text": "Trang nguồn cũ"}]

        references = References()
        viewer = QuestionService(Repository(), references).source_viewer(str(question_id))
        self.assertEqual(references.used_ocr_job_id, source_ocr_job_id)
        self.assertEqual(viewer["items"][0]["pages"][0]["text"], "Trang nguồn cũ")

    def test_evaluator_uses_verified_sources_beyond_legacy_three_item_limit(self):
        sources = [
            {
                "chunk_id": str(index),
                "citation_order": index,
                "context_excerpt": f"Nguồn {index}",
                "evidence": {
                    "quote": f"Nguồn {index}",
                    "token_count": 2,
                    "status": "VERIFIED",
                },
            }
            for index in range(1, 6)
        ]
        compacted = QuestionWorkflowService._compact_sources({"sources": sources})
        self.assertEqual(len(compacted), 5)
        self.assertEqual(compacted[-1]["evidence_status"], "VERIFIED")

    def test_hard_failures_and_evaluation_fingerprint_are_server_derived(self):
        failures = QuestionWorkflowService._evaluation_hard_failures(
            {
                "content": "Chọn đáp án",
                "classification": {"assessment_type": "TRAC_NGHIEM"},
                "question_data": {"options": VALID_OPTIONS, "correct_answer": "A"},
                "sources": [],
            },
            {},
        )
        self.assertIn("SOURCE_MISSING", {item["code"] for item in failures})
        policy = {"version": 1, "weights": {"faithfulness": 1}, "thresholds": {"pass_min": 0.5}}
        first = build_evaluation_fingerprint("question-hash", {"model_digest": "m1"}, policy)
        second = build_evaluation_fingerprint("question-hash", {"model_digest": "m2"}, policy)
        self.assertNotEqual(first[1], second[1])

    def test_code_sandbox_blocks_process_execution_without_running_it(self):
        result = validate_code_question("```cpp\nint main(){ system(\"echo unsafe\"); }\n```")
        self.assertTrue(result["applied"])
        self.assertFalse(result["passed"])
        self.assertIn("PROCESS_EXECUTION", result["issues"])
        unsafe_include = validate_code_question(
            '```cpp\n#include "/proc/self/environ"\nint main(){ return 0; }\n```'
        )
        self.assertIn("UNSAFE_INCLUDE", unsafe_include["issues"])

    def test_code_sandbox_records_toolchain_for_valid_syntax(self):
        calls = [
            SimpleNamespace(stdout="g++ test 1.0\n", stderr="", returncode=0),
            SimpleNamespace(stdout="", stderr="", returncode=0),
        ]
        fence = chr(96) * 3
        with (
            patch("modules.questions.code_sandbox.shutil.which", return_value="/usr/bin/g++"),
            patch("modules.questions.code_sandbox.subprocess.run", side_effect=calls),
        ):
            result = validate_code_question(
                f"{fence}cpp\nint main(){{ return 0; }}\n{fence}"
            )
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(result["toolchain"]["execution"], "SYNTAX_ONLY")

    def test_evidence_ids_must_match_question_sources(self):
        with self.assertRaises(ValidationError):
            QuestionCreateRequest(
                content="Chọn đáp án",
                question_data={"options": VALID_OPTIONS, "correct_answer": "A"},
                source_chunk_ids=["source-a"],
                evidence_spans=[{"chunk_id": "source-b", "quote": "Nguồn"}],
            )

    async def test_generation_resume_checkpoint_skips_completed_plan(self):
        request = QuestionGenerateRequest(
            document_id="document-1",
            bloom_level="2_hieu",
            question_type="trac_nghiem",
            num_questions=1,
        )
        checkpoint = {
            "completed_plan_indexes": [1],
            "data": [
                {
                    "question": "Câu đã lưu?",
                    "options": VALID_OPTIONS,
                    "correct_answer": "A",
                    "explanation": "Đã lưu",
                    "question_type": "trac_nghiem",
                    "bloom_level": "2_hieu",
                    "source_context": "Nguồn",
                    "source_keywords": [],
                }
            ],
            "summary": [
                {
                    "plan_index": 1,
                    "question_type": "trac_nghiem",
                    "bloom_level": "2_hieu",
                    "requested_count": 1,
                    "saved_count": 1,
                }
            ],
        }
        with (
            patch(
                "modules.generation.question.get_context_snapshot",
                return_value={
                    "context_text": "Nguồn",
                    "results": [],
                    "chunk_set_id": "set",
                    "vector_collection_id": "vector",
                },
            ),
            patch("modules.generation.question.get_document_learning_outcomes", return_value=[]),
            patch("modules.generation.question.get_existing_question_texts", return_value=[]),
            patch("modules.generation.question.get_llm_service") as llm_factory,
        ):
            result = await generate_questions_rag(request, resume_checkpoint=checkpoint)
        llm_factory.assert_not_called()
        self.assertEqual(len(result.data), 1)
        self.assertEqual(result.summary[0].saved_count, 1)


if __name__ == "__main__":
    unittest.main()
