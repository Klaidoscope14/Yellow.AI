"""Backend FastAPI service (frontend -> backend -> ai/ml).

Owns the data and all deterministic measurement: metrics, standards, detection
candidates, coverage, calibration, cardinality. Exposes them for the frontend,
and assembles the full loop-report by delegating the reasoning sections
(diagnoses, prescriptions, verifications, gaps, self-assessment) to the ai/ml
layer over HTTP.

No LLM computes any number here (Golden Rule 1); FastAPI is pure transport.
"""
from __future__ import annotations

import datetime as _dt
import os
import threading
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import settings
from .engine import engine
from . import report_fragment, store, chat

app = FastAPI(title="Nexus Loop — backend", version="1.0.0")

# Last assembled report, cached so /chat and /approvals never re-trigger replay
# (which has a per-team run budget). /report refreshes it.
_REPORT_LOCK = threading.Lock()
_LAST_REPORT: Optional[Dict[str, Any]] = None

# The frontend calls this API from the browser. Allow-list is overridable;
# defaults to permissive for local development.
_origins = settings.__dict__.get("CORS_ORIGINS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=(_origins.split(",") if isinstance(_origins, str) and _origins else ["*"]),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Compute-once warm-up so the first request is a cache hit, not an 880k rescan.
    engine.warm()


@app.get("/health")
def health() -> Dict[str, Any]:
    engine.warm()
    return {"ok": True, "service": "backend", "ready": engine.ready,
            "rows": engine.row_counts, "aiml_url": settings.AIML_URL}


@app.get("/metrics")
def metrics() -> List[Dict[str, Any]]:
    engine.warm()
    return report_fragment.build_metrics(engine)


@app.get("/standards")
def standards() -> List[Dict[str, Any]]:
    engine.warm()
    return engine.standards


@app.get("/candidates")
def candidates() -> List[Dict[str, Any]]:
    engine.warm()
    return engine.candidates


@app.get("/findings")
def findings() -> List[Dict[str, Any]]:
    engine.warm()
    return report_fragment.build_findings(engine.candidates)


@app.get("/coverage")
def coverage() -> Dict[str, Any]:
    engine.warm()
    return {"tool_coverage": engine.tool_coverage(),
            "by_tenant": engine.coverage_by_tenant(),
            "cardinality": engine.cardinality}


def _context(findings_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "tool_coverage": engine.tool_coverage(),
        "coverage_by_tenant": engine.coverage_by_tenant(),
        "cardinality": engine.cardinality,
        "catalog": engine.catalog,
        "golden_set": engine.golden_set(settings.__dict__.get("GOLDEN_SET_SIZE", 20) or 20),
        "findings": findings_list,
    }


def _assemble(team: str) -> Dict[str, Any]:
    """Build the full loop-report: backend measurement + ai/ml reasoning.
    Applies any stored approvals and caches the result."""
    engine.warm()
    metrics_list = report_fragment.build_metrics(engine)
    standards_list = engine.standards
    findings_list = report_fragment.build_findings(engine.candidates)

    aiml_payload = {
        "candidates": engine.candidates,
        "standards": standards_list,
        "context": _context(findings_list),
        "team": team,
    }
    try:
        with httpx.Client(timeout=settings.AIML_TIMEOUT_S) as client:
            resp = client.post(settings.AIML_URL.rstrip("/") + "/analyze", json=aiml_payload)
            resp.raise_for_status()
            aiml = resp.json()
    except Exception as exc:  # ai/ml down — surface clearly rather than a half report
        raise HTTPException(status_code=502,
                            detail=f"ai/ml layer unavailable at {settings.AIML_URL}: {exc}")

    report_obj = {
        "team": team,
        "corpus": settings.CORPUS_VARIANT,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "system_notes": (
            "Three-tier product: backend (DuckDB, deterministic metrics + detection + "
            "standards) -> ai/ml (trust-reconciled diagnosis, typed prescriptions, replay "
            "verification, gap authoring). Metric computation is deterministic SQL only "
            "(Golden Rule 1); quality is segmented by judge_version (Golden Rule 3); coverage "
            "and calibration are computed, not assumed."),
        "metrics": metrics_list,
        "standard": standards_list,
        "findings": findings_list,
        "diagnoses": aiml.get("diagnoses", []),
        "prescriptions": aiml.get("prescriptions", []),
        "verifications": aiml.get("verifications", []),
        "gaps": aiml.get("gaps", []),
        "self_assessment": aiml.get("self_assessment", {}),
        "reconciliation": aiml.get("reconciliation", []),
    }
    store.apply_to_report(report_obj)
    global _LAST_REPORT
    with _REPORT_LOCK:
        _LAST_REPORT = report_obj
    return report_obj


def _current_report() -> Dict[str, Any]:
    """Cached report for read-only consumers (chat, approvals). Builds once."""
    with _REPORT_LOCK:
        cached = _LAST_REPORT
    if cached is not None:
        return cached
    return _assemble("nexus-detection-squad")


@app.get("/report")
def report(team: str = "nexus-detection-squad", refresh: bool = True) -> Dict[str, Any]:
    """Full loop-report. refresh=false returns the cached build without spending
    a replay run."""
    if not refresh:
        return _current_report()
    return _assemble(team)


class ApprovalIn(BaseModel):
    prescription_id: str
    verdict: str            # accepted | rejected | deferred
    reason: str = ""
    decided_by: str = "operator"


@app.post("/approvals")
def post_approval(body: ApprovalIn) -> Dict[str, Any]:
    """Record a human Approve/Reject on a prescription (Screen 2) and reflect it
    in the cached report."""
    try:
        approval = store.record(body.prescription_id, body.verdict, body.reason, body.decided_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    with _REPORT_LOCK:
        if _LAST_REPORT is not None:
            for rx in _LAST_REPORT.get("prescriptions", []):
                if rx.get("id") == body.prescription_id:
                    rx["approval"] = approval
    return {"prescription_id": body.prescription_id, "approval": approval}


@app.get("/approvals")
def get_approvals() -> Dict[str, Any]:
    return store.all_approvals()


class ChatIn(BaseModel):
    question: str


@app.get("/chat/suggestions")
def chat_suggestions() -> List[str]:
    return chat.SUGGESTIONS


@app.post("/chat")
def post_chat(body: ChatIn) -> Dict[str, Any]:
    """Answer from the already-computed report only (Rule 1): retrieve + phrase."""
    return chat.answer(body.question, _current_report())


# --- serve the frontend (same origin as the API -> no CORS needed) ----------
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


@app.get("/")
def _root():
    return RedirectResponse(url="/app/")
