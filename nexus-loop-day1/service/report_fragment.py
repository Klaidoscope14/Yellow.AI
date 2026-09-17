"""Report fragments exposed by the deterministic backend adapter."""
from __future__ import annotations

from typing import Any


def build_metrics(engine: Any) -> list[dict[str, Any]]:
    return engine.report.get("metrics", [])


def build_findings(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for candidate in candidates:
        metric = candidate.get("primary_metric")
        values = candidate.get("metrics", {}).get(metric, {})
        findings.append({
            "id": candidate.get("problem_id"),
            "tenant": candidate.get("tenant"),
            "cohort": candidate.get("cohort", {}),
            "metric": metric,
            "window": candidate.get("window", {}),
            "observed": values.get("during"),
            "expected": values.get("before"),
            "is_regression": candidate.get("is_regression", False),
            "severity": candidate.get("severity", "medium"),
            "evidence": candidate.get("evidence", []),
            "impact": candidate.get("impact", {}),
            "audience": [],
        })
    return findings
