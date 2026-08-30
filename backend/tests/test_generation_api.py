import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import CurrentUser, require_teacher_or_admin
from modules.documents.service import get_document_service
from modules.generation.generate import router
from modules.generation.mongodb import _resolve_clo_ids
from modules.generation.prompt_builder import PromptBuilder
from modules.generation.question import _content_mode
from modules.generation.schemas import QuestionPlanItem
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


if __name__ == "__main__":
    unittest.main()
