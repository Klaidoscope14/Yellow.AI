"""AI/ML (agentic) FastAPI service.

  POST /analyze   candidates + standards + context  ->  the reasoning sections
  GET  /health

The backend calls /analyze once; this layer reconciles the claims, diagnoses,
prescribes, verifies against replay, and authors the gaps. It returns exactly
the sections the backend needs to complete the loop-report.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import settings, reasoner, verifier

app = FastAPI(title="Nexus Loop — AI/ML layer", version="1.0.0")


class AnalyzeRequest(BaseModel):
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    standards: List[Dict[str, Any]] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    team: str = "nexus-detection-squad"


def _load_catalog(context: Dict[str, Any]) -> Dict[str, Any]:
    if context.get("catalog"):
        return context["catalog"]
    try:
        with open(settings.CATALOG_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": "aiml", "replay_enabled": settings.REPLAY_ENABLED,
            "replay_url": settings.REPLAY_URL}


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> Dict[str, Any]:
    # 1. Reconcile: validate every candidate as an evidence packet (orchestrator).
    accepted, reconciliation = reasoner.reconcile(req.candidates)

    # 2. Diagnose cause; 3. prescribe typed fixes toward the mined standard.
    diagnoses = reasoner.build_diagnoses(accepted)
    prescriptions = reasoner.build_prescriptions(accepted, req.standards)

    # 4. Verify prescriptions against replay (real before/after) — optional.
    #    Findings for cohort/window come from the backend context to avoid a
    #    corpus re-read here.
    findings = req.context.get("findings", [])
    golden = req.context.get("golden_set", [])
    verifications = verifier.run_verifications(prescriptions, findings, diagnoses,
                                              golden, req.team)
    self_assessment = verifier.build_self_assessment(verifications)

    # 5. Author gaps from the catalog + computed coverage/cardinality.
    catalog = _load_catalog(req.context)
    gaps = reasoner.build_gaps(catalog, req.context)

    return {
        "reconciliation": reconciliation,
        "diagnoses": diagnoses,
        "prescriptions": prescriptions,
        "verifications": verifications,
        "self_assessment": self_assessment,
        "gaps": gaps,
    }
