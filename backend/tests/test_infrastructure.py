import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from core import database
from core.job_worker import process_available_jobs_once
from modules.admin.job_metrics import collect_job_metrics
from modules.generation.mongodb import retry_or_dead_letter_generation_job
from modules.generation.llm.model_registry import (
    GENERATION_CAPABILITY,
    available_model_options,
    resolve_model_snapshot,
)
from modules.generation.llm.base import LLMProvider
from modules.generation.llm.factory import get_llm_execution_snapshot
from modules.generation.llm.fallback import FallbackProvider


class MongoTransactionTests(unittest.TestCase):
    def test_required_transactions_fail_fast_on_standalone_mongo(self):
        with (
            patch("core.database.supports_transactions", return_value=False),
            patch.object(database.settings, "require_mongo_transactions", True),
        ):
            with self.assertRaisesRegex(RuntimeError, "replica set"):
                with database.mongo_transaction():
                    pass

    def test_local_development_can_explicitly_allow_non_transactional_writes(self):
        with (
            patch("core.database.supports_transactions", return_value=False),
            patch.object(database.settings, "require_mongo_transactions", False),
        ):
            with database.mongo_transaction() as session:
                self.assertIsNone(session)


class JobWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_processes_generation_and_evaluation_queues(self):
        generation_processor = AsyncMock()
        evaluation_processor = AsyncMock()
        with (
            patch(
                "modules.generation.mongodb.get_next_queued_generation_job_id",
                return_value="generation-job",
            ),
            patch(
                "core.job_worker.get_next_queued_evaluation_job_id",
                return_value="evaluation-job",
            ),
            patch(
                "modules.generation.generate.process_generate_background",
                generation_processor,
            ),
            patch(
                "modules.questions.workflow_service.process_evaluation_job_background",
                evaluation_processor,
            ),
        ):
            found_work = await process_available_jobs_once()

        self.assertTrue(found_work)
        generation_processor.assert_awaited_once()
        evaluation_processor.assert_awaited_once()
        self.assertEqual(generation_processor.await_args.args[0], "generation-job")
        self.assertEqual(evaluation_processor.await_args.args[0], "evaluation-job")
        self.assertEqual(generation_processor.await_args.args[1], evaluation_processor.await_args.args[1])


class GenerationRetryTests(unittest.TestCase):
    def test_failure_is_requeued_before_max_attempts(self):
        database = MagicMock()
        job = {"job_id": str(ObjectId()), "attempt_count": 1, "max_attempts": 3}
        with patch("modules.generation.mongodb.get_database", return_value=database):
            next_status = retry_or_dead_letter_generation_job(
                job,
                "worker-1",
                error_message="temporary failure",
            )

        self.assertEqual(next_status, "queued")
        update = database.generation_jobs.update_one.call_args.args[1]
        self.assertEqual(update["$set"]["status"], "queued")
        self.assertIn("next_attempt_at", update["$set"])
        self.assertNotIn("dead_lettered_at", update["$set"])

    def test_last_failure_is_marked_as_dead_letter(self):
        database = MagicMock()
        job = {"job_id": str(ObjectId()), "attempt_count": 3, "max_attempts": 3}
        with patch("modules.generation.mongodb.get_database", return_value=database):
            next_status = retry_or_dead_letter_generation_job(
                job,
                "worker-1",
                error_message="permanent failure",
            )

        self.assertEqual(next_status, "failed")
        update = database.generation_jobs.update_one.call_args.args[1]
        self.assertEqual(update["$set"]["status"], "failed")
        self.assertIn("dead_lettered_at", update["$set"])
        self.assertIn("expires_at", update["$set"])


class JobMetricsTests(unittest.TestCase):
    def test_metrics_expose_queue_lease_dead_letter_and_llm_slot_counts(self):
        database = MagicMock()
        database.generation_jobs.find_one.return_value = None
        database.evaluation_jobs.find_one.return_value = None
        database.document_jobs.find_one.return_value = None
        database.generation_jobs.count_documents.side_effect = [2, 1, 1, 3, 1]
        database.evaluation_jobs.count_documents.side_effect = [4, 2, 1, 2, 0]
        database.document_jobs.count_documents.side_effect = [5, 2]
        database.llm_slots.count_documents.side_effect = [1, 0]

        metrics = collect_job_metrics(database)

        self.assertEqual(metrics["queues"]["generation"]["queued"], 2)
        self.assertEqual(metrics["queues"]["generation"]["dead_lettered"], 3)
        self.assertEqual(metrics["queues"]["evaluation"]["processing"], 2)
        self.assertEqual(metrics["queues"]["document"]["queued"], 5)
        self.assertEqual(metrics["llm_slots"], {"in_use": 1, "expired": 0})


