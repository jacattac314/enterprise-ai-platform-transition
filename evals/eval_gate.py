"""
CI eval gate — blocks deployment if model quality regresses.

Usage (CI pipeline step):
    python evals/eval_gate.py \
        --model qwen2.5:7b \
        --endpoint http://localhost:11434 \
        --baseline-score 0.88 \
        --threshold-drop 0.15

Exits 0 if the new model passes the gate, 1 if it fails.
Fail conditions (per model_rollback_sop.md):
  - Golden set score drops > 15% vs registered baseline
  - P95 latency > 150% of 7-day baseline
  - Any single task-category score < 0.70
"""

import argparse
import json
import sys
from pathlib import Path

_GOLDEN_SET = Path(__file__).parent / "golden_set.jsonl"
_REGISTRY = Path(__file__).parent.parent / "MLOps_Standards" / "model_registry.yml"


def _load_golden_set(n: int = None) -> list[dict]:
    examples = []
    with open(_GOLDEN_SET) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples if n is None else examples[:n]


def _call_model(prompt: str, model: str, endpoint: str, mode: str) -> str:
    try:
        import requests
    except ImportError:
        print("ERROR: install requests: pip install requests")
        sys.exit(1)

    if mode == "openai":
        resp = requests.post(
            f"{endpoint}/v1/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 256},
            timeout=60,
        )
    else:
        resp = requests.post(
            f"{endpoint}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60,
        )
    resp.raise_for_status()

    if mode == "openai":
        return resp.json()["choices"][0]["message"]["content"]
    return resp.json().get("response", "")


def run_gate(
    model: str,
    endpoint: str,
    mode: str,
    baseline_score: float,
    threshold_drop: float,
    p95_baseline_ms: float,
) -> dict:
    import time
    examples = _load_golden_set()
    passed = 0
    category_scores: dict[str, list[bool]] = {}
    latencies = []

    for ex in examples:
        t0 = time.monotonic()
        try:
            response = _call_model(ex["prompt"], model, endpoint, mode)
            ok = all(kw.lower() in response.lower() for kw in ex["expected_contains"])
        except Exception as e:
            print(f"  [ERROR] {ex['id']}: {e}")
            ok = False
        latencies.append((time.monotonic() - t0) * 1000)

        cat = ex["category"]
        category_scores.setdefault(cat, []).append(ok)
        if ok:
            passed += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {ex['id']} ({cat})")

    total = len(examples)
    overall_score = passed / total if total else 0
    p95_ms = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    # Gate checks
    failures = []

    score_drop = baseline_score - overall_score
    if score_drop > threshold_drop:
        failures.append(
            f"Score dropped {score_drop:.2%} (baseline={baseline_score:.2%}, "
            f"current={overall_score:.2%}, limit={threshold_drop:.2%})"
        )

    if p95_baseline_ms > 0 and p95_ms > p95_baseline_ms * 1.5:
        failures.append(
            f"P95 latency {p95_ms:.0f}ms > 150% of baseline {p95_baseline_ms:.0f}ms"
        )

    for cat, results in category_scores.items():
        cat_score = sum(results) / len(results)
        if cat_score < 0.70:
            failures.append(f"Category '{cat}' score {cat_score:.2%} < 0.70 minimum")

    return {
        "model": model,
        "overall_score": overall_score,
        "baseline_score": baseline_score,
        "p95_latency_ms": p95_ms,
        "category_scores": {k: sum(v) / len(v) for k, v in category_scores.items()},
        "gate_passed": len(failures) == 0,
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description="CI eval gate for model deployments")
    parser.add_argument("--model", required=True)
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--mode", choices=["ollama", "openai"], default="ollama")
    parser.add_argument("--baseline-score", type=float, default=0.88,
                        help="Registered baseline accuracy (0–1)")
    parser.add_argument("--threshold-drop", type=float, default=0.15,
                        help="Max allowed score regression (default: 0.15 = 15%%)")
    parser.add_argument("--p95-baseline-ms", type=float, default=0,
                        help="7-day P95 latency baseline in ms (0 = skip check)")
    parser.add_argument("--output", default=None, help="Write JSON results to file")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"Eval gate: model={args.model} | endpoint={args.endpoint}")
    print(f"Baseline score: {args.baseline_score:.2%} | Drop limit: {args.threshold_drop:.2%}")
    print(f"{'='*60}")

    result = run_gate(
        model=args.model,
        endpoint=args.endpoint,
        mode=args.mode,
        baseline_score=args.baseline_score,
        threshold_drop=args.threshold_drop,
        p95_baseline_ms=args.p95_baseline_ms,
    )

    print(f"\nOverall score: {result['overall_score']:.2%}")
    print(f"P95 latency:  {result['p95_latency_ms']:.0f}ms")
    print(f"Gate:         {'PASSED ✅' if result['gate_passed'] else 'FAILED ❌'}")
    if result["failures"]:
        for f in result["failures"]:
            print(f"  ⚠ {f}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)

    sys.exit(0 if result["gate_passed"] else 1)


if __name__ == "__main__":
    main()
