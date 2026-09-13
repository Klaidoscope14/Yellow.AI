#!/usr/bin/env python3
"""Reliability critic for the Nexus Loop pipeline.

The scorer measures performance on the supplied practice corpus. This critic
checks whether the implementation is likely to generalize beyond that corpus.
It audits source hardcoding and the generated report independently.

Examples:
    py critic.py --pipeline pipeline.py --report ../../my-executed-loop-report-fixed.json
    py critic.py --pipeline pipeline.py --report ../../my-executed-loop-report-fixed.json --strict
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List


@dataclass
class Finding:
    finding_id: str
    severity: str
    category: str
    location: str
    issue: str
    risk: str
    recommendation: str


PRACTICE_LITERALS = (
    "acme-bank",
    "northwind-retail",
    "premium_card_info",
    "order_status",
    "acme_main_v3",
    "get_order_status",
    "branch_locator",
)


def line_number(source: str, position: int) -> int:
    return source.count("\n", 0, position) + 1


def add_literal_findings(source: str, findings: List[Finding]) -> None:
    for literal in PRACTICE_LITERALS:
        match = re.search(re.escape(literal), source)
        if not match:
            continue
        findings.append(Finding(
            finding_id="HARDCODE-" + literal.upper().replace("-", "_"),
            severity="high",
            category="portability",
            location=f"pipeline.py:{line_number(source, match.start())}",
            issue=f"Detector contains practice-specific literal {literal!r}.",
            risk="A renamed tenant, cohort, agent, or tool can be missed without an error.",
            recommendation="Discover the affected dimension from candidate evidence and configuration changes.",
        ))


def add_pattern_finding(source: str, findings: List[Finding], finding_id: str,
                        pattern: str, category: str, issue: str, risk: str,
                        recommendation: str, severity: str = "medium") -> None:
    match = re.search(pattern, source, re.MULTILINE)
    if match:
        findings.append(Finding(
            finding_id=finding_id,
            severity=severity,
            category=category,
            location=f"pipeline.py:{line_number(source, match.start())}",
            issue=issue,
            risk=risk,
            recommendation=recommendation,
        ))


def audit_source(path: Path) -> List[Finding]:
    source = path.read_text(encoding="utf-8")
    findings: List[Finding] = []
    add_literal_findings(source, findings)
    add_pattern_finding(
        source, findings, "FIXED-COVERAGE", r'"value": 0\.725',
        "measurement", "Tool coverage is a fixed 0.725 claim.",
        "Coverage can be materially wrong on a different corpus or traffic mix.",
        "Compute coverage from observed session and step denominators.", "high")
    add_pattern_finding(
        source, findings, "FIXED-WINDOWS", r"40 <= row\[\"day\"\] < 52",
        "detection", "F2 uses a fixed day window.",
        "The detector can miss the same fault when deployment timing changes.",
        "Infer onset and sustain windows from timeline changes and anomaly boundaries.", "high")
    add_pattern_finding(
        source, findings, "FIXED-THRESHOLDS", r"during_silent / during_calls > 0\.05",
        "detection", "Silent-tool detection uses a fixed 5% threshold.",
        "Small cohorts and different base rates can create false positives or negatives.",
        "Use sample-size-aware confidence intervals or calibrated thresholds.")
    add_pattern_finding(
        source, findings, "FIXED-PROMPT-RATIO", r"during_turns > before_turns \* 1\.2",
        "detection", "Prompt detection uses a fixed 20% turns threshold.",
        "Variance and cohort size are ignored.",
        "Use uncertainty bounds and a minimum practical effect size.")
    return findings


def audit_report(path: Path) -> List[Finding]:
    report = json.loads(path.read_text(encoding="utf-8"))
    findings: List[Finding] = []
    prescriptions = report.get("prescriptions", [])
    verifications = report.get("verifications", [])
    if report.get("findings") and not report.get("standard"):
        findings.append(Finding(
            "REPORT-NO-STANDARDS", "high", "report", str(path),
            "Report contains findings but no standards.",
            "Relative regressions cannot be compared against a stable yardstick.",
            "Require non-empty standards before accepting a diagnostic report.",
        ))
    if prescriptions and len(verifications) != len(prescriptions):
        findings.append(Finding(
            "REPORT-UNVERIFIED", "critical", "verification", str(path),
            f"Report has {len(prescriptions)} prescriptions but {len(verifications)} verifications.",
            "Actions may appear proposed without evidence that they were tested.",
            "Require one replay verification per prescription or mark it explicitly deferred.",
        ))
    missing_golden = [item.get("prescription_id") for item in verifications
                      if item.get("golden_set_pass") is not True]
    if missing_golden:
        findings.append(Finding(
            "REPORT-GOLDEN-SET", "high", "verification", str(path),
            "Some verifications do not pass a golden-set check: " + ", ".join(missing_golden),
            "A fix may improve the target cohort while damaging known-good behavior.",
            "Send a non-empty known-good golden set and require golden_set_pass=true.",
        ))
    assessment = report.get("self_assessment") or {}
    if verifications and not assessment.get("prescription_accuracy"):
        findings.append(Finding(
            "REPORT-NO-LEARNING", "medium", "learning", str(path),
            "Replay results exist but self-assessment has no accuracy summary.",
            "Prediction quality cannot improve future decisions.",
            "Aggregate prediction error and hit rate by change type.",
        ))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--strict", action="store_true",
                        help="fail on high or critical reliability findings")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = audit_source(args.pipeline) + audit_report(args.report)
    counts = {level: sum(item.severity == level for item in findings)
              for level in ("critical", "high", "medium", "low")}
    status = "fail" if args.strict and (counts["critical"] or counts["high"]) else (
        "pass" if not findings else "review"
    )
    result = {
        "status": status,
        "counts": counts,
        "findings": [asdict(item) for item in findings],
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("NEXUS LOOP RELIABILITY CRITIC")
        print("status: %s" % result["status"])
        print("findings: critical=%d high=%d medium=%d low=%d" % (
            counts["critical"], counts["high"], counts["medium"], counts["low"]))
        for item in findings:
            print("\n[%s] %s (%s)" % (item.severity.upper(), item.finding_id, item.location))
            print("  issue: %s" % item.issue)
            print("  risk: %s" % item.risk)
            print("  recommendation: %s" % item.recommendation)
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
