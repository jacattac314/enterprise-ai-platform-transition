"""
Alert dispatcher — evaluates SLO conditions and fires alerts.

Checks the TraceStore against SLO thresholds (from eval_slo_config.yaml)
and dispatches to Slack when conditions are breached.  Designed to run
on a scheduled basis (cron / n8n trigger) rather than per-request.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

_SLO_CONFIG_PATH = Path(__file__).parent.parent / "eval_slo_config.yaml"
_SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Alert:
    condition: str
    severity: Severity
    value: float
    threshold: float
    message: str
    fired_at: str = ""

    def __post_init__(self):
        self.fired_at = datetime.now(timezone.utc).isoformat()


def load_slo_config(path: str = str(_SLO_CONFIG_PATH)) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def evaluate_alerts(store, slo_config: dict = None) -> list[Alert]:
    """
    Check all SLO conditions against the trace store.
    Returns a list of fired Alert objects (empty if all within bounds).
    """
    if slo_config is None:
        slo_config = load_slo_config()

    alerts: list[Alert] = []
    quality = slo_config.get("quality_slos", {})
    latency = slo_config.get("latency_slos", {}).get("default", {})

    # G3: Hallucination rate > 5% over 1-hour window
    halluc_rate = store.hallucination_rate(window_hours=1)
    halluc_max = quality.get("hallucination_rate_max", 0.05)
    if halluc_rate > halluc_max:
        alerts.append(Alert(
            condition="hallucination_spike",
            severity=Severity.HIGH,
            value=halluc_rate,
            threshold=halluc_max,
            message=(
                f"Hallucination rate {halluc_rate:.1%} exceeds {halluc_max:.1%} "
                f"threshold over the last 1h window."
            ),
        ))

    # G2: P95 latency regression
    percentiles = store.latency_percentiles(window_hours=24)
    p95 = percentiles.get("p95")
    ttft_p95_limit = latency.get("ttft_p95_ms", 1200)
    if p95 is not None and p95 > ttft_p95_limit:
        alerts.append(Alert(
            condition="latency_regression",
            severity=Severity.HIGH,
            value=p95,
            threshold=ttft_p95_limit,
            message=(
                f"P95 total latency {p95:.0f}ms exceeds {ttft_p95_limit}ms SLO."
            ),
        ))

    return alerts


def dispatch_to_slack(alerts: list[Alert], webhook_url: str = None) -> int:
    """
    Post fired alerts to Slack via webhook.
    Returns the number of alerts successfully dispatched.
    Silently skips if webhook URL is not configured.
    """
    url = webhook_url or _SLACK_WEBHOOK_URL
    if not url or not alerts:
        return 0

    try:
        import urllib.request
        dispatched = 0
        for alert in alerts:
            emoji = "🔴" if alert.severity == Severity.HIGH else "🟡"
            payload = json.dumps({
                "text": (
                    f"{emoji} *AI Platform Alert* [{alert.severity}]\n"
                    f"*Condition:* {alert.condition}\n"
                    f"*Detail:* {alert.message}\n"
                    f"*Value:* {alert.value:.4f}  |  *Threshold:* {alert.threshold:.4f}\n"
                    f"*Fired:* {alert.fired_at}"
                )
            }).encode()
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
            dispatched += 1
        return dispatched
    except Exception:
        return 0
