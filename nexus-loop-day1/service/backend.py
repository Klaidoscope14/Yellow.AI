"""Backend FastAPI service (frontend -> backend -> ai/ml).

Owns deterministic measurements and delegates reasoning sections to the AI/ML
layer over HTTP. It is intentionally separate from ``service.app``, which is
the AI/ML ``/analyze`` service.
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

app = FastAPI(title="Nexus Loop - backend", version="1.0.0")

_REPORT_LOCK = threading.Lock()
_LAST_REPORT: Optional[Dict[str, Any]] = None

_origins = settings.__dict__.get("CORS_ORIGINS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=(_origins.split(",") if isinstance(_origins, str) and _origins else ["*"]),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    engine.warm()


@app.get("/health")
def health() -> Dict[str, Any]:
    engine.warm()
    return {
        "ok": True,
        "service": "backend",
        "ready": engine.ready,
        "rows": engine.row_counts,
        "aiml_url": settings.AIML_URL,
    }


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
    return {
        "tool_coverage": engine.tool_coverage(),
        "by_tenant": engine.coverage_by_tenant(),
        "cardinality": engine.cardinality,
    }


def _context(findings_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "tool_coverage": engine.tool_coverage(),
        "coverage_by_tenant": engine.coverage_by_tenant(),
        "cardinality": engine.cardinality,
        "catalog": engine.catalog,
        "golden_set": engine.golden_set(settings.GOLDEN_SET_SIZE),
        "findings": findings_list,
    }


def _assemble(team: str) -> Dict[str, Any]:
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
            response = client.post(settings.AIML_URL.rstrip("/") + "/analyze", json=aiml_payload)
            response.raise_for_status()
            aiml = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"ai/ml layer unavailable at {settings.AIML_URL}: {exc}",
        ) from exc

    report_obj = {
        "team": team,
        "corpus": settings.CORPUS_VARIANT,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "system_notes": (
            "Three-tier product: backend deterministic measurement -> ai/ml reasoning. "
            "Metric computation is deterministic; quality is segmented by judge_version; "
            "coverage and calibration are computed."
        ),
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
    with _REPORT_LOCK:
        cached = _LAST_REPORT
    return cached if cached is not None else _assemble("nexus-detection-squad")


@app.get("/report")
def report(team: str = "nexus-detection-squad", refresh: bool = True) -> Dict[str, Any]:
    if not refresh:
        return _current_report()
    return _assemble(team)


class ApprovalIn(BaseModel):
    prescription_id: str
    verdict: str
    reason: str = ""
    decided_by: str = "operator"


@app.post("/approvals")
def post_approval(body: ApprovalIn) -> Dict[str, Any]:
    try:
        approval = store.record(body.prescription_id, body.verdict, body.reason, body.decided_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    with _REPORT_LOCK:
        if _LAST_REPORT is not None:
            for prescription in _LAST_REPORT.get("prescriptions", []):
                if prescription.get("id") == body.prescription_id:
                    prescription["approval"] = approval
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
    return chat.answer(body.question, _current_report())


_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")


@app.get("/")
def _root() -> RedirectResponse:
    return RedirectResponse(url="/app/")
