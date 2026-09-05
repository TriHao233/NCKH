"""Remove legacy Firebase bearer tokens from NCKH.User.

Dry-run is the default. Re-running --apply is safe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.database import get_auth_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    collection = get_auth_db()["User"]
    query = {"token": {"$type": "string", "$ne": ""}}
    count = collection.count_documents(query)
    print(f"legacy bearer records: {count}")
    if args.apply and count:
        result = collection.update_many(query, {"$set": {"token": None}})
        print(f"sanitized: {result.modified_count}")
    elif not args.apply:
        print("dry-run only; pass --apply to sanitize")


if __name__ == "__main__":
    main()
