import unittest
from unittest.mock import AsyncMock, patch

from core import database
from core.job_worker import process_available_jobs_once


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
        generation_processor.assert_awaited_once_with("generation-job")
        evaluation_processor.assert_awaited_once_with("evaluation-job")


if __name__ == "__main__":
    unittest.main()
