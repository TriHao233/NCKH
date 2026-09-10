import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.service import get_document_service
from modules.generation.generate import router
from modules.generation.mongodb import _resolve_clo_ids
from modules.generation.prompt_builder import PromptBuilder
from modules.generation.question import (
    _content_mode,
    _focused_context_snapshot,
    _generate_questions_for_plan_item,
    generate_questions_rag,
)
from modules.generation.schemas import (
    GeneratedQuestion,
    GenerationPlanSummary,
    QuestionGenerateRequest,
    QuestionPlanItem,
)
from modules.generation.postprocessing import question_fingerprint
from modules.rag.search import _hybrid_score, _keyword_tokens, get_context_snapshot


def user(role: str = "Teacher") -> CurrentUser:
    oid = ObjectId()
    return CurrentUser(
        id=oid,
        firebase_uid=f"firebase-{oid}",
        email="teacher@example.com",
        role=role,
        is_active=True,
        permissions=(),
    )


class GenerationStatusApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.current_user = user()
        self.app.dependency_overrides[require_teacher_or_admin] = lambda: self.current_user
        self.app.dependency_overrides[get_document_service] = lambda: type(
            "DocumentServiceStub",
            (),
            {"can_use": staticmethod(lambda _document_id, _user: True)},
        )()
        self.client = TestClient(self.app)
        self.job_id = str(ObjectId())

    def tearDown(self):
        self.app.dependency_overrides.clear()

    @staticmethod
    def queued_job(job_id: str) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }

    def test_teacher_status_lookup_is_scoped_to_owner(self):
        with patch("modules.generation.generate.get_generation_job") as lookup:
            lookup.return_value = self.queued_job(self.job_id)
            response = self.client.get(f"/api/v1/generate/status/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with(self.job_id, requested_by_user_id=self.current_user.id)

    def test_other_teacher_receives_not_found(self):
        with patch("modules.generation.generate.get_generation_job", return_value=None) as lookup:
            response = self.client.get(f"/api/v1/generate/status/{self.job_id}")

        self.assertEqual(response.status_code, 404)
        lookup.assert_called_once_with(self.job_id, requested_by_user_id=self.current_user.id)

    def test_admin_can_inspect_any_generation_job(self):
        self.current_user = user("Admin")
        with patch("modules.generation.generate.get_generation_job") as lookup:
            lookup.return_value = self.queued_job(self.job_id)
            response = self.client.get(f"/api/v1/generate/status/{self.job_id}")

        self.assertEqual(response.status_code, 200)
        lookup.assert_called_once_with(self.job_id, requested_by_user_id=None)

    def test_status_event_stream_is_scoped_and_finishes_on_terminal_status(self):
        completed = self.queued_job(self.job_id)
        completed["status"] = "completed"
        completed["result"] = {"data": [], "summary": []}
        completed["progress"] = {"stage": "completed", "completed": 1, "total": 1}
        with patch("modules.generation.generate.get_generation_job", return_value=completed) as lookup:
            response = self.client.get(f"/api/v1/generate/status/{self.job_id}/events")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        self.assertIn("event: status", response.text)
        self.assertIn('"status":"completed"', response.text)
        self.assertTrue(
            all(
                call.kwargs.get("requested_by_user_id") == self.current_user.id
                for call in lookup.call_args_list
            )
        )

    @staticmethod
    def generation_payload() -> dict:
        return {
            "document_id": str(ObjectId()),
            "bloom_level": "2_hieu",
            "question_type": "dung_sai",
            "num_questions": 1,
        }

    def test_enqueue_reuses_job_for_same_idempotency_key(self):
        existing = self.queued_job(self.job_id)
        with (
            patch("modules.generation.generate.get_generation_job_by_idempotency", return_value=existing),
            patch("modules.generation.generate.count_active_generation_jobs") as count_active,
            patch("modules.generation.generate.create_generation_job") as create_job,
        ):
            response = self.client.post(
                "/api/v1/generate/questions",
                json=self.generation_payload(),
                headers={"Idempotency-Key": "request-123"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["job_id"], self.job_id)
        count_active.assert_not_called()
        create_job.assert_not_called()

    def test_enqueue_rejects_user_over_active_job_quota(self):
        with (
            patch("modules.generation.generate.get_generation_job_by_idempotency", return_value=None),
            patch("modules.generation.generate.count_active_generation_jobs", return_value=10),
            patch("modules.generation.generate.create_generation_job") as create_job,
        ):
            response = self.client.post(
                "/api/v1/generate/questions",
                json=self.generation_payload(),
                headers={"Idempotency-Key": "request-over-quota"},
            )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "15")
        create_job.assert_not_called()

    def test_enqueue_freezes_resolved_model_snapshot(self):
        snapshot = {
            "model_code": "qwen-fast",
            "model_name": "qwen2.5:14b",
            "runtime": "OLLAMA",
            "source": "catalog",
        }
        with (
            patch("modules.generation.generate.count_active_generation_jobs", return_value=0),
            patch("modules.generation.generate.resolve_model_snapshot", return_value=snapshot),
            patch("modules.generation.generate.create_generation_job", return_value=self.job_id) as create_job,
        ):
            payload = self.generation_payload()
            payload["model_provider"] = "qwen-fast"
            response = self.client.post("/api/v1/generate/questions", json=payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(create_job.call_args.kwargs["model_snapshot"], snapshot)
        self.assertEqual(create_job.call_args.kwargs["code_model_snapshot"], snapshot)
        self.assertIsNone(create_job.call_args.kwargs["fallback_model_snapshot"])

    def test_enqueue_freezes_separate_code_model_snapshot(self):
        general_snapshot = {"model_code": "qwen", "runtime": "OLLAMA"}
        code_snapshot = {"model_code": "deepseek", "runtime": "OLLAMA"}
        with (
            patch("modules.generation.generate.count_active_generation_jobs", return_value=0),
            patch(
                "modules.generation.generate.resolve_model_snapshot",
                side_effect=[general_snapshot, code_snapshot],
            ) as resolve,
            patch("modules.generation.generate.create_generation_job", return_value=self.job_id) as create_job,
        ):
            payload = self.generation_payload()
            payload.update({"model_provider": "qwen", "code_model_provider": "deepseek"})
            response = self.client.post("/api/v1/generate/questions", json=payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual([call.args[0] for call in resolve.call_args_list], ["qwen", "deepseek"])
        self.assertEqual(create_job.call_args.kwargs["model_snapshot"], general_snapshot)
        self.assertEqual(create_job.call_args.kwargs["code_model_snapshot"], code_snapshot)

    def test_content_mode_detects_code_and_honors_override(self):
        auto = QuestionPlanItem(question_type="trac_nghiem", content_mode="auto")
        forced_general = QuestionPlanItem(question_type="trac_nghiem", content_mode="general")
        context = "```cpp\nint push(int value) { return value; }\n```"

        self.assertEqual(_content_mode(auto, context, None), "code")
        self.assertEqual(_content_mode(forced_general, context, None), "general")

    def test_prompt_contains_content_mode_and_valid_clo_catalog(self):
        prompt = PromptBuilder().build(
            context="Stack dùng nguyên tắc LIFO.",
            bloom_level="3_van_dung",
            question_type="trac_nghiem",
            num_questions=1,
            content_mode="code",
            learning_outcomes=[{"clo_code": "CLO2", "description": "Cài đặt cấu trúc dữ liệu"}],
        )

        self.assertIn("CONTENT MODE: CODE", prompt)
        self.assertIn("CLO2: Cài đặt cấu trúc dữ liệu", prompt)
        self.assertIn("Do not invent codes", prompt)

    def test_hybrid_score_rewards_keyword_overlap(self):
        query_tokens = _keyword_tokens("cây nhị phân tìm kiếm")
        matching = _hybrid_score("Duyệt cây nhị phân tìm kiếm", {}, query_tokens, vector_rank=1)
        unrelated = _hybrid_score("Ngăn xếp hoạt động theo LIFO", {}, query_tokens, vector_rank=1)

        self.assertGreater(matching, unrelated)

    def test_context_snapshot_combines_semantic_and_keyword_ranking(self):
        class CollectionStub:
            def count(self):
                return 2

            def query(self, **kwargs):
                self.query_kwargs = kwargs
                return {
                    "documents": [["Stack dùng LIFO.", "Cây nhị phân tìm kiếm hỗ trợ tra cứu."]],
                    "metadatas": [[
                        {"chunk_id": "stack", "chunk_set_id": "set-1", "information_density": 0},
                        {"chunk_id": "tree", "chunk_set_id": "set-1", "information_density": 0},
                    ]],
                }

        collection = CollectionStub()
        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1")),
            patch("modules.rag.search.get_collection", return_value=collection),
        ):
            snapshot = get_context_snapshot(
                document_id=str(ObjectId()),
                collection_name="chunks",
                query_text="cây nhị phân tìm kiếm",
                limit=2,
            )

        self.assertEqual(collection.query_kwargs["query_texts"], ["cây nhị phân tìm kiếm"])
        self.assertEqual(snapshot["results"][0]["chunk_id"], "tree")

    def test_context_snapshot_excludes_heading_only_chunks(self):
        class CollectionStub:
            def count(self):
                return 3

            def query(self, **kwargs):
                return {
                    "documents": [[
                        "# Chương 6: MẢNG",
                        "Mảng là cấu trúc dữ liệu lưu nhiều phần tử cùng kiểu.",
                        "Mảng có thể được truy cập bằng chỉ số của phần tử.",
                    ]],
                    "metadatas": [[
                        {"chunk_id": "heading", "chunk_set_id": "set-1", "heading": "Chương 6: MẢNG"},
                        {"chunk_id": "definition", "chunk_set_id": "set-1", "heading": "Chương 6: MẢNG"},
                        {"chunk_id": "index", "chunk_set_id": "set-1", "heading": "Chương 6: MẢNG"},
                    ]],
                }

        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1")),
            patch("modules.rag.search.get_collection", return_value=CollectionStub()),
        ):
            snapshot = get_context_snapshot(
                document_id=str(ObjectId()),
                collection_name="chunks",
                target_heading="Chương 6: MẢNG",
                limit=2,
            )
        self.assertEqual([item["chunk_id"] for item in snapshot["results"]], ["definition", "index"])
        self.assertNotIn("Nội dung: # Chương 6: MẢNG", snapshot["context_text"])

    def test_context_snapshot_excludes_nested_markdown_heading(self):
        class CollectionStub:
            def count(self):
                return 2

            def query(self, **kwargs):
                return {
                    "documents": [[
                        "## IV. TRUY CẬP TẬP TIN NHỊ PHÂN",
                        "Tập tin nhị phân được đọc bằng các hàm phù hợp với kiểu dữ liệu đã lưu.",
                    ]],
                    "metadatas": [[
                        {
                            "chunk_id": "heading",
                            "chunk_set_id": "set-1",
                            "heading": "IV. TRUY CẬP TẬP TIN NHỊ PHÂN",
                            "heading_path_text": "Chương 10 > IV. TRUY CẬP TẬP TIN NHỊ PHÂN",
                        },
                        {"chunk_id": "content", "chunk_set_id": "set-1", "heading": "Chương 10"},
                    ]],
                }

        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1")),
            patch("modules.rag.search.get_collection", return_value=CollectionStub()),
        ):
            snapshot = get_context_snapshot(
                document_id=str(ObjectId()),
                collection_name="chunks",
                query_text="truy cập tập tin",
                limit=2,
            )

        self.assertEqual([item["chunk_id"] for item in snapshot["results"]], ["content"])
        self.assertNotIn("Nội dung: ##", snapshot["context_text"])

    def test_context_snapshot_matches_short_chapter_heading(self):
        class CollectionStub:
            def count(self):
                return 2

            def query(self, **kwargs):
                return {
                    "documents": [[
                        "Mảng một chiều lưu các phần tử cùng kiểu dữ liệu.",
                        "Chuỗi ký tự là một dãy các ký tự liên tiếp.",
                    ]],
                    "metadatas": [[
                        {"chunk_id": "array", "chunk_set_id": "set-1", "heading": "Chương 6"},
                        {"chunk_id": "string", "chunk_set_id": "set-1", "heading": "Chương 8"},
                    ]],
                }

        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1")),
            patch("modules.rag.search.get_collection", return_value=CollectionStub()),
        ):
            snapshot = get_context_snapshot(
                document_id=str(ObjectId()),
                collection_name="chunks",
                target_heading="Chương 6: MẢNG",
                limit=2,
            )

        self.assertEqual([item["chunk_id"] for item in snapshot["results"]], ["array"])

    def test_clo_resolution_prefers_model_code_from_catalog(self):
        outcomes = [
            {"id": str(ObjectId()), "clo_code": "CLO1", "description": "Giải thích cấu trúc dữ liệu"},
            {"id": str(ObjectId()), "clo_code": "CLO2", "description": "Cài đặt cấu trúc dữ liệu"},
        ]
        with patch("modules.generation.mongodb.get_document_learning_outcomes", return_value=outcomes):
            result = _resolve_clo_ids(
                str(ObjectId()),
                {"question": "Viết mã cài đặt stack", "clo_codes": ["clo2", "không-tồn-tại"]},
            )

        self.assertEqual(result, [outcomes[1]["id"]])


