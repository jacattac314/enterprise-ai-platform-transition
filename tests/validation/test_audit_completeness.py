"""
Validation: G3 — 100% of completions logged with user + role + timestamp.

Verifies that the AuditLogger captures every required field from PRD §7.1
and that no record can be omitted or altered after the fact.
"""

import sys
import os
import hashlib
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from security.audit_logger import AuditLogger, AuditRecord, AUDIT_READ_ROLES


def _record(**overrides) -> AuditRecord:
    defaults = dict(
        event_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        user_id="u_validation",
        user_role="ANALYST",
        session_id="sess_g3",
        request_hash=hashlib.sha256(b"raw_prompt").hexdigest(),
        redacted_prompt_hash=hashlib.sha256(b"redacted").hexdigest(),
    )
    defaults.update(overrides)
    return AuditRecord(**defaults)


@pytest.fixture
def logger(tmp_path):
    return AuditLogger(db_path=str(tmp_path / "audit_g3.db"))


class TestAuditCompleteness:
    """Every LLM interaction is logged with the required PRD §7.1 fields."""

    def test_audit_record_contains_all_prd_required_fields(self, logger):
        rec = _record(
            pii_tokens_present=["<PII_TOKEN_AABB1234>"],
            model_id="claude-sonnet-4-6",
            tool_calls=["search_tool"],
            completion_tokens=42,
            latency_ms=88,
            response_hash=hashlib.sha256(b"response").hexdigest(),
            compliance_flags=[],
        )
        logger.log(rec)
        rows = logger.query("SUPER_ADMIN")
        assert len(rows) == 1
        row = rows[0]
        # PRD §7.1 mandatory fields
        assert row["event_id"] == rec.event_id
        assert row["timestamp"]
        assert row["user_id"] == "u_validation"
        assert row["user_role"] == "ANALYST"
        assert row["session_id"] == "sess_g3"
        assert row["request_hash"]
        assert row["redacted_prompt_hash"]
        assert "<PII_TOKEN_AABB1234>" in row["pii_tokens_present"]
        assert row["model_id"] == "claude-sonnet-4-6"
        assert "search_tool" in row["tool_calls"]
        assert row["completion_tokens"] == 42
        assert row["latency_ms"] == 88
        assert row["response_hash"]

    def test_every_role_interaction_is_logged(self, logger):
        roles = ["ANALYST", "DEVELOPER", "PLATFORM_ADMIN", "SUPER_ADMIN"]
        for role in roles:
            logger.log(_record(event_id=str(uuid.uuid4()), user_role=role))
        assert logger.count() == len(roles)

    def test_no_record_dropped_under_concurrent_load(self, logger):
        import threading
        n = 50
        errors = []

        def _log():
            try:
                logger.log(_record())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_log) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Concurrent log errors: {errors}"
        assert logger.count() == n

    def test_audit_log_append_only_no_update(self, logger):
        rec = _record(latency_ms=10)
        logger.log(rec)
        # Attempt to overwrite via duplicate event_id (should be silently ignored)
        modified = _record(event_id=rec.event_id, latency_ms=9999)
        logger.log(modified)
        rows = logger.query("SUPER_ADMIN")
        assert rows[0]["latency_ms"] == 10  # original value preserved

    def test_audit_read_access_restricted_to_admin_roles(self, logger):
        for role in ["VIEWER", "ANALYST", "DEVELOPER"]:
            with pytest.raises(PermissionError):
                logger.query(role)
        for role in AUDIT_READ_ROLES:
            logger.query(role)  # must not raise

    def test_pii_tokens_stored_in_audit_record(self, logger):
        tokens = ["<PII_TOKEN_AABB1234>", "<PII_TOKEN_CAFE5678>"]
        logger.log(_record(pii_tokens_present=tokens))
        rows = logger.query("PLATFORM_ADMIN")
        stored_tokens = rows[0]["pii_tokens_present"]
        for t in tokens:
            assert t in stored_tokens

    def test_compliance_flags_persisted(self, logger):
        logger.log(_record(compliance_flags=["UNRESOLVED_PII_TOKENS"]))
        rows = logger.query("SUPER_ADMIN")
        assert "UNRESOLVED_PII_TOKENS" in rows[0]["compliance_flags"]
