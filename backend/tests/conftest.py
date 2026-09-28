import pytest

from core.bootstrap import POSTGRES_OWNERS
from core.config import settings

# review_policy_store has no Mongo collection in POSTGRES_OWNERS, so add it explicitly.
STORE_FLAGS = sorted(set(POSTGRES_OWNERS.values()) | {"review_policy_store"})


@pytest.fixture(autouse=True)
def _mongo_store_defaults(monkeypatch):
    """Run each test on the MongoDB code path unless it opts into PostgreSQL.

    PostgreSQL is the application default, but MongoDB remains a supported
    rollback path and most unit tests exercise it with in-memory collections.
    PostgreSQL integration tests switch the flags they need inside the test.
    """
    for flag in STORE_FLAGS:
        monkeypatch.setattr(settings, flag, "mongo")
