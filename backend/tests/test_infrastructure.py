import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId

from core import database
from core.job_worker import process_available_jobs_once
from modules.generation.mongodb import retry_or_dead_letter_generation_job


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


if __name__ == "__main__":
    unittest.main()
