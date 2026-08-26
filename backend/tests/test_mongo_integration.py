import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from core.database import get_database, mongo_transaction
from modules.generation.mongodb import claim_generation_job


@unittest.skipUnless(os.getenv("RUN_MONGO_INTEGRATION") == "1", "requires Mongo replica set")
class MongoReplicaSetIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db = get_database()
        self.job_ids: list[ObjectId] = []

    def tearDown(self):
        if self.job_ids:
            self.db.generation_jobs.delete_many({"_id": {"$in": self.job_ids}})
        self.db.integration_transactions.delete_many({"test_marker": "codex-integration"})

    def test_transaction_rolls_back_on_error(self):
        try:
            with mongo_transaction() as session:
                self.db.integration_transactions.insert_one(
                    {"test_marker": "codex-integration"},
                    session=session,
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass

        self.assertIsNone(
            self.db.integration_transactions.find_one({"test_marker": "codex-integration"})
        )

    def test_only_one_worker_can_claim_a_queued_job(self):
        now = datetime.now(timezone.utc)
        job_id = ObjectId()
        self.job_ids.append(job_id)
        self.db.generation_jobs.insert_one(
            {
                "_id": job_id,
                "request": {},
                "requested_by_user_id": None,
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": 3,
                "result": None,
                "metrics": None,
                "error_message": None,
                "created_at": now,
                "updated_at": now,
            }
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda worker: claim_generation_job(str(job_id), worker),
                    ("worker-a", "worker-b"),
                )
            )

        claimed = [result for result in results if result is not None]
        self.assertEqual(len(claimed), 1)
        self.assertIn(claimed[0]["locked_by"], {"worker-a", "worker-b"})

    def test_expired_lease_can_be_reclaimed(self):
        now = datetime.now(timezone.utc)
        job_id = ObjectId()
        self.job_ids.append(job_id)
        self.db.generation_jobs.insert_one(
            {
                "_id": job_id,
                "request": {},
                "requested_by_user_id": None,
                "status": "processing",
                "attempt_count": 1,
                "max_attempts": 3,
                "locked_by": "dead-worker",
                "lease_expires_at": now - timedelta(seconds=1),
                "result": None,
                "metrics": None,
                "error_message": None,
                "created_at": now,
                "updated_at": now,
            }
        )

        claimed = claim_generation_job(str(job_id), "replacement-worker")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["locked_by"], "replacement-worker")
        self.assertEqual(claimed["attempt_count"], 2)


if __name__ == "__main__":
    unittest.main()
