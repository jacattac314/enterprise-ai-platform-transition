"""
Smoke eval runner — referenced in model_rollback_sop.md §Step 3.

Usage:
    python evals/run_smoke_eval.py --n 5 --model qwen2.5:7b
    python evals/run_smoke_eval.py --n 10 --endpoint http://localhost:11434

Exits 0 if all selected golden examples pass, 1 if any fail.
Supports both Ollama (default) and OpenAI-compatible endpoints (vLLM).
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.jsonl"


def load_golden_set(n: int) -> list[dict]:
    examples = []
    with open(GOLDEN_SET_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples[:n]


def call_ollama(prompt: str, model: str, endpoint: str, timeout: int) -> str:
    resp = requests.post(
        f"{endpoint}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


def call_openai_compat(prompt: str, model: str, endpoint: str, timeout: int) -> str:
    resp = requests.post(
        f"{endpoint}/v1/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 256,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def evaluate_response(response: str, expected_contains: list[str]) -> bool:
    lowered = response.lower()
    return all(kw.lower() in lowered for kw in expected_contains)


def run_eval(
    n: int,
    model: str,
    endpoint: str,
    mode: str,
    timeout: int,
    verbose: bool,
) -> dict:
    if not _REQUESTS_AVAILABLE:
        print("ERROR: 'requests' package not installed. Run: pip install requests")
        sys.exit(1)

    examples = load_golden_set(n)
    results = []
    latencies = []

    print(f"\n{'='*60}")
    print(f"Smoke eval: {len(examples)} examples | model={model} | endpoint={endpoint}")
    print(f"{'='*60}")

    for ex in examples:
        t0 = time.monotonic()
        try:
            if mode == "openai":
                response = call_openai_compat(ex["prompt"], model, endpoint, timeout)
            else:
                response = call_ollama(ex["prompt"], model, endpoint, timeout)
            latency_ms = (time.monotonic() - t0) * 1000
            passed = evaluate_response(response, ex["expected_contains"])
        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000
            response = f"ERROR: {e}"
            passed = False

        latencies.append(latency_ms)
        results.append({**ex, "response": response[:200], "passed": passed, "latency_ms": latency_ms})

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {ex['id']} ({ex['category']}) — {latency_ms:.0f}ms")
        if verbose and not passed:
            print(f"         prompt:   {ex['prompt']}")
            print(f"         expected: {ex['expected_contains']}")
            print(f"         got:      {response[:200]}")

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    p95_ms = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    print(f"\nResult: {passed_count}/{total} passed | P95 latency: {p95_ms:.0f}ms")
    print(f"{'='*60}\n")

    return {
        "passed": passed_count,
        "total": total,
        "success": passed_count == total,
        "p95_latency_ms": p95_ms,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Smoke eval against a running inference endpoint")
    parser.add_argument("--n", type=int, default=5, help="Number of golden examples to run (default: 5)")
    parser.add_argument("--model", type=str, default="qwen2.5:7b", help="Model name")
    parser.add_argument("--endpoint", type=str, default="http://localhost:11434", help="Inference endpoint base URL")
    parser.add_argument("--mode", choices=["ollama", "openai"], default="ollama", help="API mode")
    parser.add_argument("--timeout", type=int, default=60, help="Per-request timeout in seconds")
    parser.add_argument("--verbose", action="store_true", help="Show full response on failure")
    parser.add_argument("--output", type=str, default=None, help="Write JSON results to file")
    args = parser.parse_args()

    summary = run_eval(
        n=args.n,
        model=args.model,
        endpoint=args.endpoint,
        mode=args.mode,
        timeout=args.timeout,
        verbose=args.verbose,
    )

    if args.output:
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Results written to {args.output}")

    sys.exit(0 if summary["success"] else 1)


if __name__ == "__main__":
    main()
