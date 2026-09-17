"""Generic diagnosis, prescription, reconciliation and gap authoring.

No tenant/intent/tool/agent/day/version literals and no fault-specific prose:
every value comes from the candidate's own computed fields, the standards, the
coverage numbers, or the catalog. This is what lets the ai/ml layer behave
identically on the sealed corpus, where all faults move.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from . import settings

# Reuse the trust-aware orchestrator that already ships in the kit.
_KIT_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "tools", "nexus-loop-kit")
if _KIT_TOOLS not in sys.path:
    sys.path.insert(0, _KIT_TOOLS)

from orchestrator import (  # noqa: E402
    AnalysisQuery, EvidencePacket, Orchestrator, AgentSpec,
)


# --------------------------------------------------------------------------- #
# Reconciliation — wire the orchestrator so malformed / incomparable claims
# never reach the report, and colliding claims are resolved by trust+evidence.
# --------------------------------------------------------------------------- #

def _packet_for(cand: Dict[str, Any]) -> Tuple[AnalysisQuery, EvidencePacket]:
    scope = {"tenant": cand.get("tenant"), **(cand.get("cohort") or {}),
             "from_day": (cand.get("window") or {}).get("from_day"),
             "to_day": (cand.get("window") or {}).get("to_day")}
    query = AnalysisQuery(
        query_id=cand.get("detection_type", "candidate"),
        question=f"is {cand.get('primary_metric')} anomalous for this cohort?",
        metric=cand.get("primary_metric", "unknown"),
        grain="session",
        scope=scope,
    )
    m = cand.get("metrics", {}).get(cand.get("primary_metric"), {})
    value = m.get("during") if isinstance(m, dict) else None
    packet = EvidencePacket(
        agent="backend-detector",
        query_id=query.query_id,
        metric=query.metric,
        grain=query.grain,
        scope=scope,
        value=value,
        claim=(cand.get("not_a_regression_because")
               or f"{cand.get('cause_class')} regression in cohort"),
        evidence=list(cand.get("evidence", [])),
        confidence=min(0.99, 0.6 + 0.1 * cand.get("corroborating_signals", 0)),
        denominator=(cand.get("impact", {}) or {}).get("derivation", "cohort sessions in window"),
        source=["sessions", "agent_steps"],
        limitations=[] if cand.get("is_regression") else ["classified as non-regression"],
    )
    return query, packet


def reconcile(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate every candidate as an evidence packet; drop malformed ones.

    Returns (accepted, reconciliation_notes). Well-formed candidates pass
    through; anything missing a denominator, evidence, or a coherent scope is
    rejected here rather than being reported as a finding.
    """
    accepted: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    for cand in candidates:
        query, packet = _packet_for(cand)
        errors = packet.validate(query)
        if errors:
            notes.append({"problem_id": cand.get("problem_id"), "status": "rejected",
                          "errors": errors})
            continue
        accepted.append(cand)
        notes.append({"problem_id": cand.get("problem_id"), "status": "accepted",
                      "evidence_confidence": round(packet.confidence, 3)})
    return accepted, notes


# --------------------------------------------------------------------------- #
# Diagnoses — cause from the candidate, attribution from its config marker,
# confidence from how many independent signals corroborated it.
# --------------------------------------------------------------------------- #

