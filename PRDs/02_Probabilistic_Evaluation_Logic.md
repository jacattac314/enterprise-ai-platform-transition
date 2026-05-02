# PRD 02: Probabilistic Evaluation Logic — Hallucination & Latency Monitoring Framework
**Version:** 1.0  
**Status:** Draft — Ready for Engineering Review  
**Owner:** AI Platform Team  
**Last Updated:** 2025-05

---

## 1. Problem Statement

Deterministic software fails in predictable, testable ways. LLMs fail probabilistically — and often silently. A response can be fluent, confident, and completely wrong. Without a structured eval harness, there is no defensible way to:

- Know whether model performance has degraded after an update
- Compare two models on production workload characteristics
- Detect hallucination before it surfaces in user-facing output
- Set data-driven SLOs for AI-powered features

This PRD specifies the evaluation framework that makes LLM outputs **auditable, comparable, and continuously measured** across the platform.

---

## 2. Goals

| # | Goal | Success Metric |
|---|------|----------------|
| G1 | Quantify hallucination rate per model/task type | Hallucination rate measured on weekly basis |
| G2 | Track latency distributions across inference targets | P50/P95/P99 dashboarded per model |
| G3 | Automated regression detection on model updates | Alert fires when hallucination rate increases >15% |
| G4 | Enable A/B eval between model versions | Side-by-side scores on standardized eval set |

---

## 3. Evaluation Dimensions

### 3.1 Dimension Map

```
LLM Output Quality
├── Factual Accuracy (hallucination detection)
│   ├── Grounded claims (verifiable against source)
│   └── Ungrounded claims (model-generated, not in context)
│
├── Task Completion
│   ├── Instruction following (did it do what was asked?)
│   └── Format compliance (JSON, markdown, schema adherence)
│
├── Latency
│   ├── Time to first token (TTFT)
│   └── Total generation time
│
└── Safety & Compliance
    ├── PII leakage in output
    └── Policy violations
```

---

## 4. Hallucination Detection Architecture

### 4.1 Three-Layer Detection

**Layer 1 — Self-Consistency Check (Fast)**  
Run the same prompt 3x with temperature > 0. Measure semantic similarity of responses using cosine similarity on sentence embeddings. High variance = high hallucination risk.

```python
def self_consistency_score(responses: list[str]) -> float:
    """
    Returns 0.0 (max hallucination risk) to 1.0 (fully consistent).
    """
    embeddings = embed_sentences(responses)  # sentence-transformers
    pairwise_similarities = cosine_similarity(embeddings)
    # Average upper triangle (unique pairs)
    return float(np.mean(pairwise_similarities[np.triu_indices_from(
        pairwise_similarities, k=1
    )]))
```

**Layer 2 — Grounding Check (Medium)**  
For RAG-based responses: extract claims from the response, check each claim against the retrieved context chunks. Flag claims not traceable to source.

```python
CLAIM_EXTRACTION_PROMPT = """
Extract all factual claims from the following response as a JSON list.
Each claim should be a single, atomic statement.
Response: {response}
Return ONLY valid JSON: ["claim1", "claim2", ...]
"""

GROUNDING_CHECK_PROMPT = """
Given this source context:
{context}

Is the following claim directly supported by the context? Answer YES or NO.
Claim: {claim}
"""
```

**Layer 3 — LLM-as-Judge (Slow, High Confidence)**  
Use a separate judge model (GPT-4o or Claude Opus) to evaluate response quality on a 1–5 rubric. Reserved for sampled traffic and eval runs — not real-time.

```python
JUDGE_RUBRIC = """
Evaluate this AI response on the following dimensions. Score each 1-5.

Response: {response}
Reference (if available): {reference}

Dimensions:
1. Factual Accuracy: Is everything stated verifiable and correct?
2. Completeness: Does it fully address the question?
3. Hallucination: Are there invented facts not in the context?
4. Instruction Following: Did it follow the format/task specified?

Return ONLY valid JSON: {"factual_accuracy": N, "completeness": N, "hallucination": N, "instruction_following": N, "notes": "..."}
"""
```

---

## 5. Latency Monitoring

### 5.1 Metrics to Capture

| Metric | Definition | Target |
|--------|------------|--------|
| `ttft_ms` | Time to first token (streaming) | P95 < 1200ms |
| `total_latency_ms` | Full response generation | P95 < 8000ms |
| `tokens_per_second` | Throughput during generation | > 20 tok/s |
| `queue_wait_ms` | Time waiting before inference starts | P99 < 500ms |
| `security_overhead_ms` | Latency added by PII + RBAC layer | P99 < 120ms |

### 5.2 Instrumentation

