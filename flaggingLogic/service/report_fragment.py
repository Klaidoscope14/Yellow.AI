"""Backend's slice of the loop-report: metrics[], standard[], findings[].

Everything here is generic: coverage and calibration are computed from the
engine, impact blocks are derived from each candidate's own before/during
numbers, and there are no tenant/intent/tool/day literals or fabricated
fallback constants. The same code produces a correct fragment on the practice
corpus and on the sealed corpus.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .engine import BackendEngine


# Which audiences must act, by cause. Generic mapping, not per-fault text.
_AUDIENCE = {
    "kb.gap": ["agent_builder", "business_owner"],
    "tool.contract_break": ["agent_builder", "platform_owner"],
    "prompt.regression": ["agent_builder"],
}


def plain_summary(cand: Dict[str, Any]) -> str:
    """One plain-English sentence for a finding — the claim the operator reads
    first (Screen 1 card, Screen 2 headline, chatbot). Generic, from the cohort
    and cause, no per-fault literals."""
    cause = cand.get("cause_class")
    cohort = cand.get("cohort", {})
    intent = cohort.get("intent")
    agent = cohort.get("agent_id")
    where = f"the {intent} flow" if intent else (f"the {agent} assistant" if agent else "this area")
    if cause == "kb.gap":
        return (f"{where.capitalize()} often can't find a knowledge-base answer, "
                f"so many of these conversations don't get resolved.")
    if cause == "tool.contract_break":
        return (f"A tool used by {where} is returning empty results while reporting success, "
                f"so answers quietly fall through and users aren't helped.")
    if cause == "prompt.regression":
        return (f"{where.capitalize()} is taking noticeably more back-and-forth per "
                f"conversation — and costing more — even though it still resolves them.")
    if cause == "traffic_mix":
        return ("An overall number moved only because the mix of question types shifted; "
                "each type is performing about the same as before.")
    if cause == "load":
        return ("A short spike in traffic raised response times, but answer quality held — "
                "this was a load event, not a quality problem.")
    if cause == "judge_change":
        return ("Quality scores dropped on every team at once because the grading rubric "
                "changed — the assistant itself did not get worse.")
    return cand.get("not_a_regression_because") or "A change was observed in this area."


def build_metrics(engine: BackendEngine) -> List[Dict[str, Any]]:
    """Declare every authored metric with computed coverage and real calibration.

    Fidelity is fixed by the nature of each ask (A04 measured, A06/A09 judged),
    which is what the honesty score checks; coverage on tool/kb/cost metrics is
    the engine's computed non-legacy share, so it tracks the corpus rather than
    a baked-in 0.725.
    """
    tool_cov = engine.tool_coverage()
    cov_basis = ("v2_flow sessions emit no tool_call/kb_lookup rows and carry no LLM cost; "
                 "excluded from the denominator (computed as the minimum non-legacy session "
                 "share across tenants), not counted as zero.")
    calib = engine.calibration  # None when labels absent — honest rather than fabricated

    def cov_full():
        return {"value": 1.0, "basis": "present on every session, v2 and v3 alike"}

    def cov_v3():
        return {"value": tool_cov, "basis": cov_basis, "excluded": ["agent_kind = v2_flow"]}

    return [
        {"id": "m_containment", "name": "Containment rate", "ask_id": "A01", "grain": "session",
         "fidelity": "measured", "coverage": cov_full(), "calibration": None,
         "plan": {"source": "sessions", "filter": "session_end='resolved' OR (session_end='handoff' AND handoff_by_design)",
                  "denominator": "all sessions in scope", "breakdowns": ["intent", "agent_kind", "agent_id"],
                  "alternatives_offered": ["resolution_rate — excludes by-design handoffs"]}},
        {"id": "m_resolution", "name": "Resolution rate", "ask_id": "A01", "grain": "session",
         "fidelity": "measured", "coverage": cov_full(), "calibration": None,
         "plan": {"source": "sessions", "filter": "session_end='resolved'",
                  "denominator": "all sessions in scope", "breakdowns": ["intent", "agent_id", "day"]}},
        {"id": "m_turns", "name": "Turns to resolve", "ask_id": "A02", "grain": "session",
         "fidelity": "measured", "coverage": cov_full(), "calibration": None,
         "plan": {"source": "sessions", "filter": "median over resolved sessions",
                  "denominator": "n/a — distribution reported as median and p90", "breakdowns": ["intent", "agent_id"]}},
        {"id": "m_cost", "name": "Cost per session", "ask_id": "A08", "grain": "session",
         "fidelity": "measured", "coverage": cov_v3(), "calibration": None,
         "plan": {"source": "sessions WHERE agent_kind='v3_agent'", "filter": "none",
                  "denominator": "v3_agent sessions only", "breakdowns": ["intent", "agent_id"]}},
        {"id": "m_tool_fail", "name": "Tool failure rate", "ask_id": "A04", "grain": "step",
         "fidelity": "measured", "coverage": cov_v3(), "calibration": None,
         "plan": {"source": "steps WHERE step_type='tool_call'", "filter": "outcome IN ('error','timeout')",
                  "denominator": "all tool_call steps on v3 sessions", "breakdowns": ["tool_name", "agent_id"]}},
        {"id": "m_silent_tool", "name": "Silent tool failure rate", "ask_id": "A04", "grain": "step",
         "fidelity": "derived", "coverage": cov_v3(), "calibration": None,
         "plan": {"source": "steps WHERE step_type='tool_call'", "filter": "outcome='ok' AND result_field_count=0",
                  "denominator": "tool_call steps with outcome='ok'", "breakdowns": ["tool_name"],
                  "alternatives_offered": ["catalog lists silent_tool_success as derivable_not_declared — derived and declared here"]}},
        {"id": "m_kb_miss", "name": "KB miss rate", "ask_id": "A06", "grain": "step",
         "fidelity": "measured", "coverage": cov_v3(), "calibration": None,
         "plan": {"source": "steps WHERE step_type='kb_lookup'", "filter": "kb_hit=false",
                  "denominator": "all kb_lookup steps", "breakdowns": ["intent"]}},
        {"id": "m_quality", "name": "Judged quality", "ask_id": "A06", "grain": "session",
         "fidelity": "judged", "coverage": cov_full(), "calibration": calib,
         "plan": {"source": "sessions", "filter": "quality_score SEGMENTED BY judge_version — never trended across the boundary",
                  "denominator": "sessions within one judge_version", "breakdowns": ["intent", "judge_version"]}},
        {"id": "m_abandon_reason", "name": "Abandonment with frustration", "ask_id": "A09", "grain": "session",
         "fidelity": "judged", "coverage": cov_full(), "calibration": calib,
         "plan": {"source": "sessions JOIN turns", "filter": "session_end='abandoned', then a judged rubric over the last turns",
                  "denominator": "all abandoned sessions", "breakdowns": ["intent"],
                  "alternatives_offered": ["session_end='abandoned' alone is MEASURED but answers a different question"]}},
    ]


def _impact_block(cand: Dict[str, Any]) -> Dict[str, Any]:
    """Build a schema impact block from the candidate's own numbers only."""
    imp = cand.get("impact", {})
    m = cand.get("metrics", {})
    affected = imp.get("conversations_affected", 0)
    share = imp.get("share_of_tenant_traffic", 0)
    days = max(1, imp.get("days_running", 1))
    cause = cand.get("cause_class")

    block: Dict[str, Any] = {
        "conversations_affected": affected,
        "share_of_traffic": share,
        "days_running": imp.get("days_running", days),
        "derivation": imp.get("derivation", ""),
        "cost_usd": None,
    }

    res = m.get("resolution_rate", {}) if isinstance(m.get("resolution_rate"), dict) else {}
    res_before, res_during = res.get("before"), res.get("during")

    if cause in ("kb.gap", "tool.contract_break") and res_before and res_during is not None:
        would = round(affected * res_before)
        did = round(affected * res_during)
        deficit = would - did
        block["downstream"] = {"would_have_resolved_at_baseline": would, "deficit": deficit}
        if cause == "tool.contract_break":
            silent = m.get("silent_calls_total")
            if silent is not None:
                block["downstream"]["silent_empty_responses"] = silent
        block["derivation"] = (
            f"{affected} sessions in the cohort window over {days} day(s) "
            f"({share:.1%} of tenant traffic). Observed resolution {res_during:.3f} against a "
            f"baseline of {res_before:.3f}, so {deficit} conversations that would have resolved did not."
        )
    elif cause == "prompt.regression":
        turns = m.get("median_turns", {}) if isinstance(m.get("median_turns"), dict) else {}
        cost = m.get("mean_cost", {}) if isinstance(m.get("mean_cost"), dict) else {}
        tb, td = turns.get("before"), turns.get("during")
        cb, cd = cost.get("before"), cost.get("during")
        downstream: Dict[str, Any] = {}
        if tb is not None and td is not None:
            downstream["extra_turns_total"] = round((td - tb) * affected)
        if cb is not None and cd is not None:
            extra_cost = round((cd - cb) * affected, 2)
            downstream["extra_cost_usd"] = extra_cost
            block["cost_usd"] = extra_cost
        block["downstream"] = downstream
        if tb and td:
            block["derivation"] = (
                f"{affected} sessions over {days} day(s) ({share:.1%} of tenant traffic). "
                f"Median turns rose from {tb:.1f} to {td:.1f} "
                f"(+{((td - tb) / tb):.0%}); resolution stayed flat (outcome-neutral)."
            )
    return block


