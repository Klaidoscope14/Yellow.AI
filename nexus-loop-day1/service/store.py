"""Small local approval store used by the FastAPI backend."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".approvals.json")


def _load() -> dict[str, Any]:
    try:
        with open(_PATH, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(value: dict[str, Any]) -> None:
    temporary = _PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
    os.replace(temporary, _PATH)


def record(prescription_id: str, verdict: str, reason: str, decided_by: str) -> dict[str, Any]:
    if verdict not in {"accepted", "rejected", "deferred"}:
        raise ValueError("verdict must be accepted, rejected, or deferred")
    if not reason.strip():
        raise ValueError("reason is required")
    approval = {
        "verdict": verdict,
        "decided_by": decided_by or "operator",
        "reason": reason.strip(),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    approvals = _load()
    approvals[prescription_id] = approval
    _save(approvals)
    return approval


def all_approvals() -> dict[str, Any]:
    return _load()


def apply_to_report(report: dict[str, Any]) -> None:
    approvals = _load()
    for prescription in report.get("prescriptions", []):
        approval = approvals.get(prescription.get("id"))
        if approval:
            prescription["approval"] = approval
