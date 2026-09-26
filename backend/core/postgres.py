"""PostgreSQL connection lifecycle for business repositories.

The pool stays closed until a PostgreSQL-backed repository is selected. This
keeps the existing MongoDB application usable during the staged migration.
"""

from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from typing import Iterator

from core.config import settings

_pool = None
_pool_lock = Lock()


def get_postgres_pool():
    global _pool
    if _pool is not None:
        return _pool
    if not settings.postgres_dsn:
        raise RuntimeError("POSTGRES_DSN is required for PostgreSQL repositories")
    with _pool_lock:
        if _pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            if settings.postgres_pool_min_size < 1:
                raise ValueError("POSTGRES_POOL_MIN_SIZE must be at least 1")
            if settings.postgres_pool_max_size < settings.postgres_pool_min_size:
                raise ValueError("POSTGRES_POOL_MAX_SIZE must be >= POSTGRES_POOL_MIN_SIZE")
            pool = ConnectionPool(
                conninfo=settings.postgres_dsn,
                min_size=settings.postgres_pool_min_size,
                max_size=settings.postgres_pool_max_size,
                kwargs={"row_factory": dict_row},
                open=False,
            )
            pool.open(wait=True)
            _pool = pool
    return _pool


@contextmanager
def postgres_connection() -> Iterator:
    """Borrow a connection; successful writes commit on context exit."""
    with get_postgres_pool().connection() as connection:
        yield connection


def ping_postgres() -> None:
    with postgres_connection() as connection:
        connection.execute("SELECT 1")


def close_postgres() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None
