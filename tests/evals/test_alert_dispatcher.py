import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "evals"))

import pytest
from inference_tracer import InferenceTrace, TraceStore
from alerts.alert_dispatcher import evaluate_alerts, Alert, Severity


@pytest.fixture
def store(tmp_path):
    return TraceStore(db_path=str(tmp_path / "traces.db"))


def _trace(flagged=False, latency_ms=500.0):
    return InferenceTrace(
        model_id="test-model",
        task_type="generation",
        total_latency_ms=latency_ms,
        hallucination_flagged=flagged,
    )


_SLO = {
    "quality_slos": {"hallucination_rate_max": 0.05},
    "latency_slos": {"default": {"ttft_p95_ms": 1200, "total_p95_ms": 8000}},
}


def test_no_alerts_when_all_clean(store):
    for _ in range(20):
        store.record(_trace(flagged=False, latency_ms=400.0))
    alerts = evaluate_alerts(store, slo_config=_SLO)
    assert alerts == []


def test_hallucination_alert_fires(store):
    for _ in range(4):
        store.record(_trace(flagged=True))
    for _ in range(6):
        store.record(_trace(flagged=False))
    # 40% hallucination → exceeds 5% threshold
    alerts = evaluate_alerts(store, slo_config=_SLO)
    assert any(a.condition == "hallucination_spike" for a in alerts)


def test_hallucination_alert_severity_high(store):
    for _ in range(3):
        store.record(_trace(flagged=True))
    for _ in range(7):
        store.record(_trace(flagged=False))
    alerts = evaluate_alerts(store, slo_config=_SLO)
    halluc_alerts = [a for a in alerts if a.condition == "hallucination_spike"]
    assert all(a.severity == Severity.HIGH for a in halluc_alerts)


def test_latency_alert_fires(store):
    for _ in range(20):
        store.record(_trace(latency_ms=2000.0))
    alerts = evaluate_alerts(store, slo_config=_SLO)
    assert any(a.condition == "latency_regression" for a in alerts)


def test_no_latency_alert_within_slo(store):
    for _ in range(20):
        store.record(_trace(latency_ms=800.0))
    alerts = evaluate_alerts(store, slo_config=_SLO)
    assert not any(a.condition == "latency_regression" for a in alerts)


def test_dispatch_no_op_without_webhook(store):
    from alerts.alert_dispatcher import dispatch_to_slack
    alerts = [Alert("test", Severity.HIGH, 0.1, 0.05, "test alert")]
    result = dispatch_to_slack(alerts, webhook_url="")
    assert result == 0
