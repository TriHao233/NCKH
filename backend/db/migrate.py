"""Apply versioned PostgreSQL schema files explicitly.

Usage from backend/: python -m db.migrate [--apply | --check]
The default is a read-only pending-migration listing.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from core.config import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def apply_migrations(connection, *, apply: bool = False, check: bool = False) -> list[str]:
    """Return pending filenames or apply them atomically, verifying checksums."""
    if apply and check:
        raise ValueError("Choose either apply or check")
    if apply:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )"""
        )
    else:
        table_exists = connection.execute(
            "SELECT to_regclass('public.schema_migrations') AS name"
        ).fetchone()["name"] is not None
        if not table_exists:
            pending = [path.name for path in migration_files()]
            if check and pending:
                raise RuntimeError(f"Pending PostgreSQL migrations: {', '.join(pending)}")
            return pending

    applied = {
        row["version"]: row["checksum"]
        for row in connection.execute("SELECT version, checksum FROM schema_migrations")
    }
    pending = []
    for path in migration_files():
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        old_checksum = applied.get(path.name)
        if old_checksum is not None:
            if old_checksum != checksum:
                raise RuntimeError(f"PostgreSQL migration changed after apply: {path.name}")
            continue
        pending.append(path.name)
        if apply:
            with connection.transaction():
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
                    (path.name, checksum),
                )
    if check and pending:
        raise RuntimeError(f"Pending PostgreSQL migrations: {', '.join(pending)}")
    return pending


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Apply pending migrations")
    group.add_argument("--check", action="store_true", help="Fail if migrations are pending")
    args = parser.parse_args()
    if not settings.postgres_dsn:
        parser.error("POSTGRES_DSN is required")
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(settings.postgres_dsn, row_factory=dict_row) as connection:
        pending = apply_migrations(connection, apply=args.apply, check=args.check)
    if args.apply:
        print(f"Applied {len(pending)} migration(s): {', '.join(pending) or 'none'}")
    else:
        print(f"Pending {len(pending)} migration(s): {', '.join(pending) or 'none'}")


if __name__ == "__main__":
    main()
