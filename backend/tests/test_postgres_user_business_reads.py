"""User PostgreSQL mode must read still-live business records from MongoDB."""

from bson import ObjectId

from modules.users import postgres_repository


class Collection:
    def __init__(self, records):
        self.records = records

    def find(self, query, projection=None):
        def matches(record):
            for field, expected in query.items():
                actual = record.get(field)
                if isinstance(expected, dict) and "$ne" in expected:
                    if actual == expected["$ne"]:
                        return False
                elif isinstance(expected, dict) and "$in" in expected:
                    if actual not in expected["$in"]:
                        return False
                elif actual != expected:
                    return False
            return True
        return [record for record in self.records if matches(record)]

    def count_documents(self, query):
        return len(self.find(query))


def test_postgres_user_stats_and_calendar_read_live_business_data(monkeypatch):
    user_id, document_id, question_id = ObjectId(), ObjectId(), ObjectId()
    documents = Collection([
        {"_id": document_id, "uploaded_by_user_id": user_id, "status": "READY"},
        {"_id": ObjectId(), "uploaded_by_user_id": user_id, "status": "ARCHIVED"},
    ])
    questions = Collection([
        {"_id": question_id, "created_by_user_id": user_id, "document_id": document_id,
         "review_status": "PENDING", "lifecycle_status": "DRAFT"},
        {"_id": ObjectId(), "created_by_user_id": user_id,
         "review_status": "APPROVED", "lifecycle_status": "ARCHIVED"},
    ])
    db = type("Database", (), {"users": Collection([]), "documents": documents,
                               "questions": questions})()
    monkeypatch.setattr(postgres_repository, "get_database", lambda: db)
    monkeypatch.setattr(postgres_repository, "postgres_connection",
                        lambda: (_ for _ in ()).throw(AssertionError("shadow tables queried")))

    repository = postgres_repository.PostgresUserRepository()
    assert repository.get_stats(user_id) == {
        "documents_count": 1, "questions_count": 1, "pending_questions_count": 1,
    }
    assert repository.get_calendar_documents(user_id) == [documents.records[0]]
    assert repository.get_calendar_questions(user_id) == [questions.records[0]]
    assert repository.get_document_ids_with_questions([document_id]) == {str(document_id)}


def test_postgres_review_calendar_delegates_to_question_store(monkeypatch):
    from core.config import settings
    from modules.questions.postgres_repository import PostgresQuestionRepository
    user_id, other_id = ObjectId(), ObjectId()
    held = [{"_id": ObjectId(), "review_assignment": {"reviewer_user_id": user_id}},
            {"_id": ObjectId(), "review_assignment": {"reviewer_user_id": other_id}}]
    monkeypatch.setattr(settings, "question_store", "postgres")
    monkeypatch.setattr(PostgresQuestionRepository, "__init__", lambda self: None)
    monkeypatch.setattr(PostgresQuestionRepository, "held_reviews", lambda self: held)
    monkeypatch.setattr(PostgresQuestionRepository, "count_unassigned_pending", lambda self: 7)
    repository = postgres_repository.PostgresUserRepository()
    assert repository.get_review_assignment_questions(user_id) == held[:1]
    assert repository.count_unassigned_pending() == 7