```python
from dataclasses import dataclass
from time import perf_counter

@dataclass
class InferenceTrace:
    request_id: str
    model_id: str
    task_type: str  # "rag", "tool_call", "generation", "classification"
    ttft_ms: float
    total_latency_ms: float
    tokens_per_second: float
    prompt_tokens: int
    completion_tokens: int
    security_overhead_ms: float
    self_consistency_score: float | None
    grounding_score: float | None
    judge_scores: dict | None
    timestamp: str
```

### 5.3 Percentile Buckets for Alerting

```yaml
# eval_slo_config.yaml
latency_slos:
  default:
    ttft_p95_ms: 1200
    total_p95_ms: 8000
  tool_call:
    ttft_p95_ms: 800
    total_p95_ms: 5000
  rag_query:
    ttft_p95_ms: 1500
    total_p95_ms: 12000

quality_slos:
  hallucination_rate_max: 0.05   # 5% of sampled responses
  self_consistency_min: 0.80
  grounding_score_min: 0.85
```

---

## 6. Eval Dataset Management

### 6.1 Dataset Types

| Dataset | Purpose | Size | Update Cadence |
|---------|---------|------|----------------|
| Golden Set | Regression testing — static reference answers | 200–500 examples | Quarterly |
| Adversarial Set | Edge cases, known failure modes | 50–100 examples | Monthly |
| Production Sample | Random 2% of live traffic (no PII) | Dynamic | Continuous |

### 6.2 Example Schema — Golden Set Record

```json
{
  "id": "gs_001",
  "task_type": "rag_query",
  "prompt": "What was the Q3 revenue growth rate for the APAC region?",
  "context_chunks": ["...relevant retrieved text..."],
  "reference_answer": "The APAC region grew 14.3% in Q3, driven by...",
  "acceptable_range": {
    "min_score": 4,
    "required_facts": ["14.3%", "APAC", "Q3"]
  },
  "tags": ["finance", "rag", "numerical"]
}
```

---

## 7. Dashboard & Alerting

### 7.1 Core Dashboard Panels

1. **Hallucination Rate Trend** — 7-day rolling, by model + task type
2. **Latency Percentiles** — P50/P95/P99 per inference target
3. **Self-Consistency Distribution** — Histogram of consistency scores
4. **Grounding Score Heatmap** — By document type + query category
5. **Model Comparison View** — Side-by-side on standardized eval set
6. **SLO Burn Rate** — Error budget remaining for quality and latency SLOs

### 7.2 Alert Conditions

| Alert | Threshold | Channel | Severity |
|-------|-----------|---------|----------|
| Hallucination spike | Rate > 5% over 1hr window | Slack #ai-ops | HIGH |
| Latency regression | P95 TTFT > 150% of 7-day avg | PagerDuty | HIGH |
| Grounding drop | Score drops >15% day-over-day | Slack #ai-ops | MEDIUM |
| Low self-consistency | Score < 0.70 for >20 consecutive calls | Slack #ai-ops | MEDIUM |
| Eval run failure | CI eval job fails on golden set | Slack #ai-eng | HIGH |

---

## 8. CI/CD Eval Gate

Every model update must pass eval gate before production promotion:

```yaml
# .github/workflows/model_eval_gate.yml
name: Model Eval Gate
on:
  push:
    paths:
      - 'models/**'
      - 'prompts/**'

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - name: Run Golden Set Eval
        run: python evals/run_golden_set.py --model ${{ env.MODEL_ID }}
      
      - name: Check Hallucination Threshold
        run: python evals/check_thresholds.py --max-hallucination 0.05
      
      - name: Check Latency Regression
        run: python evals/check_latency.py --p95-ttft-max 1200
      
      - name: Fail on Regression
        if: failure()
        run: echo "Eval gate FAILED. Model promotion blocked." && exit 1
```

---

## 9. Implementation Plan

### Phase 1 — Instrumentation (Week 1–2)
- [ ] Add `InferenceTrace` capture to LLM gateway
- [ ] Ship traces to structured log store (SQLite → dashboard)
- [ ] Implement self-consistency check for sampled traffic (5%)

### Phase 2 — Grounding & Judge (Week 3–4)
- [ ] Build claim extraction pipeline
- [ ] Integrate grounding check for all RAG endpoints
- [ ] Set up LLM-as-judge for weekly eval runs

### Phase 3 — Dashboard & Alerts (Week 5–6)
- [ ] Build eval dashboard (latency + quality panels)
- [ ] Wire alert conditions to Slack
- [ ] Integrate eval gate into CI/CD pipeline

### Phase 4 — Golden Set (Week 7)
- [ ] Curate 200-example golden set from production samples
- [ ] Establish baseline scores per model/task type
- [ ] Document SLO targets in runbook

---

## 10. Open Questions

| # | Question | Owner |
|---|----------|-------|
| OQ1 | Should judge model be the same family as production model? (conflict of interest) | ML Lead |
| OQ2 | What's the budget for LLM-as-judge API calls per week? | Platform |
| OQ3 | Do adversarial examples get shared across teams or siloed? | Security |
