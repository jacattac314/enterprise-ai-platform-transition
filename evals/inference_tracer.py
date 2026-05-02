"""
InferenceTrace — captures per-request quality + latency signals.

Wired into the LLM gateway on every completion.  Traces are written to
a SQLite store for dashboard queries and SLO evaluation.
"""

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_DB = str(Path(__file__).parent.parent / "eval_traces.db")

_CREATE = """
CREATE TABLE IF NOT EXISTS inference_traces (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id                TEXT    NOT NULL UNIQUE,
    timestamp               TEXT    NOT NULL,
    model_id                TEXT    NOT NULL,
    task_type               TEXT    NOT NULL,
    ttft_ms                 REAL    NOT NULL DEFAULT 0,
    total_latency_ms        REAL    NOT NULL,
    tokens_per_second       REAL    NOT NULL DEFAULT 0,
    prompt_tokens           INTEGER NOT NULL DEFAULT 0,
    completion_tokens       INTEGER NOT NULL DEFAULT 0,
    security_overhead_ms    REAL    NOT NULL DEFAULT 0,
    self_consistency_score  REAL,
    grounding_score         REAL,
    judge_scores            TEXT,   -- JSON object or null
    hallucination_flagged   INTEGER NOT NULL DEFAULT 0,
    user_role               TEXT    NOT NULL DEFAULT '',
    session_id              TEXT    NOT NULL DEFAULT ''
);
"""

_INSERT = """
INSERT OR IGNORE INTO inference_traces (
    trace_id, timestamp, model_id, task_type,
    ttft_ms, total_latency_ms, tokens_per_second,
    prompt_tokens, completion_tokens, security_overhead_ms,
    self_consistency_score, grounding_score, judge_scores,
    hallucination_flagged, user_role, session_id
) VALUES (
    :trace_id, :timestamp, :model_id, :task_type,
    :ttft_ms, :total_latency_ms, :tokens_per_second,
    :prompt_tokens, :completion_tokens, :security_overhead_ms,
    :self_consistency_score, :grounding_score, :judge_scores,
    :hallucination_flagged, :user_role, :session_id
);
"""


@dataclass
class InferenceTrace:
    model_id: str
    task_type: str          # "generation" | "rag_query" | "tool_call" | "classification"
    total_latency_ms: float
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ttft_ms: float = 0.0
    tokens_per_second: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    security_overhead_ms: float = 0.0
    self_consistency_score: Optional[float] = None
    grounding_score: Optional[float] = None
    judge_scores: Optional[dict] = None
    hallucination_flagged: bool = False
    user_role: str = ""
    session_id: str = ""


class TraceStore:
    """Thread-safe SQLite store for inference traces."""

    def __init__(self, db_path: str = _DEFAULT_DB):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def record(self, trace: InferenceTrace) -> None:
        params = {**asdict(trace)}
        params["judge_scores"] = json.dumps(trace.judge_scores) if trace.judge_scores else None
        params["hallucination_flagged"] = int(trace.hallucination_flagged)
        with self._lock:
            with self._connect() as conn:
                conn.execute(_INSERT, params)

    def query_recent(self, limit: int = 100, model_id: str = None) -> list[dict]:
        where = "WHERE model_id = ?" if model_id else ""
        args = (model_id, limit) if model_id else (limit,)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM inference_traces {where} ORDER BY id DESC LIMIT ?", args
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def latency_percentiles(self, model_id: str = None, window_hours: int = 24) -> dict:
        """Return P50/P95/P99 for total_latency_ms over the given window."""
        where_parts = ["datetime(timestamp) >= datetime('now', ?)"  ]
        args = [f"-{window_hours} hours"]
        if model_id:
            where_parts.append("model_id = ?")
            args.append(model_id)
        where = "WHERE " + " AND ".join(where_parts)

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT total_latency_ms FROM inference_traces {where} ORDER BY total_latency_ms",
                args,
            ).fetchall()

        latencies = [r[0] for r in rows]
        if not latencies:
            return {"p50": None, "p95": None, "p99": None, "count": 0}

        n = len(latencies)
        return {
            "p50": latencies[int(n * 0.50)],
            "p95": latencies[int(n * 0.95)],
            "p99": latencies[int(n * 0.99)],
            "count": n,
        }

    def hallucination_rate(self, window_hours: int = 1) -> float:
        """Return fraction of flagged-hallucination traces in the window."""
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM inference_traces "
                "WHERE datetime(timestamp) >= datetime('now', ?)",
                (f"-{window_hours} hours",),
            ).fetchone()[0]
            flagged = conn.execute(
                "SELECT COUNT(*) FROM inference_traces "
                "WHERE hallucination_flagged = 1 "
                "AND datetime(timestamp) >= datetime('now', ?)",
                (f"-{window_hours} hours",),
            ).fetchone()[0]
        return flagged / total if total else 0.0

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM inference_traces").fetchone()[0]

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(_CREATE)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    if d.get("judge_scores"):
        d["judge_scores"] = json.loads(d["judge_scores"])
    d["hallucination_flagged"] = bool(d["hallucination_flagged"])
    return d
