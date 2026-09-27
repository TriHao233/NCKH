"""Review workflow against a real MongoDB replica set.

These cover behaviour the in-memory fakes cannot prove: upserts keyed by _id,
$in with null matching a missing field, $nin, projections, collection
validators and multi-document transactions.

Run with RUN_MONGO_INTEGRATION=1 and MONGO_URI pointing at a replica set.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from core.bootstrap import SCHEMA_VERSION, bootstrap_database
from core.config import settings
from core.database import get_database
from core.dependencies import CurrentUser
from modules.notifications.service import NotificationService
from modules.questions.repository import MongoQuestionRepository
from modules.questions.workflow_schemas import (
    AutoAssignRequest,
    ReviewAssignmentRequest,
    ReviewCreateRequest,
    ReviewPolicyPayload,
)
from modules.questions.workflow_service import REVIEW_POLICY_ID, QuestionWorkflowService

MARKER = "review-workflow-integration"


def _current_user(user_id: ObjectId, role: str) -> CurrentUser:
    return CurrentUser(id=user_id, firebase_uid=f"fb-{user_id}", email=f"{user_id}@example.com", role=role, is_active=True)


@unittest.skipUnless(os.getenv("RUN_MONGO_INTEGRATION") == "1", "requires Mongo replica set")
class ReviewWorkflowMongoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bootstrap_database()

    def setUp(self):
        self.db = get_database()
        self.now = datetime.now(timezone.utc)
        self.created: dict[str, list] = {}
        self.saved_policy = self.db.review_settings.find_one({"_id": REVIEW_POLICY_ID})
        self.db.review_settings.delete_one({"_id": REVIEW_POLICY_ID})
        self.subject_id = ObjectId()
        self.service = QuestionWorkflowService(self.db)

    def tearDown(self):
        for collection, ids in self.created.items():
            self.db[collection].delete_many({"_id": {"$in": ids}})
        question_ids = self.created.get("questions", [])
        for collection in ("question_reviews", "question_versions", "question_review_drafts"):
            self.db[collection].delete_many({"question_id": {"$in": question_ids}})
        self.db.audit_logs.delete_many({"entity.id": {"$in": question_ids}})
        self.db.audit_logs.delete_many({"entity.id": REVIEW_POLICY_ID, "created_at": {"$gte": self.now}})
        user_ids = self.created.get("users", [])
        self.db.notifications.delete_many({"recipient_user_id": {"$in": user_ids}})
        self.db.review_settings.delete_one({"_id": REVIEW_POLICY_ID})
        if self.saved_policy:
            self.db.review_settings.insert_one(self.saved_policy)

    def _track(self, collection: str, item_id) -> None:
        self.created.setdefault(collection, []).append(item_id)

    def _user(self, role: str, **extra) -> CurrentUser:
        user_id = ObjectId()
        self.db.users.insert_one(
            {
                "_id": user_id,
                "schema_version": SCHEMA_VERSION,
                "firebase_uid": f"fb-{user_id}",
                "email": f"{user_id}@example.com",
                "display_name": f"{role} {MARKER}",
                "role": role,
                "is_active": True,
                "created_at": self.now,
                "updated_at": self.now,
                **extra,
            }
        )
        self._track("users", user_id)
        return _current_user(user_id, role)

    def _question(self, author: CurrentUser, *, submitted_hours_ago=1, assignment=None, **extra) -> ObjectId:
        question_id, version_id = ObjectId(), ObjectId()
        self.db.question_versions.insert_one(
            {
                "_id": version_id,
                "schema_version": SCHEMA_VERSION,
                "question_id": question_id,
                "version": 1,
                "origin": "MANUAL",
                "document_id": None,
                "created_by_user_id": author.id,
                "classification": {
                    "subject": {"id": self.subject_id},
                    "chapter": {"id": None},
                    "assessment_type": "TRAC_NGHIEM",
                    "bloom": {"level": 2},
                    "difficulty": None,
                },
                "clos": [],
                "content": f"{MARKER} {question_id}",
                "question_data": {"options": {"A": "LIFO", "B": "FIFO"}, "correct_answer": "A"},
                "sources": [],
                "keywords": [],
                "content_hash": f"hash-{question_id}",
                "change_note": "",
                "created_at": self.now,
            }
        )
        document = {
            "_id": question_id,
            "schema_version": SCHEMA_VERSION,
            "question_code": f"Q-{str(question_id)[-6:]}",
            "current_version": 1,
            "current_version_id": version_id,
            "approved_version_id": None,
            "lifecycle_status": "ACTIVE",
            "evaluation_status": "PASSED",
            "review_status": "PENDING",
            "publication_status": "NOT_PUBLISHED",
            "quality_summary": {"overall_score": 0.9, "color": "GREEN"},
            "latest_review_id": None,
            "subject_id": self.subject_id,
            "created_by_user_id": author.id,
            "review_submission": {"submitted_at": self.now - timedelta(hours=submitted_hours_ago)},
            "created_at": self.now,
            "updated_at": self.now,
            "archived_at": None,
            **extra,
        }
        if assignment is not None:
            document["review_assignment"] = assignment
        self.db.questions.insert_one(document)
        self._track("questions", question_id)
        return question_id

    def test_policy_upsert_forces_secondary_review_inside_a_transaction(self):
        admin = self._user("Admin")
        teacher = self._user("Teacher")
        reviewer = self._user("Reviewer")
        question_id = self._question(teacher)

        # Fresh database: the policy document does not exist and must be upserted by _id.
        policy = self.service.update_review_policy(ReviewPolicyPayload(secondary_on_override=True), admin)
        self.assertTrue(policy["secondary_on_override"])
        self.assertTrue(self.service.get_review_policy()["secondary_on_override"])

        self.service.claim_review(str(question_id), reviewer)
        review = self.service.review(
            str(question_id),
            ReviewCreateRequest(
                expected_version=1,
                decision="APPROVED",
                override={"applied": True, "reason": "Đối chiếu nguồn thấy đúng"},
            ),
            reviewer,
        )

        stored = self.db.questions.find_one({"_id": question_id})
        self.assertEqual(review["resulting_status"], "PENDING")
        self.assertEqual(stored["review_status"], "PENDING")
        self.assertEqual(stored["secondary_review"]["status"], "AWAITING_SECONDARY")
        self.assertEqual(stored["secondary_review"]["primary_reviewer_user_id"], reviewer.id)
        with self.assertRaisesRegex(PermissionError, "lần hai"):
            self.service.claim_review(str(question_id), reviewer)
        with self.assertRaisesRegex(ValueError, "lần đầu"):
            self.service.assign_review(
                str(question_id),
                ReviewAssignmentRequest(reviewer_user_id=str(reviewer.id)),
                admin,
            )
        audit = self.db.audit_logs.find_one(
            {"entity.id": question_id, "action": "QUESTION_SECONDARY_REVIEW_REQUESTED"}
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit["entity"]["type"], "question")
        self.assertEqual(audit["actor"]["user_id"], reviewer.id)
        self.assertEqual(audit["actor"]["role"], "Reviewer")
        self.assertEqual(
            self.db.notifications.count_documents(
                {"recipient_user_id": teacher.id, "type": "QUESTION_SECONDARY_REVIEW_PENDING"}
            ),
            1,
        )

    def test_reviewer_decision_cancels_running_ai_evaluation_atomically(self):
        teacher = self._user("Teacher")
        reviewer = self._user("Reviewer")
        question_id = self._question(teacher, evaluation_status="PROCESSING", quality_summary={})
        version_id = self.db.questions.find_one({"_id": question_id})["current_version_id"]
        job_id = ObjectId()
        self.db.evaluation_jobs.insert_one(
            {
                "_id": job_id,
                "schema_version": SCHEMA_VERSION,
                "question_id": question_id,
                "question_version_id": version_id,
                "question_version": 1,
                "status": "PROCESSING",
                "evaluator_model_code": "test",
                "trigger": "SUBMIT_FOR_REVIEW",
                "attempt_no": 1,
                "locked_by": "worker-1",
                "lease_expires_at": self.now + timedelta(minutes=5),
                "queued_at": self.now,
                "updated_at": self.now,
            }
        )
        self._track("evaluation_jobs", job_id)

        self.service.claim_review(str(question_id), reviewer)
        review = self.service.review(
            str(question_id),
            ReviewCreateRequest(expected_version=1, decision="APPROVED"),
            reviewer,
        )

        self.assertFalse(review["override"]["applied"])
        job = self.db.evaluation_jobs.find_one({"_id": job_id})
        self.assertEqual(job["status"], "CANCELLED")
        self.assertEqual(job["error"]["stage"], "REVIEWER_DECIDED")
        self.assertNotIn("locked_by", job)
        self.assertNotIn("lease_expires_at", job)
        stored = self.db.questions.find_one({"_id": question_id})
        self.assertEqual(stored["review_status"], "APPROVED")
        self.assertEqual(stored["evaluation_status"], "NOT_STARTED")

    def test_list_filters_match_missing_assignment_overrides_and_sla(self):
        teacher = self._user("Teacher")
        never_assigned = self._question(teacher, submitted_hours_ago=settings.review_sla_hours + 2)
        released = self._question(teacher, assignment={"status": "UNASSIGNED", "reviewer_user_id": None})
        self._question(
            teacher,
            assignment={"status": "IN_REVIEW", "reviewer_user_id": ObjectId(), "lock_expires_at": self.now},
        )
        override_review_id = ObjectId()
        self.db.question_reviews.insert_one(
            {"_id": override_review_id, "question_id": ObjectId(), "override": {"applied": True}}
        )
        self._track("question_reviews", override_review_id)
        overridden = self._question(teacher, review_status="APPROVED", latest_review_id=override_review_id)

        repo = MongoQuestionRepository(self.db)

        def ids(result):
            return {question["_id"] for question, _version in result[0]}

        unassigned = repo.list(1, 50, "PENDING", None, subject_id=str(self.subject_id), assignment_status="UNASSIGNED")
        self.assertEqual(ids(unassigned), {never_assigned, released})

        overrides = repo.list(1, 50, "APPROVED", None, subject_id=str(self.subject_id), override_only=True)
        self.assertEqual(ids(overrides), {overridden})

        cutoff = self.now - timedelta(hours=settings.review_sla_hours)
        late = repo.list(1, 50, "PENDING", None, subject_id=str(self.subject_id), submitted_to=cutoff)
        self.assertEqual(ids(late), {never_assigned})

    def test_auto_assign_and_sla_reminders(self):
        admin = self._user("Admin")
        teacher = self._user("Teacher")
        specialist = self._user("Reviewer", review_subject_ids=[self.subject_id])
        late_question = self._question(teacher, submitted_hours_ago=settings.review_sla_hours + 3)
        fresh_question = self._question(teacher)

        result = self.service.auto_assign_reviews(
            AutoAssignRequest(question_ids=[str(late_question), str(fresh_question)], subject_mode="strict"),
            admin,
        )
        self.assertEqual({item["reviewer_user_id"] for item in result["assigned"]}, {str(specialist.id)})
        self.assertEqual(len(result["assigned"]), 2)
        assignment = self.db.questions.find_one({"_id": late_question})["review_assignment"]
        self.assertEqual(assignment["status"], "ASSIGNED")
        self.assertGreater(
            assignment["lock_expires_at"].replace(tzinfo=timezone.utc),
            self.now + timedelta(hours=settings.review_assignment_timeout_hours - 1),
        )

        self.service.send_review_sla_reminders(self.now)
        self.service.send_review_sla_reminders(self.now)
        reminders = list(
            self.db.notifications.find({"recipient_user_id": specialist.id, "type": "QUESTION_REVIEW_SLA_BREACHED"})
        )
        self.assertEqual(len(reminders), 1)
        self.assertIn(str(late_question), reminders[0]["link"])

        dashboard = self.service.review_dashboard(admin)
        row = next(row for row in dashboard["reviewers"] if row["user_id"] == str(specialist.id))
        self.assertEqual(row["holding"], 2)
        self.assertEqual(row["holding_sla_breached"], 1)
        self.assertEqual(row["review_subject_ids"], [str(self.subject_id)])

    def test_dashboard_counts_each_review_of_the_same_version(self):
        teacher = self._user("Teacher")
        reviewer = self._user("Reviewer")
        question_id = self._question(teacher)
        version_id = self.db.questions.find_one({"_id": question_id})["current_version_id"]
        for decision in ("APPROVED", "NEEDS_REVISION"):
            review_id = ObjectId()
            self.db.question_reviews.insert_one(
                {
                    "_id": review_id,
                    "question_id": question_id,
                    "question_version_id": version_id,
                    "reviewer_user_id": reviewer.id,
                    "decision": decision,
                    "reviewed_at": self.now,
                }
            )
            self._track("question_reviews", review_id)

        dashboard = self.service.review_dashboard(reviewer)
        self.assertEqual(dashboard["performance"]["reviews_30d"], 2)
        self.assertEqual(dashboard["subjects"][0]["subject_id"], str(self.subject_id))
        self.assertEqual(dashboard["subjects"][0]["reviewed"], 2)

    def test_exam_owner_notification_skips_finalized_exams(self):
        owner = self._user("Teacher")
        editor = self._user("Teacher")
        question_id = self._question(editor)
        exams = [
            {"_id": ObjectId(), "name": f"Mở {MARKER}", "status": "DRAFT", "created_by_user_id": owner.id,
             "questions": [{"question_id": question_id}]},
            {"_id": ObjectId(), "name": f"Chốt {MARKER}", "status": "FINALIZED", "created_by_user_id": owner.id,
             "questions": [{"question_id": question_id}]},
        ]
        self.db.exams.insert_many(exams)
        for exam in exams:
            self._track("exams", exam["_id"])

        created = NotificationService(self.db).notify_exam_owners_question_reopened(
            question_id=question_id,
            question_code="Q-INT",
            actor_user_id=editor.id,
        )
        self.assertEqual(len(created), 1)
        self.assertIn("Mở", created[0]["title"])


if __name__ == "__main__":
    unittest.main()
