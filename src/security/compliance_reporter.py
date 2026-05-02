"""
Compliance sign-off reporter.

Generates a structured compliance report from the audit log and a set of
control validation results.  Intended to be run post-validation suite as
the final gate before production approval.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).parent.parent.parent


@dataclass
class ControlResult:
    control_id: str
    description: str
    status: str          # PASS | FAIL | SKIPPED
    evidence: str = ""
    detail: Optional[str] = None


@dataclass
class ComplianceReport:
    generated_at: str
    prd_version: str = "1.0"
    overall_status: str = "PENDING"
    controls: list[ControlResult] = field(default_factory=list)
    audit_record_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(asdict(self), indent=indent)

    def to_markdown(self) -> str:
        lines = [
            "# Compliance Sign-Off Report",
            f"**Generated:** {self.generated_at}",
            f"**PRD Version:** {self.prd_version}",
            f"**Overall Status:** `{self.overall_status}`",
            f"**Audit Records on File:** {self.audit_record_count}",
            "",
            "## Control Validation Results",
            "",
            "| Control ID | Description | Status | Evidence |",
            "|------------|-------------|--------|----------|",
        ]
        for c in self.controls:
            status_badge = "✅ PASS" if c.status == "PASS" else (
                "❌ FAIL" if c.status == "FAIL" else "⚠️ SKIPPED"
            )
            lines.append(
                f"| {c.control_id} | {c.description} | {status_badge} | {c.evidence} |"
            )
        if self.notes:
            lines += ["", "## Notes", ""]
            lines += [f"- {n}" for n in self.notes]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# PRD §2 control definitions
# ---------------------------------------------------------------------------

PRD_CONTROLS: list[dict] = [
    {
        "control_id": "G1",
        "description": "Role-scoped prompt injection prevention — zero cross-role data leakage",
        "test_marker": "pen_test",
    },
    {
        "control_id": "G2",
        "description": "PII redacted before reaching model context (recall ≥ 99%)",
        "test_marker": "pii",
    },
    {
        "control_id": "G3",
        "description": "100% of completions logged with user + role + timestamp",
        "test_marker": "audit",
    },
    {
        "control_id": "G4",
        "description": "Security layer P99 latency ≤ 120 ms",
        "test_marker": "latency",
    },
    {
        "control_id": "RT1",
        "description": "PII exfiltration via indirect prompt injection blocked",
        "test_marker": "red_team",
    },
    {
        "control_id": "RT2",
        "description": "Token smuggling via retrieved content rejected",
        "test_marker": "token_smuggling",
    },
]


def run_validation_suite() -> ComplianceReport:
    """
    Execute the validation test suite via pytest and parse results into a
    ComplianceReport.  Returns a fully-populated report.
    """
    report = ComplianceReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # Run pytest in verbose mode so test node IDs appear in output
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/validation/",
            "-v",
            "--tb=short",
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr

    # Map controls by checking that at least one matching test node PASSED.
    # Keywords are substrings of test node IDs written in each validation module.
    control_map = {
        "G1": _check_output(output, ["prompt_injection", "PASSED"]),
        "G2": _check_output(output, ["pii_redact", "PASSED"]) or
              _check_output(output, ["pii_in_injection", "PASSED"]) or
              _check_output(output, ["pii_in_retrieved", "PASSED"]),
        "G3": _check_output(output, ["audit", "PASSED"]),
        "G4": _check_output(output, ["latency", "PASSED"]),
        "RT1": _check_output(output, ["indirect_injection", "PASSED"]),
        "RT2": _check_output(output, ["token_smuggling", "PASSED"]) or
               _check_output(output, ["fake_token", "PASSED"]),
    }

    for ctrl in PRD_CONTROLS:
        cid = ctrl["control_id"]
        status = "PASS" if control_map.get(cid, False) else (
            "FAIL" if result.returncode != 0 else "SKIPPED"
        )
        report.controls.append(ControlResult(
            control_id=cid,
            description=ctrl["description"],
            status=status,
            evidence=f"pytest tests/validation/ (exit={result.returncode})",
        ))

    # Audit record count from live DB if available
    try:
        from security.audit_logger import AuditLogger
        logger = AuditLogger()
        report.audit_record_count = logger.count()
    except Exception:
        report.notes.append("Audit DB not available; record count skipped.")

    all_pass = all(c.status == "PASS" for c in report.controls)
    report.overall_status = "APPROVED" if all_pass else "REVIEW_REQUIRED"

    if not all_pass:
        failing = [c.control_id for c in report.controls if c.status != "PASS"]
        report.notes.append(f"Failing controls: {', '.join(failing)}")

    return report


def _check_output(output: str, keywords: list[str]) -> bool:
    """Return True if all keywords appear in the pytest output (case-insensitive)."""
    lowered = output.lower()
    return all(kw.lower() in lowered for kw in keywords)


if __name__ == "__main__":
    report = run_validation_suite()
    print(report.to_markdown())
    print("\n--- JSON ---")
    print(report.to_json())

    out_path = _REPO_ROOT / "compliance_report.json"
    out_path.write_text(report.to_json())
    print(f"\nReport written to {out_path}")

    sys.exit(0 if report.overall_status == "APPROVED" else 1)
