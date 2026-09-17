"""Deterministic backend adapter over the generated Nexus Loop report."""
from __future__ import annotations

import gzip
import json
import os
from typing import Any


class Engine:
    def __init__(self) -> None:
        self.ready = False
        self.row_counts: dict[str, int] = {}
        self.report: dict[str, Any] = {}
        self.standards: list[dict[str, Any]] = []
        self.candidates: list[dict[str, Any]] = []
        self.catalog: dict[str, Any] = {}
        self.cardinality: list[dict[str, Any]] = []

    @property
    def root(self) -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def warm(self) -> None:
        if self.ready:
            return
        report_path = os.environ.get(
            "NEXUS_REPORT_PATH",
            os.path.join(self.root, "loop-report.json"),
        )
        with open(report_path, encoding="utf-8") as handle:
            self.report = json.load(handle)
        catalog_path = os.path.join(self.root, "kit", "catalog.json")
        if os.path.exists(catalog_path):
            with open(catalog_path, encoding="utf-8") as handle:
                self.catalog = json.load(handle)
        self.standards = self.report.get("standard", [])
        diagnoses = {d.get("finding_id"): d for d in self.report.get("diagnoses", [])}
        self.candidates = []
        for finding in self.report.get("findings", []):
            diagnosis = diagnoses.get(finding.get("id"), {})
            metric = finding.get("metric", "unknown")
            self.candidates.append({
                "problem_id": finding.get("id"),
                "tenant": finding.get("tenant"),
                "cohort": finding.get("cohort", {}),
                "window": finding.get("window", {}),
                "primary_metric": metric,
                "metrics": {metric: {
                    "during": finding.get("observed"),
                    "before": finding.get("expected"),
                }},
                "cause_class": diagnosis.get("cause_class"),
                "config_attribution": {
                    "found": bool(diagnosis.get("attributed_change")),
                    "changes": ([diagnosis["attributed_change"]]
                                if diagnosis.get("attributed_change") else []),
                },
                "corroborating_signals": len(finding.get("evidence", [])),
                "is_regression": finding.get("is_regression", False),
                "evidence": finding.get("evidence", []),
                "impact": finding.get("impact", {}),
                "severity": finding.get("severity"),
            })
        self.row_counts = {"findings": len(self.candidates), "standards": len(self.standards)}
        self.ready = True

    def tool_coverage(self) -> float:
        for metric in self.report.get("metrics", []):
            if metric.get("id") == "m_tool_failure":
                return float((metric.get("coverage") or {}).get("value", 0))
        return 0.0

    def coverage_by_tenant(self) -> dict[str, float]:
        return {}

    def golden_set(self, limit: int) -> list[str]:
        path = os.path.join(self.root, "kit", "corpus", "sessions.jsonl.gz")
        result: list[str] = []
        if not os.path.exists(path):
            return result
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("session_end") == "resolved":
                    result.append(row["session_id"])
                if len(result) >= limit:
                    break
        return result


engine = Engine()