class ModelRegistryTests(unittest.TestCase):
    def test_resolver_does_not_truth_test_pymongo_database(self):
        database = MagicMock()
        database.__bool__.side_effect = NotImplementedError(
            "Database objects do not implement truth value testing"
        )
        database.ai_models.find_one.return_value = {
            "model_code": "qwen-fast",
            "model_name": "qwen2.5:7b",
            "runtime": "OLLAMA",
            "capabilities": [GENERATION_CAPABILITY],
            "is_active": True,
        }

        snapshot = resolve_model_snapshot(
            "qwen-fast",
            capability=GENERATION_CAPABILITY,
            database=database,
        )

        self.assertEqual(snapshot["model_code"], "qwen-fast")

    def test_catalog_model_resolves_version_and_safe_runtime_parameters(self):
        database = MagicMock()
        database.ai_models.find_one.return_value = {
            "_id": ObjectId(),
            "model_code": "qwen-fast",
            "display_name": "Qwen nhanh",
            "description": "Dùng cho tác vụ thông thường.",
            "model_name": "qwen2.5:14b",
            "runtime": "OLLAMA",
            "revision": "2026-08",
            "capabilities": [GENERATION_CAPABILITY],
            "config": {"temperature": 0.2, "num_predict": 1200, "timeout_seconds": 90},
            "is_active": True,
        }

        snapshot = resolve_model_snapshot(
            "qwen-fast",
            capability=GENERATION_CAPABILITY,
            database=database,
        )

        self.assertEqual(snapshot["model_name"], "qwen2.5:14b")
        self.assertEqual(snapshot["display_name"], "Qwen nhanh")
        self.assertEqual(snapshot["parameters"]["temperature"], 0.2)
        self.assertEqual(snapshot["parameters"]["num_ctx"], 8192)
        self.assertEqual(snapshot["parameters"]["num_predict"], 1200)
        self.assertEqual(snapshot["source"], "catalog")

    def test_inactive_catalog_model_is_rejected(self):
        database = MagicMock()
        database.ai_models.find_one.return_value = {
            "model_code": "paused",
            "model_name": "qwen2.5:7b",
            "runtime": "OLLAMA",
            "is_active": False,
        }

        with self.assertRaisesRegex(ValueError, "tạm dừng"):
            resolve_model_snapshot("paused", database=database)

    def test_available_models_only_return_matching_active_capability(self):
        database = MagicMock()
        cursor = MagicMock()
        cursor.sort.return_value = [
            {
                "model_code": "generation-model",
                "display_name": "Model sinh câu hỏi",
                "model_name": "qwen2.5:7b",
                "runtime": "OLLAMA",
                "capabilities": [GENERATION_CAPABILITY],
                "is_active": True,
            },
            {
                "model_code": "evaluation-only",
                "model_name": "deepseek-r1",
                "runtime": "OLLAMA",
                "capabilities": ["QUESTION_EVALUATION"],
                "is_active": True,
            },
        ]
        database.ai_models.find.return_value = cursor

        result = available_model_options(
            database,
            capability=GENERATION_CAPABILITY,
            default_code="generation-model",
        )

        self.assertEqual([item["code"] for item in result["items"]], ["generation-model"])


class _FailingProvider(LLMProvider):
    runtime_snapshot = {"model_code": "primary", "model_name": "primary-v1"}

    async def generate_text(self, prompt: str) -> str:
        raise RuntimeError(f"failed: {prompt}")


class _WorkingProvider(LLMProvider):
    runtime_snapshot = {"model_code": "fallback", "model_name": "fallback-v2"}

    async def generate_text(self, prompt: str) -> str:
        return f"ok: {prompt}"


class FallbackSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_records_the_model_that_served_the_request(self):
        provider = FallbackProvider(_FailingProvider(), _WorkingProvider())

        result = await provider.generate_text("prompt")
        snapshot = get_llm_execution_snapshot(provider)

        self.assertEqual(result, "ok: prompt")
        self.assertTrue(snapshot["fallback_used"])
        self.assertEqual(snapshot["used_model"]["model_code"], "fallback")


if __name__ == "__main__":
    unittest.main()
