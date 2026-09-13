"""Durable approval store.

Screen 2's Approve/Reject decision must survive report regeneration and process
restarts, so it is persisted to a small JSON file keyed by prescription id.
Prescription ids are deterministic (`rx_<problem_id>`), so a stored verdict
re-attaches to the same prescription on the next report build.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import settings

_LOCK = threading.Lock()
_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "output", "approvals.json")

_VALID = {"accepted", "rejected", "deferred"}


def _load() -> Dict[str, Any]:
    try:
        with open(_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    tmp = _PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, _PATH)


def record(prescription_id: str, verdict: str, reason: str = "",
           decided_by: str = "operator") -> Dict[str, Any]:
    """Persist one decision and return the approval object."""
    if verdict not in _VALID:
        raise ValueError(f"verdict must be one of {sorted(_VALID)}")
    approval = {
        "verdict": verdict,
        "decided_by": decided_by or "operator",
        "reason": reason or "",
        "at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        data = _load()
        data[prescription_id] = approval
        _save(data)
    return approval


def get(prescription_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        return _load().get(prescription_id)


def all_approvals() -> Dict[str, Any]:
    with _LOCK:
        return _load()


def apply_to_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Merge stored verdicts onto the report's prescriptions in place."""
    stored = all_approvals()
    for rx in report.get("prescriptions", []):
        if rx.get("id") in stored:
            rx["approval"] = stored[rx["id"]]
    return report
