from typing import Protocol

from pymongo import ReturnDocument
from pymongo.database import Database

from core.database import get_auth_db

class FirebaseSessionRepository(Protocol):
    def upsert(self, uid: str, token: str | None) -> dict: ...

    def find_by_uid(self, uid: str) -> dict | None: ...


class MongoFirebaseSessionRepository:
    """Persistence adapter for the minimal NCKH.User Firebase session link."""

    def __init__(self, database: Database):
        self.collection = database["User"]

    def upsert(self, uid: str, token: str | None) -> dict:
        return self.collection.find_one_and_replace(
            {"uid": uid},
            {"uid": uid, "token": token},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    def find_by_uid(self, uid: str) -> dict | None:
        return self.collection.find_one({"uid": uid})


def get_firebase_session_repository() -> FirebaseSessionRepository:
    return MongoFirebaseSessionRepository(get_auth_db())
