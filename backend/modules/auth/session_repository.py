from datetime import datetime, timezone
from typing import Protocol

from pymongo import ReturnDocument
from pymongo.database import Database

from core.database import get_auth_db

class FirebaseSessionRepository(Protocol):
    def upsert(self, uid: str, token: str | None) -> dict: ...

    def find_by_uid(self, uid: str) -> dict | None: ...


class MongoFirebaseSessionRepository:
    """Persist only a revocable identity marker, never the Firebase bearer token."""

    def __init__(self, database: Database):
        self.collection = database["User"]

    def upsert(self, uid: str, token: str | None) -> dict:
        return self.collection.find_one_and_replace(
            {"uid": uid},
            {
                "uid": uid,
                # Kept nullable for schema/read compatibility while legacy raw
                # bearer values are removed by the stage-B migration.
                "token": None,
                "last_seen_at": datetime.now(timezone.utc),
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    def find_by_uid(self, uid: str) -> dict | None:
        return self.collection.find_one({"uid": uid})


def get_firebase_session_repository() -> FirebaseSessionRepository:
    return MongoFirebaseSessionRepository(get_auth_db())
