import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from security.audit_logger import AuditLogger, AuditRecord


def _sample_record(**kwargs) -> AuditRecord:
    import uuid
    from datetime import datetime, timezone
    defaults = dict(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id="u1",
        user_role="ANALYST",
        session_id="sess_001",
        request_hash="abc123",
        redacted_prompt_hash="def456",
    )
    defaults.update(kwargs)
    return AuditRecord(**defaults)


@pytest.fixture
def logger(tmp_path):
    return AuditLogger(db_path=str(tmp_path / "test_audit.db"))


def test_log_and_count(logger):
    assert logger.count() == 0
    logger.log(_sample_record())
    assert logger.count() == 1


def test_log_multiple(logger):
    for _ in range(5):
        logger.log(_sample_record())
    assert logger.count() == 5


def test_query_requires_admin_role(logger):
    logger.log(_sample_record())
    with pytest.raises(PermissionError):
        logger.query(caller_role="ANALYST")
    with pytest.raises(PermissionError):
        logger.query(caller_role="DEVELOPER")


def test_query_allowed_for_platform_admin(logger):
    logger.log(_sample_record(user_role="ANALYST"))
    records = logger.query(caller_role="PLATFORM_ADMIN")
    assert len(records) == 1


def test_query_allowed_for_super_admin(logger):
    logger.log(_sample_record())
    records = logger.query(caller_role="SUPER_ADMIN")
    assert len(records) >= 1


def test_record_fields_persisted(logger):
    rec = _sample_record(
        user_id="user42",
        user_role="DEVELOPER",
        pii_tokens_present=["<PII_TOKEN_AABB>"],
        compliance_flags=["UNRESOLVED_PII_TOKENS"],
    )
    logger.log(rec)
    rows = logger.query("SUPER_ADMIN")
    assert rows[0]["user_id"] == "user42"
    assert rows[0]["user_role"] == "DEVELOPER"
    assert "<PII_TOKEN_AABB>" in rows[0]["pii_tokens_present"]
    assert "UNRESOLVED_PII_TOKENS" in rows[0]["compliance_flags"]


def test_append_only_duplicate_event_id_ignored(logger):
    rec = _sample_record()
    logger.log(rec)
    logger.log(rec)  # same event_id
    assert logger.count() == 1
