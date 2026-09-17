"""Replay verification and self-assessment.

Each typed prescription is replayed once against the replay endpoint, which
returns a before/after for the cohort and a golden-set regression check. The
self-assessment is computed from those real results — never fabricated. If
replay is disabled or unreachable, verification degrades to empty rather than
crashing the product.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

import httpx

from . import settings


def _finding_for(prescription: Dict[str, Any], findings: List[Dict[str, Any]],
                 diagnoses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    diag = next((d for d in diagnoses if d["id"] == prescription.get("diagnosis_id")), None)
    if not diag:
        return None
    return next((f for f in findings if f["id"] == diag.get("finding_id")), None)


def run_verifications(prescriptions: List[Dict[str, Any]],
                      findings: List[Dict[str, Any]],
                      diagnoses: List[Dict[str, Any]],
                      golden_set: List[str],
                      team: str) -> List[Dict[str, Any]]:
    if not settings.REPLAY_ENABLED or not prescriptions:
        return []

    verifications: List[Dict[str, Any]] = []
    url = settings.REPLAY_URL.rstrip("/") + "/replay"
    try:
        client = httpx.Client(timeout=settings.REPLAY_TIMEOUT_S)
    except Exception:
        return []

    with client:
        for rx in prescriptions:
            finding = _finding_for(rx, findings, diagnoses)
            if not finding:
                continue
            cohort = dict(finding.get("cohort") or {})
            cohort.update(finding.get("window") or {})
            body = {
                "team": team,
                "tenant": finding.get("tenant"),
                "change": {"type": rx["change_type"], "target": rx.get("target", ""),
                           "description": rx.get("description", "")},
                "cohort": cohort,
                "golden_set": golden_set,
            }
            try:
                resp = client.post(url, json=body)
                result = resp.json()
            except Exception:
                continue  # replay unreachable mid-run; skip this one, keep the rest
            if "verdict" not in result:  # e.g. run_budget_exhausted / error
                continue
            predicted = rx.get("predicted_delta", {})
            pred_to = predicted.get("to")
            verifications.append({
                "prescription_id": rx["id"],
                "replay_run_id": result.get("run_id"),
                "metric": result.get("metric"),
                "before": result.get("before"),
                "after": result.get("after"),
                "golden_set_pass": (result.get("golden_set") or {}).get("pass"),
                "verdict": result.get("verdict"),
                "prediction_error": (round(pred_to - result["after"], 4)
                                     if pred_to is not None and result.get("after") is not None
                                     else None),
            })
    return verifications


def build_self_assessment(verifications: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not verifications:
        return {"cycles": 0, "prescription_accuracy": {}, "downweighted": [],
                "notes": ("No replay cycle ran (endpoint disabled or unreachable). Prescriptions "
                          "are proposed with predicted deltas but not yet verified.")}

    by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    # Map prescription_id -> change_type is not available here; group by metric as a
    # deterministic proxy that still separates the fix families (resolution vs turns).
    for v in verifications:
        by_type[v.get("metric") or "unknown"].append(v)

    accuracy: Dict[str, Any] = {}
    for key, items in by_type.items():
        errs = [i["prediction_error"] for i in items if i.get("prediction_error") is not None]
        accuracy[key] = {
            "n": len(items),
            "hit_rate": round(sum(i.get("verdict") == "improved" for i in items) / len(items), 4),
            "mean_prediction_error": round(sum(errs) / len(errs), 4) if errs else None,
        }
    return {
        "cycles": 1,
        "prescription_accuracy": accuracy,
        "downweighted": [],
        "notes": ("One replay cycle completed; results recorded. With n small per family the loop "
                  "reports accuracy but does not yet down-weight any change class."),
    }
