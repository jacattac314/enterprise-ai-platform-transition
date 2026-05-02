import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "evals"))

import pytest
from inference_tracer import InferenceTrace, TraceStore


@pytest.fixture
def store(tmp_path):
    return TraceStore(db_path=str(tmp_path / "traces.db"))


def _trace(**kw) -> InferenceTrace:
    defaults = dict(model_id="test-model", task_type="generation", total_latency_ms=500.0)
    defaults.update(kw)
    return InferenceTrace(**defaults)


def test_record_and_count(store):
    store.record(_trace())
    assert store.count() == 1


def test_query_recent(store):
    store.record(_trace(model_id="m1"))
    store.record(_trace(model_id="m2"))
    rows = store.query_recent(limit=10)
    assert len(rows) == 2


def test_query_recent_filter_by_model(store):
    store.record(_trace(model_id="m1"))
    store.record(_trace(model_id="m2"))
    rows = store.query_recent(model_id="m1")
    assert all(r["model_id"] == "m1" for r in rows)


def test_latency_percentiles(store):
    for ms in [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]:
        store.record(_trace(total_latency_ms=float(ms)))
    p = store.latency_percentiles()
    assert p["p50"] is not None
    assert p["p95"] is not None
    assert p["count"] == 10


def test_hallucination_rate_zero(store):
    store.record(_trace(hallucination_flagged=False))
    store.record(_trace(hallucination_flagged=False))
    assert store.hallucination_rate() == 0.0


def test_hallucination_rate_nonzero(store):
    store.record(_trace(hallucination_flagged=True))
    store.record(_trace(hallucination_flagged=False))
    store.record(_trace(hallucination_flagged=False))
    store.record(_trace(hallucination_flagged=False))
    rate = store.hallucination_rate()
    assert abs(rate - 0.25) < 0.01


def test_judge_scores_persisted(store):
    store.record(_trace(judge_scores={"factual_accuracy": 4, "hallucination": 5}))
    rows = store.query_recent()
    assert rows[0]["judge_scores"]["hallucination"] == 5


def test_duplicate_trace_id_ignored(store):
    t = _trace()
    store.record(t)
    store.record(t)
    assert store.count() == 1
