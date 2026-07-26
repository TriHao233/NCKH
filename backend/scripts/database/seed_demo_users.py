"""Seed fixed Firebase demo accounts for Admin and Reviewer flows."""

import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from firebase_admin import auth
from pymongo import ReturnDocument

from core.bootstrap import SCHEMA_VERSION, bootstrap_database
from core.database import get_rag_db, ping_database
from core.firebase import init_firebase


DEMO_USERS = (
    {
        "alias": "admin",
        "email": "admin@qbankctu.edu.vn",
        "password": "admin",
        "display_name": "Admin Demo",
        "role": "Admin",
    },
    {
        "alias": "reviewer",
        "email": "reviewer@qbankctu.edu.vn",
        "password": "reviewer",
        "display_name": "Reviewer Demo",
        "role": "Reviewer",
    },
)


def upsert_firebase_user(email: str, display_name: str):
    try:
        firebase_user = auth.get_user_by_email(email)
        return auth.update_user(
            firebase_user.uid,
            display_name=display_name,
            disabled=False,
            email_verified=True,
        )
    except auth.UserNotFoundError:
        return auth.create_user(
            email=email,
            display_name=display_name,
            disabled=False,
            email_verified=True,
        )


def upsert_app_user(firebase_uid: str, email: str, display_name: str, role: str) -> dict:
    now = datetime.now(timezone.utc)
    return get_rag_db().users.find_one_and_update(
        {"firebase_uid": firebase_uid},
        {
            "$set": {
                "schema_version": SCHEMA_VERSION,
                "firebase_uid": firebase_uid,
                "email": email.lower(),
                "display_name": display_name,
                "role": role,
                "profile": {"school": "", "address": "", "avatar": ""},
                "is_active": True,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


def main() -> int:
    init_firebase()
    ping_database()
    bootstrap_database()
    for demo_user in DEMO_USERS:
        firebase_user = upsert_firebase_user(
            demo_user["email"],
            demo_user["display_name"],
        )
        app_user = upsert_app_user(
            firebase_user.uid,
            demo_user["email"],
            demo_user["display_name"],
            demo_user["role"],
        )
        print(
            f"{demo_user['alias']}/{demo_user['password']} -> "
            f"{app_user['email']} ({app_user['role']}), active={app_user['is_active']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
