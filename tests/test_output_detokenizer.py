import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from security.redis_token_store import PIITokenStore
from security.output_detokenizer import OutputDetokenizer


@pytest.fixture
def store_with_token():
    s = PIITokenStore()
    s._client = None
    s._mem = {}
    s.put(
        token="<PII_TOKEN_AABB1234>",
        value="jane@example.com",
        entity_type="EMAIL",
        session_id="sess_001",
    )
    return s


@pytest.fixture
def detokenizer(store_with_token):
    return OutputDetokenizer(store_with_token)


def test_pii_access_role_gets_original_value(detokenizer):
    text = "User email is <PII_TOKEN_AABB1234>."
    result, unresolved = detokenizer.detokenize(text, "PLATFORM_ADMIN")
    assert "jane@example.com" in result
    assert unresolved == []


def test_super_admin_also_gets_original_value(detokenizer):
    text = "User email is <PII_TOKEN_AABB1234>."
    result, _ = detokenizer.detokenize(text, "SUPER_ADMIN")
    assert "jane@example.com" in result


def test_analyst_does_not_see_original_value(detokenizer):
    text = "User email is <PII_TOKEN_AABB1234>."
    result, unresolved = detokenizer.detokenize(text, "ANALYST")
    assert "<PII_TOKEN_AABB1234>" in result
    assert "jane@example.com" not in result
    assert unresolved == []


def test_developer_does_not_see_original_value(detokenizer):
    text = "Contact <PII_TOKEN_AABB1234> for support."
    result, _ = detokenizer.detokenize(text, "DEVELOPER")
    assert "jane@example.com" not in result


def test_unresolved_token_reported(detokenizer):
    # DEADBEEF is valid hex but is not in the store — should be reported unresolved
    text = "Unknown token: <PII_TOKEN_DEADBEEF>."
    result, unresolved = detokenizer.detokenize(text, "PLATFORM_ADMIN")
    assert "<PII_TOKEN_DEADBEEF>" in result
    assert "<PII_TOKEN_DEADBEEF>" in unresolved


def test_no_tokens_passthrough(detokenizer):
    text = "No PII here, just a normal sentence."
    result, unresolved = detokenizer.detokenize(text, "SUPER_ADMIN")
    assert result == text
    assert unresolved == []