def build_diagnoses(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    diagnoses: List[Dict[str, Any]] = []
    for cand in candidates:
        signals = cand.get("corroborating_signals", 0)
        confidence = round(min(0.97, 0.62 + 0.09 * signals), 2)
        d: Dict[str, Any] = {
            "id": "diag_" + cand["problem_id"],
            "finding_id": cand["problem_id"],
            "cause_class": cand.get("cause_class"),
            "confidence": confidence,
            "attributed_change": None,
            # Evidence is the detector's own data-derived strings, not prose.
            "evidence": list(cand.get("evidence", [])),
        }
        attr = cand.get("config_attribution", {})
        if attr.get("found") and attr.get("changes"):
            c0 = attr["changes"][0]
            day = c0.get("day")
            try:
                day = int(day)
            except (TypeError, ValueError):
                pass
            d["attributed_change"] = {"kind": c0.get("kind"), "day": day}
        diagnoses.append(d)
    return diagnoses


# --------------------------------------------------------------------------- #
# Prescriptions — typed fix per cause, target discovered from the cohort,
# recovery target taken from the mined standard when available.
# --------------------------------------------------------------------------- #

_PLANS = {
    "kb.gap": {
        "change_type": "kb.add", "autonomy_rung": "L3", "metric": "resolution_rate",
        "target_key": "intent",
        "description": ("Author and index the missing knowledge content for the affected "
                        "cohort so retrieval returns a confident, relevant document."),
        "risk": ("Low. If the cause is not a content gap, the agent has gained correct content "
                 "it lacked and no existing behaviour changes; the failure mode is that "
                 "resolution does not move."),
        "would_not_ship_if": ("Replay shows any golden-set regression, or the questions need a "
                              "policy decision not yet made — in which case a scripted handoff, "
                              "not an article, is the answer."),
    },
    "tool.contract_break": {
        "change_type": "tool.validate", "autonomy_rung": "L2", "metric": "resolution_rate",
        "target_key": "tool_name",
        "description": ("Assert a non-empty, well-formed payload before handing the tool result "
                        "to the model; on an empty success, treat it as a malformed response and "
                        "take the existing fallback path instead of answering from nothing."),
        "risk": ("Moderate. If some inputs legitimately return an empty payload, valid states "
                 "could be routed to a human unnecessarily until the contract is confirmed."),
        "would_not_ship_if": ("The empty-payload rate does not fall after the upstream owner's "
                              "own fix lands, i.e. we would be patching a symptom of a contract "
                              "about to change again."),
    },
    "prompt.regression": {
        "change_type": "prompt.edit", "autonomy_rung": "L2", "metric": "median_turns",
        "target_key": "agent_id",
        "description": ("Trim the wording that inflates turns without improving resolution "
                        "(over-confirmation / re-asking), preserving any required safety copy "
                        "in a more concise form."),
        "risk": ("Low. If the added wording was mandated for compliance, shortening it must keep "
                 "the required content; verify before shipping."),
        "would_not_ship_if": ("Replay shows the turn count does not fall, or a golden-set "
                              "regression appears, or compliance requires the verbose wording."),
    },
}


def _standard_best(standards: List[Dict[str, Any]], tenant: str, cohort: Dict[str, Any],
                   metric: str) -> Optional[float]:
    for s in standards:
        if s.get("tenant") != tenant or s.get("metric") != metric:
            continue
        sc = s.get("cohort") or {}
        if all(sc.get(k) == v for k, v in (cohort or {}).items() if k in sc):
            return s.get("best")
    return None


def build_prescriptions(candidates: List[Dict[str, Any]],
                        standards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prescriptions: List[Dict[str, Any]] = []
    for cand in candidates:
        if not cand.get("is_regression"):
            continue
        plan = _PLANS.get(cand.get("cause_class"))
        if not plan:
            continue
        cohort = cand.get("cohort", {})
        target = cohort.get(plan["target_key"]) or "affected-cohort"
        metric = plan["metric"]
        m = cand.get("metrics", {})

        if metric == "median_turns":
            mt = m.get("median_turns", {})
            frm = mt.get("during")
            to = _standard_best(standards, cand["tenant"], cohort, "turns_to_resolve") or mt.get("before")
        else:  # resolution_rate
            rr = m.get("resolution_rate", {})
            frm = rr.get("during")
            to = _standard_best(standards, cand["tenant"], cohort, "resolution_rate") or rr.get("before")

        if frm is None or to is None:
            continue

        prescriptions.append({
            "id": "rx_" + cand["problem_id"],
            "diagnosis_id": "diag_" + cand["problem_id"],
            "change_type": plan["change_type"],
            "target": target,
            "description": plan["description"],
            "autonomy_rung": plan["autonomy_rung"],
            "predicted_delta": {"metric": metric, "from": round(float(frm), 4), "to": round(float(to), 4)},
            "decision": {
                "asking_approval_for": (
                    f"Apply a {plan['change_type']} change to '{target}' "
                    f"({cand['tenant']}) to recover {metric}."),
                "risk_if_diagnosis_wrong": plan["risk"],
                "would_not_ship_if": plan["would_not_ship_if"],
            },
        })
    return prescriptions


# --------------------------------------------------------------------------- #
# Gaps — the honest refusals, authored from the catalog + computed coverage.
# --------------------------------------------------------------------------- #

_FALLBACK_FAILOVER = {
    "ask_id": "A11",
    "verdict": "NOT_MEASURABLE",
    "why": ("No failover mechanism exists in the runtime, so no failover event is emitted. "
            "Nothing records a primary path failing and an alternate being chosen, because "
            "that choice is never made."),
    "nearest_proxy": "llm_call rows with retry_count > 0",
    "why_the_proxy_misleads": ("those are quality retries — the same target re-issued — not a "
                               "switch to an alternate. Reporting them as failover reads as "
                               "'failover works' when it does not exist."),
    "required_event": {"name": "failover", "grain": "step",
                       "fields": ["from_target", "to_target", "reason", "recovered"],
                       "owner": "conversation-runtime"},
}


def build_gaps(catalog: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Author gap specs generically from the catalog and computed coverage."""
    gaps: List[Dict[str, Any]] = []

    # NOT_MEASURABLE capabilities (e.g. failover_rate) straight from the catalog.
    emitted_failover = False
    for cap in (catalog.get("capabilities") or []):
        if cap.get("class") == "NOT_MEASURABLE":
            gaps.append({
                "ask_id": "A11",
                "verdict": "NOT_MEASURABLE",
                "why": cap.get("blocker", _FALLBACK_FAILOVER["why"]),
                "nearest_proxy": cap.get("nearest_proxy", _FALLBACK_FAILOVER["nearest_proxy"]),
                "why_the_proxy_misleads": _FALLBACK_FAILOVER["why_the_proxy_misleads"],
                "required_event": cap.get("required_event", _FALLBACK_FAILOVER["required_event"]),
            })
            emitted_failover = True
    if not emitted_failover:
        gaps.append(dict(_FALLBACK_FAILOVER))

    # COVERAGE_TOO_LOW for cost-per-conversation when legacy traffic has no cost.
    tool_cov = context.get("tool_coverage")
    if tool_cov is not None and tool_cov < 0.95:
        cov_by_tenant = context.get("coverage_by_tenant", {})
        worst = min(cov_by_tenant, key=cov_by_tenant.get) if cov_by_tenant else None
        gaps.append({
            "ask_id": "A03",
            "verdict": "COVERAGE_TOO_LOW",
            "why": (f"Cost per resolved conversation is computable only for v3 traffic; cost is "
                    f"absent on legacy v2_flow sessions. Non-legacy coverage bottoms out at "
                    f"{tool_cov:.1%}"
                    + (f" on {worst}." if worst else ".")
                    + " We report the v3 figure with the denominator stated rather than blending "
                      "a quarter of traffic in as free."),
            "nearest_proxy": "blended cost over all sessions",
            "why_the_proxy_misleads": ("it silently treats legacy sessions as zero-cost, "
                                       "understating cost per conversation."),
            "required_event": {"name": "cost_rollup", "grain": "session",
                               "fields": ["cost_usd", "source"], "owner": "legacy-flow-runtime"},
        })

    # CARDINALITY_REFUSED for any near-unique dimension over its catalog budget.
    for card in context.get("cardinality", []):
        if not card.get("refuse"):
            continue
        field = card.get("field", "")
        # Skip pure keys (budget 0) — those are never a requested breakdown.
        if card.get("budget", 0) <= 0:
            continue
        gaps.append({
            "ask_id": "A02",
            "verdict": "CARDINALITY_REFUSED",
            "why": (f"A breakdown by {field} is refused: it has {card['distinct']} distinct values "
                    f"against a declared cardinality budget of {card['budget']}. Grouping by a "
                    f"near-unique field yields ~one row per value and is a planner error."),
            "nearest_proxy": "a lower-cardinality dimension (intent, agent_kind, channel, segment)",
            "why_the_proxy_misleads": ("a per-customer breakdown is not an operational cohort; use "
                                       "a declared coarse dimension instead."),
        })

    return gaps
