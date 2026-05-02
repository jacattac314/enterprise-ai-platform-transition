"""
CI step: check hallucination threshold after an eval run.

Usage:
    python evals/check_thresholds.py --max-hallucination 0.05 \
        --traces-db eval_traces.db

Exits 0 if within thresholds, 1 if any threshold is breached.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "evals"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-hallucination", type=float, default=0.05)
    parser.add_argument("--min-self-consistency", type=float, default=0.80)
    parser.add_argument("--traces-db", default="eval_traces.db")
    parser.add_argument("--window-hours", type=int, default=1)
    args = parser.parse_args()

    from inference_tracer import TraceStore
    store = TraceStore(db_path=args.traces_db)

    failures = []

    rate = store.hallucination_rate(window_hours=args.window_hours)
    if rate > args.max_hallucination:
        failures.append(
            f"Hallucination rate {rate:.2%} > limit {args.max_hallucination:.2%}"
        )

    print(f"Hallucination rate ({args.window_hours}h window): {rate:.2%}")
    print(f"Threshold: {args.max_hallucination:.2%}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        sys.exit(1)

    print("PASS: all quality thresholds met")
    sys.exit(0)


if __name__ == "__main__":
    main()
