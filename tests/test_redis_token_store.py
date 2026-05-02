import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from security.redis_token_store import PIITokenStore


@pytest.fixture
def store():
    # In-process store (no Redis required)
    s = PIITokenStore()
    s._client = None  # force in-process fallback
    s._mem = {}
    return s


def test_put_and_get(store):
    store.put(
        token="<PII_TOKEN_AABB>",
        value="secret@example.com",
        entity_type="EMAIL",
        session_id="sess_001",
    )
    record = store.get("<PII_TOKEN_AABB>")
    assert record is not None
    assert record["value"] == "secret@example.com"
    assert record["type"] == "EMAIL"
    assert record["session_id"] == "sess_001"


def test_write_once_semantics(store):
    store.put(
        token="<PII_TOKEN_CCDD>",
        value="first@example.com",
        entity_type="EMAIL",
        session_id="sess_001",
    )
    store.put(
        token="<PII_TOKEN_CCDD>",
        value="second@example.com",
        entity_type="EMAIL",
        session_id="sess_001",
    )
    record = store.get("<PII_TOKEN_CCDD>")
    assert record["value"] == "first@example.com"


def test_missing_token_returns_none(store):
    assert store.get("<PII_TOKEN_NONEXISTENT>") is None


def test_ping_returns_true_for_in_process_store(store):
    assert store.ping() is True