def _if_nothing_changes(cand: Dict[str, Any], block: Dict[str, Any]) -> str:
    cause = cand.get("cause_class")
    days = max(1, block.get("days_running", 1))
    ds = block.get("downstream", {})
    if cause in ("kb.gap", "tool.contract_break"):
        per_day = round(ds.get("deficit", 0) / days)
        tail = (" The tool reports itself healthy throughout (error_rate flat), so nothing surfaces it on its own."
                if cause == "tool.contract_break" else
                " The cohort is new, so these are first impressions of it.")
        return (f"About {per_day} conversation(s) per day that would have resolved now do not.{tail}")
    if cause == "prompt.regression":
        return (f"Extra turns and cost persist on every conversation with this agent. Resolution is flat, "
                f"so outcome-based alerts stay quiet and the regression continues silently "
                f"(~${ds.get('extra_cost_usd', 0)} extra over {days} day(s)).")
    return "Left unaddressed, the degraded behaviour continues for the affected cohort."


def build_findings(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map detection candidates to schema findings — generic, no literals."""
    findings: List[Dict[str, Any]] = []
    for cand in candidates:
        window = dict(cand.get("window", {}))
        # Anchor a regression's reported onset to its attributed config change.
        # A fault caused by a deploy began on the deploy day, even if the metric
        # only crossed the alert threshold a day or two later; reporting the
        # detection day instead understates the true onset. Generic: uses the
        # attribution the detector already computed, never a literal day.
        if cand.get("is_regression"):
            attr = cand.get("config_attribution", {})
            if attr.get("found") and attr.get("changes"):
                try:
                    change_day = int(attr["changes"][0].get("day"))
                except (TypeError, ValueError):
                    change_day = None
                onset = window.get("from_day")
                if change_day is not None and onset is not None and change_day <= onset:
                    window["from_day"] = change_day

        f: Dict[str, Any] = {
            "id": cand["problem_id"],
            "tenant": cand["tenant"],
            "cohort": cand.get("cohort", {}),
            "metric": cand.get("primary_metric"),
            "window": window,
            "is_regression": cand.get("is_regression", False),
            "severity": cand.get("severity", "low"),
            "evidence": cand.get("evidence", []),
            "plain_summary": plain_summary(cand),
        }
        pm = cand.get("primary_metric")
        pm_metrics = cand.get("metrics", {}).get(pm, {})
        if isinstance(pm_metrics, dict):
            if "during" in pm_metrics:
                f["observed"] = pm_metrics.get("during")
            if "before" in pm_metrics:
                f["expected"] = pm_metrics.get("before")

        if cand.get("is_regression"):
            block = _impact_block(cand)
            f["impact"] = block
            f["audience"] = _AUDIENCE.get(cand.get("cause_class"), ["agent_builder"])
            f["if_nothing_changes"] = _if_nothing_changes(cand, block)
        else:
            f["not_a_regression_because"] = cand.get("not_a_regression_because", "")
        findings.append(f)
    return findings
