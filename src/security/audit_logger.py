"""
Append-only audit logger.

Writes every LLM interaction to a SQLite database opened in WAL mode.
No DELETE or UPDATE operations are ever issued — the table is insert-only,
mirroring the immutability guarantee of S3 Object Lock / Azure Immutable Blob.

In production, swap _write_record() for an S3/Azure SDK call; the
AuditRecord schema is intentionally identical to the PRD §7.1 JSON spec.
"""

import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

_DEFAULT_DB_PATH = os.environ.get(
    "AUDIT_LOG_DB", str(Path(__file__).parent.parent.parent / "audit_log.db")
)

# Roles permitted to read audit logs (PRD §7.2)
AUDIT_READ_ROLES = frozenset({"PLATFORM_ADMIN", "SUPER_ADMIN"})

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT    NOT NULL UNIQUE,
    timestamp     TEXT    NOT NULL,
    user_id       TEXT    NOT NULL,
    user_role     TEXT    NOT NULL,
    session_id    TEXT    NOT NULL,
    request_hash  TEXT    NOT NULL,
    redacted_prompt_hash TEXT NOT NULL,
    pii_tokens_present   TEXT NOT NULL,   -- JSON array
    model_id      TEXT    NOT NULL DEFAULT '',
    tool_calls    TEXT    NOT NULL DEFAULT '[]',
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    response_hash TEXT    NOT NULL DEFAULT '',
    compliance_flags     TEXT NOT NULL DEFAULT '[]'
);
"""

_INSERT = """
INSERT OR IGNORE INTO audit_log (
    event_id, timestamp, user_id, user_role, session_id,
    request_hash, redacted_prompt_hash, pii_tokens_present,
    model_id, tool_calls, completion_tokens, latency_ms,
    response_hash, compliance_flags
) VALUES (
    :event_id, :timestamp, :user_id, :user_role, :session_id,
    :request_hash, :redacted_prompt_hash, :pii_tokens_present,
    :model_id, :tool_calls, :completion_tokens, :latency_ms,
    :response_hash, :compliance_flags
);
"""


@dataclass
class AuditRecord:
    event_id: str
    timestamp: str
    user_id: str
    user_role: str
    session_id: str
    request_hash: str
    redacted_prompt_hash: str
    pii_tokens_present: list[str] = field(default_factory=list)
    model_id: str = ""
    tool_calls: list[str] = field(default_factory=list)
    completion_tokens: int = 0
    latency_ms: int = 0
    response_hash: str = ""
    compliance_flags: list[str] = field(default_factory=list)


class AuditLogger:
    """
    Thread-safe, append-only SQLite audit logger.

    One instance per process is sufficient; it uses a connection-per-write
    strategy to avoid cross-thread SQLite issues without a connection pool.
    """

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, record: AuditRecord) -> None:
        """Append an audit record. Never raises — logs errors to stderr."""
        try:
            self._write_record(record)
        except Exception as exc:
            import sys
            print(f"[AuditLogger] WRITE FAILED: {exc}", file=sys.stderr)

    def query(self, caller_role: str, limit: int = 100, offset: int = 0) -> list[dict]:
        """Return recent records. Only PLATFORM_ADMIN / SUPER_ADMIN may call."""
        if caller_role not in AUDIT_READ_ROLES:
            raise PermissionError(
                f"Role {caller_role!r} is not permitted to read audit logs."
            )
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    def _write_record(self, record: AuditRecord) -> None:
        params = {
            **asdict(record),
            "pii_tokens_present": json.dumps(record.pii_tokens_present),
            "tool_calls": json.dumps(record.tool_calls),
            "compliance_flags": json.dumps(record.compliance_flags),
        }
        with self._lock:
            with self._connect() as conn:
                conn.execute(_INSERT, params)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("pii_tokens_present", "tool_calls", "compliance_flags"):
        d[key] = json.loads(d[key])
    return d
