"""Create V2 collections, validators, indexes and reference data."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from core.bootstrap import SCHEMA_VERSION, bootstrap_database
from core.config import settings
from core.database import ping_database


def main() -> int:
    ping_database()
    bootstrap_database()
    print(f"Database '{settings.db_name}' is ready at schema version {SCHEMA_VERSION}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
