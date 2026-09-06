import unittest
from unittest.mock import patch

from modules.generation.llm.model_registry import (
    CODE_GENERATION_ROLE,
    GENERAL_GENERATION_ROLE,
    bind_model_role,
)
from modules.generation.llm.structured_output import (
    extract_question_candidates,
    parse_structured_json,
)
from modules.generation.prompt_builder import PromptBuilder
from modules.generation.schemas import QuestionGenerateRequest
from modules.rag.chunking import _chunk_buffer
from modules.rag.search import _fuse_candidates, get_context_snapshot
from scripts.benchmark_retrieval import recall_at_k


class StageDContractTests(unittest.TestCase):
    def test_chunk_keeps_protected_code_and_source_span_when_over_budget(self):
        code = "\n".join(f"int value_{index} = {index};" for index in range(90))
        source = f"<!-- PAGE:7 -->\n# Cây nhị phân\n\n```cpp\n{code}\n```"
        with patch("modules.rag.chunking.get_active_keywords", return_value=[]):
            chunks = list(
                _chunk_buffer(
                    source,
                    "document-1",
                    chunk_size=20_000,
                    chunk_overlap=0,
                    max_code_block_lines=200,
                    token_budget=64,
                )
            )

        self.assertEqual(len(chunks), 1)
        self.assertIn("int value_89 = 89;", chunks[0]["content"])
        metadata = chunks[0]["metadata"]
        self.assertEqual(metadata["token_budget_status"], "OVERSIZE_PROTECTED")
        self.assertEqual(metadata["source_span"]["page_start"], 7)
        self.assertTrue(metadata["parent_section_id"])

    def test_hard_heading_filter_does_not_fallback_outside_scope(self):
        class CollectionStub:
            def count(self):
                return 1

            def query(self, **_kwargs):
                return {
                    "documents": [["Stack dùng LIFO."]],
                    "metadatas": [[
                        {
                            "chunk_id": "stack",
                            "chunk_set_id": "set-1",
                            "heading": "Ngăn xếp",
                        }
                    ]],
                    "distances": [[0.1]],
                }

        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1")),
            patch("modules.rag.search.get_collection", return_value=CollectionStub()),
        ):
            with self.assertRaisesRegex(ValueError, "INSUFFICIENT_EVIDENCE"):
                get_context_snapshot(
                    document_id="document-1",
                    collection_name="chunks",
                    target_heading="Cây nhị phân",
                    query_text="tìm kiếm",
                    retrieval_mode="dense",
                )

    def test_lexical_branch_is_independent_from_vector_collection(self):
        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1")),
            patch(
                "modules.rag.search._mongo_lexical_candidates",
                return_value=[
                    (
                        "Cây nhị phân tìm kiếm hỗ trợ tra cứu.",
                        {"chunk_id": "tree", "chunk_set_id": "set-1", "token_count": 8},
                    )
                ],
            ),
            patch("modules.rag.search.get_collection") as vector_collection,
        ):
            snapshot = get_context_snapshot(
                document_id="document-1",
                collection_name="chunks",
                query_text="cây nhị phân tìm kiếm",
                retrieval_mode="lexical",
            )

        vector_collection.assert_not_called()
        self.assertEqual(snapshot["results"][0]["chunk_id"], "tree")
        self.assertEqual(snapshot["trace"]["mode"], "lexical")

    def test_fusion_trace_keeps_both_branch_ranks(self):
        dense = [("Dense", {"chunk_id": "shared", "_dense_score": 0.8})]
        lexical = [("Lexical", {"chunk_id": "shared", "_lexical_score": 1.0})]
        fused = _fuse_candidates(dense, lexical, "hybrid")

        self.assertEqual(len(fused), 1)
        self.assertEqual(fused[0][1]["_dense_rank"], 1)
        self.assertEqual(fused[0][1]["_lexical_rank"], 1)

    def test_prompt_manifest_has_hashes_and_db_source_is_strict(self):
        release = PromptBuilder().build_with_manifest(
            context="Nội dung: Stack dùng nguyên tắc LIFO.",
            bloom_level="2_hieu",
            question_type="trac_nghiem",
            num_questions=1,
            topic="LIFO",
        )
        self.assertEqual(len(release["templates"]), 7)
        self.assertTrue(all(item["content_hash"] for item in release["templates"]))
        self.assertTrue(release["release_hash"])
        self.assertIn("CHỦ ĐỀ TRỌNG TÂM", release["rendered_prompt"])

        with (
            patch("modules.generation.prompt_builder.settings.prompt_source", "db"),
            patch.object(PromptBuilder, "_load_db_template", return_value=None),
        ):
            with self.assertRaisesRegex(RuntimeError, "PROMPT_TEMPLATE_NOT_FOUND"):
                PromptBuilder().build(
                    context="nguồn",
                    bloom_level="2_hieu",
                    question_type="trac_nghiem",
                    num_questions=1,
                )

    def test_model_role_digest_and_structured_output_contract(self):
        base = {
            "model_code": "qwen",
            "model_name": "qwen2.5:7b",
            "runtime": "OLLAMA",
            "parameters": {"temperature": 0},
        }
        general = bind_model_role(base, GENERAL_GENERATION_ROLE)
        code = bind_model_role(base, CODE_GENERATION_ROLE)
        self.assertNotEqual(general["model_digest"], code["model_digest"])
        self.assertEqual(general["resource_profile"]["group"], "gpu:local_inference")

        parsed = parse_structured_json('{"questions": [{"question": "Q"}]}')
        self.assertEqual(extract_question_candidates(parsed)[0]["question"], "Q")
        with self.assertRaisesRegex(ValueError, "STRUCTURED_OUTPUT_SCHEMA_ERROR"):
            extract_question_candidates(parse_structured_json('{"questions": {}}'))

    def test_model_artifact_digest_is_distinct_from_config_digest(self):
        base = {
            "model_code": "qwen",
            "model_name": "qwen2.5:7b",
            "runtime": "OLLAMA",
            "revision": "release-1",
            "quantization": "Q4_K_M",
            "parameters": {"temperature": 0},
        }
        first = bind_model_role(
            {**base, "artifact_digest": "sha256:weights-a"}, GENERAL_GENERATION_ROLE
        )
        second = bind_model_role(
            {**base, "artifact_digest": "sha256:weights-b"}, GENERAL_GENERATION_ROLE
        )

        self.assertEqual(first["config_digest"], second["config_digest"])
        self.assertNotEqual(first["model_digest"], second["model_digest"])

    def test_generation_request_normalizes_clos_and_retrieval_contract(self):
        request = QuestionGenerateRequest(
            document_id="document-1",
            bloom_level="2_hieu",
            topic="  hàng đợi  ",
            clo_codes=[" clo2 ", "CLO2"],
            retrieval_mode="hybrid",
        )
        self.assertEqual(request.topic, "hàng đợi")
        self.assertEqual(request.clo_codes, ["CLO2"])

    def test_retrieval_benchmark_recall(self):
        self.assertEqual(recall_at_k(["a", "b"], ["b", "c"]), 0.5)

    def test_context_budget_never_accepts_oversized_first_chunk(self):
        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1")),
            patch(
                "modules.rag.search._mongo_lexical_candidates",
                return_value=[
                    (
                        "oversized evidence",
                        {"chunk_id": "large", "chunk_set_id": "set-1", "token_count": 200},
                    )
                ],
            ),
        ):
            with self.assertRaisesRegex(ValueError, "token budget"):
                get_context_snapshot(
                    document_id="document-1",
                    collection_name="chunks",
                    retrieval_mode="lexical",
                    context_token_budget=128,
                )


if __name__ == "__main__":
    unittest.main()
