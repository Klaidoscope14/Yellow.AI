"""Report-grounded chat responses for the backend API."""
from __future__ import annotations

from typing import Any

SUGGESTIONS = [
    "What is the highest-impact regression?",
    "Why was the failover question refused?",
    "Which fixes are waiting for approval?",
]


def answer(question: str, report: dict[str, Any]) -> dict[str, Any]:
    text = question.strip().lower()
    if "failover" in text:
        gap = next((g for g in report.get("gaps", []) if g.get("ask_id") == "A11"), None)
        if gap:
            return {
                "answer": gap.get("why", "Failover is not measurable from the available events."),
                "based_on": ["gap:A11"],
                "link": {"screen": "refusals"},
                "refusal": True,
                "intent": "gap_lookup",
            }
    findings = report.get("findings", [])
    finding = next((f for f in findings if f.get("is_regression")), None)
    if finding:
        return {
            "answer": finding.get("plain_summary") or finding.get("metric", "Regression detected."),
            "based_on": [f"finding:{finding.get('id')}"],
            "link": {"screen": "finding", "id": finding.get("id")},
            "refusal": False,
            "intent": "finding_lookup",
        }
    return {
        "answer": "The report contains no matching finding.",
        "based_on": [],
        "link": None,
        "refusal": False,
        "intent": "unknown",
    }