class IncrementalGenerationTests(unittest.IsolatedAsyncioTestCase):
    def test_focused_context_snapshot_rotates_context_sections(self):
        snapshot = {
            "context_text": "Mục lục: [A]\nNội dung: A đủ dài.\n\n---\n\nMục lục: [B]\nNội dung: B đủ dài.",
            "results": [{"chunk_id": "a"}, {"chunk_id": "b"}],
            "chunk_set_id": "set-1",
            "vector_collection_id": "vec-1",
        }

        first, first_directive = _focused_context_snapshot(snapshot, 0)
        second, second_directive = _focused_context_snapshot(snapshot, 1)

        self.assertIn("Nội dung: A", first["context_text"])
        self.assertEqual(first["results"], [{"chunk_id": "a"}])
        self.assertIn("section 1 of 2", first_directive)
        self.assertIn("Nội dung: B", second["context_text"])
        self.assertEqual(second["results"], [{"chunk_id": "b"}])
        self.assertIn("section 2 of 2", second_directive)

    async def test_generation_saves_and_reports_each_question_independently(self):
        request = QuestionGenerateRequest(
            document_id=str(ObjectId()),
            bloom_level="2_hieu",
            question_type="trac_nghiem",
            num_questions=3,
        )
        progress_updates = []

        async def generate_one(_req, plan_item, *, plan_index, **_kwargs):
            question_number = generate_one.call_count
            generate_one.call_count += 1
            question = GeneratedQuestion(
                question=f"Câu hỏi {question_number}",
                options={"A": "Một", "B": "Hai", "C": "Ba", "D": "Bốn"},
                correct_answer="A",
                explanation="Giải thích",
                question_type="trac_nghiem",
                bloom_level="2_hieu",
                source_context="Nội dung nguồn đủ dài để kiểm thử.",
                question_id=str(ObjectId()),
            )
            summary = GenerationPlanSummary(
                plan_index=plan_index,
                question_type="trac_nghiem",
                bloom_level="2_hieu",
                requested_count=plan_item.num_questions,
                parsed_count=1,
                valid_count=1,
                saved_count=1,
            )
            return [question], summary

        generate_one.call_count = 1

        async def report_progress(progress):
            progress_updates.append(progress)

        with (
            patch(
                "modules.generation.question.get_context_snapshot",
                return_value={
                    "context_text": "Nội dung: Kiến thức dùng để sinh câu hỏi.",
                    "results": [],
                    "chunk_set_id": None,
                    "vector_collection_id": None,
                },
            ),
            patch("modules.generation.question.get_document_learning_outcomes", return_value=[]),
            patch("modules.generation.question.get_existing_question_texts", return_value=[]),
            patch("modules.generation.question.resolve_model_snapshot", return_value={}),
            patch("modules.generation.question.get_llm_service", return_value=object()),
            patch(
                "modules.generation.question._generate_questions_for_plan_item",
                new=AsyncMock(side_effect=generate_one),
            ) as generate_batch,
        ):
            result = await generate_questions_rag(request, progress_callback=report_progress)

        self.assertEqual(generate_batch.await_count, 3)
        self.assertTrue(all(call.args[1].num_questions == 1 for call in generate_batch.await_args_list))
        self.assertEqual(len(result.data), 3)
        self.assertEqual(result.summary[0].requested_count, 3)
        self.assertEqual(result.summary[0].saved_count, 3)
        self.assertEqual([item["completed"] for item in progress_updates], [0, 1, 2, 3])
        self.assertEqual([len(item["data"]) for item in progress_updates], [0, 1, 2, 3])

    async def test_invalid_json_only_rejects_the_current_question(self):
        request = QuestionGenerateRequest(
            document_id=str(ObjectId()),
            bloom_level="2_hieu",
            question_type="trac_nghiem",
            num_questions=1,
        )
        plan_item = request.effective_plan()[0]
        llm = MagicMock()
        llm.generate_text = AsyncMock(return_value='{"questions": [{"question": "bị cắt"}')
        prompt_builder = MagicMock()
        prompt_builder.build.return_value = "prompt"

        with (
            patch("modules.generation.question.create_generation_run", return_value=str(ObjectId())),
            patch("modules.generation.question.finish_generation_run") as finish_run,
            patch("modules.generation.question.reset_llm_execution_tracking"),
            patch("modules.generation.question.get_llm_execution_snapshot", return_value={}),
        ):
            questions, summary = await _generate_questions_for_plan_item(
                request,
                plan_item,
                plan_index=1,
                avoid_questions=[],
                seen_question_fingerprints=set(),
                context_snapshot={
                    "results": [],
                    "chunk_set_id": None,
                    "vector_collection_id": None,
                },
                context_text="Nội dung: Kiến thức dùng để sinh câu hỏi.",
                prompt_builder=prompt_builder,
                llm=llm,
                model_snapshot={},
                model_provider="qwen",
                content_mode="general",
                learning_outcomes=[],
            )

        self.assertEqual(questions, [])
        self.assertEqual(summary.saved_count, 0)
        self.assertEqual(summary.rejection_reasons[0].code, "INVALID_JSON_RESPONSE")
        finish_run.assert_called_once()
        self.assertEqual(finish_run.call_args.kwargs["status"], "FAILED")

    async def test_duplicate_candidate_is_retried_before_fallback(self):
        source_context = "Kiến thức dùng để sinh câu hỏi về ngăn xếp LIFO."
        duplicate_question = {
            "question": "Ngăn xếp hoạt động theo nguyên tắc nào?",
            "options": {"A": "FIFO", "B": "LIFO", "C": "Random", "D": "Hash"},
            "correct_answer": "B",
            "explanation": "Ngăn xếp hoạt động theo LIFO.",
            "question_type": "trac_nghiem",
            "bloom_level": "2_hieu",
            "source_context": source_context,
            "source_keywords": ["ngăn xếp"],
            "false_mutation": None,
        }
        unique_question = {
            **duplicate_question,
            "question": "Vì sao thao tác pop của ngăn xếp lấy phần tử được thêm sau cùng?",
            "options": {
                "A": "Vì ngăn xếp dùng FIFO",
                "B": "Vì ngăn xếp dùng LIFO",
                "C": "Vì ngăn xếp sắp xếp theo khóa",
                "D": "Vì ngăn xếp truy cập ngẫu nhiên",
            },
        }
        request = QuestionGenerateRequest(
            document_id=str(ObjectId()),
            bloom_level="2_hieu",
            question_type="trac_nghiem",
            num_questions=1,
        )
        plan_item = request.effective_plan()[0]
        llm = MagicMock()
        llm.generate_text = AsyncMock(side_effect=[
            json.dumps({"questions": [duplicate_question]}, ensure_ascii=False),
            json.dumps({"questions": [unique_question]}, ensure_ascii=False),
        ])
        prompt_builder = MagicMock()
        prompt_builder.build.return_value = "prompt"

        with (
            patch("modules.generation.question.create_generation_run", return_value=str(ObjectId())),
            patch("modules.generation.question.finish_generation_run"),
            patch("modules.generation.question.reset_llm_execution_tracking"),
            patch("modules.generation.question.get_llm_execution_snapshot", return_value={}),
            patch(
                "modules.generation.question.save_generated_questions",
                return_value=[{**unique_question, "question_id": str(ObjectId())}],
            ) as save_questions,
        ):
            questions, summary = await _generate_questions_for_plan_item(
                request,
                plan_item,
                plan_index=1,
                avoid_questions=[duplicate_question["question"]],
                seen_question_fingerprints={question_fingerprint(duplicate_question["question"])},
                context_snapshot={
                    "results": [],
                    "chunk_set_id": None,
                    "vector_collection_id": None,
                },
                context_text=f"Nội dung: {source_context}",
                prompt_builder=prompt_builder,
                llm=llm,
                model_snapshot={},
                model_provider="qwen",
                content_mode="general",
                learning_outcomes=[],
            )

        self.assertEqual(llm.generate_text.call_count, 2)
        self.assertEqual(questions[0].question, unique_question["question"])
        self.assertEqual(save_questions.call_args.args[1][0]["question"], unique_question["question"])
        self.assertEqual(summary.saved_count, 1)
        self.assertEqual(summary.retry_attempt_count, 1)


if __name__ == "__main__":
    unittest.main()
