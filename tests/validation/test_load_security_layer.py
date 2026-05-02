"""
Load test: P99 latency overhead of the security layer (PRD §8 Phase 3).

Measures wall-clock time for the pure security pipeline — PII detection,
role prompt injection, token storage write, and output detokenization —
excluding the LLM network call (which is runtime-environment-dependent).

Success criterion (PRD §2 G4): P99 ≤ 120 ms.
"""

import sys
import os
import statistics
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from security.pii_detector import PIIDetector
from security.redis_token_store import PIITokenStore
from security.role_prompts import build_system_prompt, SessionContext
from security.output_detokenizer import OutputDetokenizer

# Number of iterations for the load test
ITERATIONS = 500
P99_LIMIT_MS = 120.0

_SAMPLE_PROMPTS = [
    "What is the quarterly revenue for EMEA?",
    "Summarise the incident report for ticket INC-4821.",
    "Contact alice@example.com about the billing discrepancy.",
    "The SSN on file is 123-45-6789 — please verify.",
    "List all transactions over $10,000 for account holder Bob Smith.",
    "IP 192.168.10.5 was flagged in the SIEM — pull the context.",
]

_SAMPLE_RESPONSES = [
    "The answer to your question is: Here is the analysis.",
    "No PII found in this response.",
    "The email <PII_TOKEN_AABB1234> has been redacted per policy.",
]


@pytest.fixture(scope="module")
def pipeline():
    store = PIITokenStore()
    store._client = None
    store._mem = {}
    store.put(
        token="<PII_TOKEN_AABB1234>",
        value="alice@example.com",
        entity_type="EMAIL",
        session_id="sess_load",
    )
    return {
        "detector": PIIDetector(),
        "store": store,
        "detokenizer": OutputDetokenizer(store),
    }


def _measure_pipeline(pipeline, prompt: str, role: str = "ANALYST") -> float:
    """Returns wall-clock time in milliseconds for one pipeline pass."""
    t0 = time.perf_counter()

    # Step 1: PII redaction
    redacted, entities = pipeline["detector"].redact(prompt)

    # Step 2: Token storage writes
    for ent in entities:
        pipeline["store"].put(
            token=ent.token,
            value=ent.value,
            entity_type=ent.entity_type.value,
            session_id="sess_load",
        )

    # Step 3: Role-scoped system prompt build
    ctx = SessionContext(
        user_id="u_load",
        role=role,
        session_id="sess_load",
        approved_datasets=["ds_finance"],
        approved_tools=["search"],
    )
    _ = build_system_prompt(ctx)

    # Step 4: Output detokenization
    response = "The report for <PII_TOKEN_AABB1234> is attached."
    pipeline["detokenizer"].detokenize(response, "PLATFORM_ADMIN")

    return (time.perf_counter() - t0) * 1000  # ms


class TestSecurityLayerLatency:

    def test_p99_latency_under_limit(self, pipeline):
        """P99 of the full security pipeline must be ≤ 120 ms (PRD G4)."""
        import itertools
        prompt_cycle = itertools.cycle(_SAMPLE_PROMPTS)
        latencies = [
            _measure_pipeline(pipeline, next(prompt_cycle))
            for _ in range(ITERATIONS)
        ]

        p99 = sorted(latencies)[int(ITERATIONS * 0.99)]
        p50 = statistics.median(latencies)
        mean = statistics.mean(latencies)

        print(f"\nSecurity layer latency over {ITERATIONS} iterations:")
        print(f"  mean = {mean:.2f} ms")
        print(f"  p50  = {p50:.2f} ms")
        print(f"  p99  = {p99:.2f} ms  (limit: {P99_LIMIT_MS} ms)")

        assert p99 <= P99_LIMIT_MS, (
            f"P99 latency {p99:.2f} ms exceeds {P99_LIMIT_MS} ms SLA"
        )

    def test_p50_latency_reasonable(self, pipeline):
        """Median pipeline pass should be well under 20 ms."""
        import itertools
        prompt_cycle = itertools.cycle(_SAMPLE_PROMPTS)
        latencies = [
            _measure_pipeline(pipeline, next(prompt_cycle))
            for _ in range(200)
        ]
        p50 = statistics.median(latencies)
        assert p50 <= 20.0, f"Median latency {p50:.2f} ms is unexpectedly high"

    @pytest.mark.parametrize("role", ["ANALYST", "DEVELOPER", "PLATFORM_ADMIN"])
    def test_all_roles_within_limit(self, pipeline, role):
        """Security overhead must meet the SLA regardless of role."""
        latencies = [
            _measure_pipeline(pipeline, "Analyse the dataset for anomalies.", role)
            for _ in range(100)
        ]
        p99 = sorted(latencies)[int(100 * 0.99)]
        assert p99 <= P99_LIMIT_MS, (
            f"Role {role}: P99 {p99:.2f} ms > {P99_LIMIT_MS} ms"
        )

    def test_pii_heavy_prompt_within_limit(self, pipeline):
        """High-PII-density prompt must still process within SLA."""
        pii_prompt = (
            "Contact alice@corp.com and bob@corp.com. "
            "SSNs: 111-22-3333, 444-55-6666. "
            "IPs: 10.0.0.1, 192.168.1.1. Phone: 555-867-5309."
        )
        latencies = [
            _measure_pipeline(pipeline, pii_prompt)
            for _ in range(100)
        ]
        p99 = sorted(latencies)[int(100 * 0.99)]
        assert p99 <= P99_LIMIT_MS, (
            f"PII-heavy prompt P99 {p99:.2f} ms > {P99_LIMIT_MS} ms"
        )
