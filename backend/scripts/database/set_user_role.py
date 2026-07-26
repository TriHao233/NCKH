"""Set an existing synced application user's role for demo/admin setup."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from pymongo import ReturnDocument

from core.database import get_rag_db, ping_database
from modules.users.schemas import RoleEnum


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update role/is_active for a user already synced into rag_database.users. "
            "This does not create a Firebase account."
        )
    )
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--email", help="Application user email.")
    identity.add_argument("--firebase-uid", help="Firebase UID.")
    parser.add_argument(
        "--role",
        required=True,
        choices=[role.value for role in RoleEnum],
        help="Target application role.",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="Also set is_active=false. By default the user is activated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ping_database()
    db = get_rag_db()
    query = (
        {"email": args.email.lower()}
        if args.email
        else {"firebase_uid": args.firebase_uid}
    )
    now = datetime.now(timezone.utc)
    user = db.users.find_one_and_update(
        query,
        {
            "$set": {
                "role": args.role,
                "is_active": not args.inactive,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    if not user:
        target = args.email or args.firebase_uid
        print(f"User not found: {target}")
        print("Hint: sign in once first so /auth/login syncs the Firebase user.")
        return 1

    print(
        "Updated user role: "
        f"{user.get('email')} ({user.get('firebase_uid')}) -> "
        f"{user.get('role')}, active={user.get('is_active')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
