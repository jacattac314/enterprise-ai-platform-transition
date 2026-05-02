"""
CI step: check latency regression after an eval run.

Usage:
    python evals/check_latency.py --p95-ttft-max 1200 \
        --traces-db eval_traces.db

Exits 0 if within bounds, 1 if regression detected.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "evals"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--p95-ttft-max", type=float, default=1200,
                        help="Maximum allowed P95 latency in ms")
    parser.add_argument("--traces-db", default="eval_traces.db")
    parser.add_argument("--window-hours", type=int, default=24)
    args = parser.parse_args()

    from inference_tracer import TraceStore
    store = TraceStore(db_path=args.traces_db)
    percentiles = store.latency_percentiles(window_hours=args.window_hours)

    print(f"Latency percentiles ({args.window_hours}h window, n={percentiles['count']}):")
    print(f"  P50: {percentiles['p50']}ms")
    print(f"  P95: {percentiles['p95']}ms  (limit: {args.p95_ttft_max}ms)")
    print(f"  P99: {percentiles['p99']}ms")

    if percentiles["count"] == 0:
        print("No traces found — skipping latency check")
        sys.exit(0)

    p95 = percentiles["p95"]
    if p95 is not None and p95 > args.p95_ttft_max:
        print(f"FAIL: P95 {p95:.0f}ms > limit {args.p95_ttft_max:.0f}ms")
        sys.exit(1)

    print("PASS: latency within bounds")
    sys.exit(0)


if __name__ == "__main__":
    main()
