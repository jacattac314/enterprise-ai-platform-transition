import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from security.jwt_middleware import (
    VALID_ROLES,
    _extract_bearer_token,
    _decode_token,
)
from unittest.mock import MagicMock


def _make_request(auth_header: str = ""):
    req = MagicMock()
    req.headers = {"Authorization": auth_header} if auth_header else {}
    return req


def test_valid_roles_set():
    assert "ANALYST" in VALID_ROLES
    assert "DEVELOPER" in VALID_ROLES
    assert "PLATFORM_ADMIN" in VALID_ROLES
    assert "SUPER_ADMIN" in VALID_ROLES
    assert "VIEWER" in VALID_ROLES


def test_extract_bearer_token_valid():
    req = _make_request("Bearer mytoken123")
    assert _extract_bearer_token(req) == "mytoken123"


def test_extract_bearer_token_missing():
    req = _make_request()
    assert _extract_bearer_token(req) is None


def test_extract_bearer_token_wrong_scheme():
    req = _make_request("Basic dXNlcjpwYXNz")
    assert _extract_bearer_token(req) is None


def test_decode_token_returns_none_without_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "")
    import security.jwt_middleware as m
    m._JWT_SECRET = ""
    # Should raise RuntimeError when secret is blank
    with pytest.raises(RuntimeError):
        _decode_token("some.fake.token")
