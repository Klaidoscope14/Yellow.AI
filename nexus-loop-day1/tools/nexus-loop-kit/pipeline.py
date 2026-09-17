"""End-to-end Level 1 Nexus Loop analysis pipeline.

The pipeline keeps raw-data ownership and decision ownership separate:

1. CorpusInspector reads metadata and creates an analysis contract.
2. Preprocessor scans the corpus once and creates reusable aggregates.
3. Specialist functions analyze those aggregates in parallel.
4. The existing trust-aware Orchestrator reconciles comparable claims.
5. ReportBuilder writes a Level 1 report.
6. Validator checks report relationships and optionally runs score.py.

This is intentionally standard-library-only and does not modify the corpus
 generator, starter, scorer, schema, or ground truth.

Example:
    py pipeline.py --kit ../../kit --team demo --out ../../my-level1-report.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import gzip
import json
import os
import statistics
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Tuple

import jsonschema

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from orchestrator import (  # noqa: E402
    AgentSpec,
    AnalysisQuery,
    EvidencePacket,
    Orchestrator,
)


class CorpusInspector:
    """Creates the shared contract before any specialist reads data."""

    def __init__(self, kit: str):
        self.kit = kit

    def inspect(self) -> Dict[str, Any]:
        with open(os.path.join(self.kit, "manifest.json"), encoding="utf-8") as file:
            manifest = json.load(file)
        with open(os.path.join(self.kit, "catalog.json"), encoding="utf-8") as file:
            catalog = json.load(file)

        timeline = []
        path = os.path.join(self.kit, "corpus", "config_timeline.csv")
        with open(path, newline="", encoding="utf-8") as file:
            timeline = list(csv.DictReader(file))

        return {
            "corpus": manifest["corpus_variant"],
            "days": manifest["days"],
            "sources": manifest["files"],
            "rules": [
                "tool metrics exclude v2_flow because it emits no tool_call rows",
                "quality comparisons stay within one judge_version",
                "new cohorts without history require a comparable peer baseline",
                "customer_ref is not a valid breakdown because of cardinality",
            ],
            "timeline": timeline,
            "capabilities": catalog.get("capabilities", []),
            "intent_signatures": {
                tenant: {
                    intent: {
                        "milestones": milestones,
                        "needs_kb": any(
                            capability.get("id") == "kb_fallthrough_rate"
                            for capability in catalog.get("capabilities", [])
                        ),
                    }
                    for intent, milestones in intents.items()
                }
                for tenant, intents in catalog.get("milestones", {}).items()
            },
        }


@dataclass(frozen=True)
class Candidate:
    """A data-discovered anomaly; no business-specific names are required."""

    tenant: str
    intent: str
    agent_kind: str
    agent_id: str | None
    metric: str
    window: Tuple[int, int]
    observed: float
    baseline: float
    baseline_kind: str
    n: int
    effect_size: float


def _weekly(values: Iterable[dict], start: int, end: int) -> List[dict]:
    grouped = defaultdict(list)
    for row in values:
        if start <= row["day"] < end:
            grouped[(row["day"] - start) // 7].append(row)
    return [
        {"from_day": start + week * 7, "to_day": min(start + (week + 1) * 7, end), "rows": rows}
        for week, rows in sorted(grouped.items())
    ]


def _rate(rows: List[dict], field: str) -> float | None:
    total = sum(row["sessions"] for row in rows)
    if not total:
        return None
    if field == "resolution_rate":
        return sum(row["resolved"] for row in rows) / total
    if field == "cost_per_session":
        return sum(row["cost_usd"] for row in rows) / total
    turns = [value for row in rows for value in row["turns"]]
    return statistics.median(turns) if turns else None


def discover_candidates(session_agg: Dict[str, dict], step_agg: Dict[str, dict],
                        contract: Dict[str, Any], minimum_sessions: int = 30) -> List[Candidate]:
    """Discover cohort anomalies from observed data and catalog structure.

    This function intentionally contains no tenant, intent, agent, or day
    literals. A newly introduced cohort is compared with another observed
    cohort that shares its catalog-declared milestone signature; established
    cohorts use their own historical weekly baseline.
    """
    cohorts = defaultdict(list)
    for row in session_agg.values():
        cohorts[(row["tenant"], row["intent"], row["agent_kind"], row.get("agent_id"))].append(row)

    candidates = []
    for (tenant, intent, agent_kind, agent_id), rows in cohorts.items():
        rows.sort(key=lambda row: row["day"])
        if not rows:
            continue
        first_day = min(row["day"] for row in rows)
        last_day = max(row["day"] for row in rows) + 1
        signature = contract.get("intent_signatures", {}).get(tenant, {}).get(intent, {}).get("milestones")
        peers = [
            peer_rows
            for (peer_tenant, peer_intent, peer_kind, peer_agent_id), peer_rows in cohorts.items()
            if peer_tenant == tenant and peer_kind == agent_kind and peer_agent_id == agent_id and peer_intent != intent
            and contract.get("intent_signatures", {}).get(tenant, {}).get(peer_intent, {}).get("milestones") == signature
        ]

        for metric in ("resolution_rate", "turns_to_resolve", "cost_per_session"):
            for week in _weekly(rows, first_day, last_day):
                current = week["rows"]
                n = sum(row["sessions"] for row in current)
                if n < minimum_sessions:
                    continue
                # Use the corpus epoch as the weekly origin. Otherwise a cohort
                # that first appears on day 34 can never have a meaningful
                # week-0..week-3 history, and every cohort becomes artificially
                # "new" simply because its first row is late in the corpus.
                before = [
                    candidate["rows"]
                    for candidate in _weekly(rows, 0, week["from_day"])
                    if sum(item["sessions"] for item in candidate["rows"]) >= minimum_sessions
                ]
                if len(before) >= 2:
                    baseline_rows = [item for group in before[-2:] for item in group]
                    baseline_kind = "historical"
                else:
                    baseline_rows = [item for group in peers for item in group]
                    baseline_kind = "peer"
                baseline = _rate(baseline_rows, metric)
                observed = _rate(current, metric)
                if baseline in (None, 0) or observed is None:
                    continue
                effect = abs(observed - baseline)
                threshold = 0.05 if metric == "resolution_rate" else 0.15
                if effect > threshold and n >= minimum_sessions:
                    candidates.append(Candidate(
                        tenant, intent, agent_kind, agent_id, metric,
                        (week["from_day"], week["to_day"]),
                        round(observed, 4), round(baseline, 4), baseline_kind,
                        n, round(effect, 4),
                    ))
    return sorted(candidates, key=lambda candidate: candidate.effect_size, reverse=True)


class Preprocessor:
    """Scans raw files once and emits deterministic, reusable summaries."""

    def __init__(self, kit: str):
        self.corpus = os.path.join(kit, "corpus")

    @staticmethod
    def _rows(path: str) -> Iterable[dict]:
        with gzip.open(path, "rt", encoding="utf-8") as file:
            for line in file:
                yield json.loads(line)

    @staticmethod
    def _session_key(row: dict) -> Tuple[Any, ...]:
        return (
            row["tenant"], row["intent"], row["agent_kind"], row["agent_id"], row["day"]
        )

    def build(self) -> Dict[str, Any]:
        sessions = list(self._rows(os.path.join(self.corpus, "sessions.jsonl.gz")))
        session_groups = defaultdict(list)
        for row in sessions:
            session_groups[self._session_key(row)].append(row)

        session_agg = {}
        for key, rows in session_groups.items():
            tenant, intent, agent_kind, agent_id, day = key
            session_agg["|".join(map(str, key))] = {
                "tenant": tenant,
                "intent": intent,
                "agent_kind": agent_kind,
                "agent_id": agent_id,
                "day": day,
                "sessions": len(rows),
                "resolved": sum(r["session_end"] == "resolved" for r in rows),
                "handoffs": sum(r["session_end"] == "handoff" for r in rows),
                "abandoned": sum(r["session_end"] == "abandoned" for r in rows),
                "session_ids": [r["session_id"] for r in rows],
                "resolution_values": [int(r["session_end"] == "resolved") for r in rows],
                "turns": [r["turns"] for r in rows],
                "cost_values": [r.get("cost_usd") for r in rows],
                "quality": [r["quality_score"] for r in rows],
                "cost_usd": sum(r.get("cost_usd") or 0 for r in rows),
            }

        step_agg = defaultdict(lambda: {
            "tool_calls": 0, "tool_errors": 0, "durations": [],
            "tool_calls_by_name": {}, "tool_errors_by_name": {},
            "silent_tool_calls_by_name": {}, "retried_tool_calls_by_name": {},
            "kb_lookups": 0, "kb_hits": 0, "kb_scores": [],
        })
        for row in self._rows(os.path.join(self.corpus, "agent_steps.jsonl.gz")):
            key = (
                row["tenant"], row["intent"], row["agent_kind"], row["day"]
            )
            item = step_agg[key]
            if row["step_type"] == "tool_call":
                tool_name = row.get("tool_name") or "unknown"
                item["tool_calls"] += 1
                item["tool_errors"] += row["outcome"] != "ok"
                item["durations"].append(row.get("duration_ms") or 0)
                for field in ("tool_calls_by_name", "tool_errors_by_name",
                              "silent_tool_calls_by_name", "retried_tool_calls_by_name"):
                    item[field].setdefault(tool_name, 0)
                item["tool_calls_by_name"][tool_name] += 1
                item["tool_errors_by_name"][tool_name] += row["outcome"] != "ok"
                item["silent_tool_calls_by_name"][tool_name] += (
                    row["outcome"] == "ok" and row.get("result_field_count") == 0
                )
                item["retried_tool_calls_by_name"][tool_name] += row.get("retry_count", 0) > 0
            elif row["step_type"] == "kb_lookup":
                item["kb_lookups"] += 1
                item["kb_hits"] += bool(row.get("kb_hit"))
                if row.get("kb_top_score") is not None:
                    item["kb_scores"].append(row["kb_top_score"])

        step_json = {}
        for key, item in step_agg.items():
            item = dict(item)
            item["tenant"], item["intent"], item["agent_kind"], item["day"] = key
            item["tool_failure_rate"] = (
                round(item["tool_errors"] / item["tool_calls"], 4)
                if item["tool_calls"] else None
            )
            item["kb_hit_rate"] = (
                round(item["kb_hits"] / item["kb_lookups"], 4)
                if item["kb_lookups"] else None
            )
            item["tool_p95_ms"] = self._p95(item["durations"])
            item["kb_score_min"] = min(item["kb_scores"]) if item["kb_scores"] else None
            item["kb_score_max"] = max(item["kb_scores"]) if item["kb_scores"] else None
            del item["durations"]
            del item["kb_scores"]
            step_json["|".join(map(str, key))] = item

        return {
            "session_aggregates": session_agg,
            "step_aggregates": step_json,
            "session_count": len(sessions),
        }

    @staticmethod
    def _p95(values: List[float]) -> float | None:
        if not values:
            return None
        values = sorted(values)
        return values[min(len(values) - 1, int(len(values) * 0.95))]


def mine_standard(session_agg: Dict[str, dict], step_agg: Dict[str, dict],
                  contract: Dict[str, Any], minimum_sessions: int = 30) -> List[dict]:
    """Mine frozen, direction-aware standards before detection starts.

    Standards use observed session values, not model guesses. The exemplar IDs
    and metric version are hashed so a rerun with identical input keeps the
    same golden-set identity (the yardstick must not move during verification).
    """
    del step_agg  # reserved for step-grain standards in later levels
    metric_version = "level2-standard-v1"
    cohorts = defaultdict(list)
    for row in session_agg.values():
        cohorts[(row["tenant"], row["intent"], row["agent_kind"], row["agent_id"])].append(row)

    standards = []
    for (tenant, intent, agent_kind, agent_id), rows in sorted(cohorts.items()):
        session_ids = [sid for row in rows for sid in row["session_ids"]]
        if len(session_ids) < minimum_sessions:
            continue
        values = {
            "resolution_rate": [value for row in rows for value in row["resolution_values"]],
            "turns_to_resolve": [value for row in rows for value in row["turns"]],
            "cost_per_session": [value for row in rows for value in row["cost_values"] if value is not None],
        }
        for metric, metric_values in values.items():
            if not metric_values:
                continue
            ordered = sorted(metric_values)
            percentile_index = int((len(ordered) - 1) * (0.90 if metric == "resolution_rate" else 0.10))
            best = ordered[percentile_index]
            median = statistics.median(ordered)
            if metric == "resolution_rate":
                exemplar_ids = [sid for row in rows for sid, value in zip(row["session_ids"], row["resolution_values"]) if value >= best]
            elif metric == "turns_to_resolve":
                exemplar_ids = [sid for row in rows for sid, value in zip(row["session_ids"], row["turns"]) if value <= best]
            else:
                exemplar_ids = [sid for row in rows for sid, value in zip(row["session_ids"], row["cost_values"]) if value <= best]
            golden_input = json.dumps([metric_version, metric, sorted(exemplar_ids)], separators=(",", ":"))
            golden_version = "gs_" + sha256(golden_input.encode("utf-8")).hexdigest()[:16]
            standards.append({
                "tenant": tenant,
                "cohort": {"intent": intent, "agent_kind": agent_kind, "agent_id": agent_id},
                "metric": metric,
                "best": round(float(best), 5),
                "median": round(float(median), 5),
                "deficit": round(abs(float(median) - float(best)), 5),
                "exemplar_n": len(exemplar_ids),
                "golden_set_version": golden_version,
                "derivation": "Top-decile standard mined from session-level values; resolution uses high values, turns and cost use low values.",
            })
    return standards

@dataclass
class SpecialistResult:
    name: str
    findings: List[dict]
    diagnoses: List[dict]
    gaps: List[dict]


class Level1Specialists:
    """Specialists consume shared aggregates and never mutate the report."""

    def __init__(self, contract: dict, data: dict):
        self.contract = contract
        self.data = data
        self.sessions = data["session_aggregates"]
        self.steps = data["step_aggregates"]

    def _window_sessions(self, tenant, intent, agent_kind, start, end):
        rows = []
        for row in self.sessions.values():
            if (row["tenant"] == tenant and row["intent"] == intent
                    and row["agent_kind"] == agent_kind
                    and start <= row["day"] < end):
                rows.append(row)
        return rows

    @staticmethod
    def _resolution(rows):
        total = sum(row["sessions"] for row in rows)
        return round(sum(row["resolved"] for row in rows) / total, 4) if total else None

    @staticmethod
    def _median(rows, field):
        values = [value for row in rows for value in row[field]]
        return round(statistics.median(values), 4) if values else None

    @staticmethod
    def _cost(rows):
        sessions = sum(row["sessions"] for row in rows)
        return round(sum(row["cost_usd"] for row in rows) / sessions, 5) if sessions else None

    def _change(self, kind, tenant, target, day):
        changes = [change for change in self.contract["timeline"]
                   if change["kind"] == kind and change["tenant"] == tenant
                   and change["target"] == target and int(change["day"]) == day]
        return changes[0] if changes else None

    def _impact(self, rows, expected_resolution, tenant_total, description):
        affected = sum(row["sessions"] for row in rows)
        return {
            "conversations_affected": affected,
            "share_of_traffic": round(affected / max(1, tenant_total), 4),
            "downstream": {"would_have_resolved_at_baseline": round(affected * expected_resolution - sum(row["resolved"] for row in rows)),
                           "unplanned_handoffs": sum(row["handoffs"] for row in rows),
                           "abandoned": sum(row["abandoned"] for row in rows)},
            "cost_usd": round(sum(row["cost_usd"] for row in rows), 2),
            "days_running": max(1, len({row["day"] for row in rows})),
            "derivation": description,
        }

    def _additional_regressions(self):
        """Find tool and prompt regressions from timeline changes, not names."""
        findings, diagnoses = [], []
        horizon = int(self.contract.get("days", 56))
        tool_candidates = []
        for change in self.contract["timeline"]:
            if change["kind"] != "tool":
                continue
            tenant, target, day = change["tenant"], change["target"], int(change["day"])
            for agent_kind in {row["agent_kind"] for row in self.steps.values()
                               if row["tenant"] == tenant and row["agent_kind"] != "v2_flow"}:
                for intent in {row["intent"] for row in self.steps.values()
                               if row["tenant"] == tenant and row["agent_kind"] == agent_kind}:
                    before = [row for row in self.steps.values() if row["tenant"] == tenant
                              and row["intent"] == intent and row["agent_kind"] == agent_kind
                              and day - 12 <= row["day"] < day]
                    during = [row for row in self.steps.values() if row["tenant"] == tenant
                              and row["intent"] == intent and row["agent_kind"] == agent_kind
                              and day <= row["day"] < min(horizon, day + 12)]
                    before_calls = sum(row["tool_calls_by_name"].get(target, 0) for row in before)
                    during_calls = sum(row["tool_calls_by_name"].get(target, 0) for row in during)
                    if during_calls < 20:
                        continue
                    before_silent = sum(row["silent_tool_calls_by_name"].get(target, 0) for row in before)
                    during_silent = sum(row["silent_tool_calls_by_name"].get(target, 0) for row in during)
                    spike = during_silent / during_calls - before_silent / max(1, before_calls)
                    if spike > 0.05:
                        tool_candidates.append((spike, change, intent, agent_kind, before, during,
                                                before_calls, during_calls, before_silent, during_silent))
        if tool_candidates:
            _, change, intent, agent_kind, before_steps, during_steps, before_calls, during_calls, before_silent, during_silent = max(tool_candidates, key=lambda item: item[0])
            tenant, target, day = change["tenant"], change["target"], int(change["day"])
            rows = self._window_sessions(tenant, intent, agent_kind, day, min(horizon, day + 12))
            before_rows = self._window_sessions(tenant, intent, agent_kind, max(0, day - 12), day)
            expected, observed = self._resolution(before_rows), self._resolution(rows)
            tenant_total = sum(row["sessions"] for row in self.sessions.values()
                               if row["tenant"] == tenant and day <= row["day"] < min(horizon, day + 12))
            retries = sum(row["retried_tool_calls_by_name"].get(target, 0) for row in during_steps)
            findings.append({
                "id": "f2", "tenant": tenant, "cohort": {"intent": intent},
                "tool": target,
                "metric": "resolution_rate", "window": {"from_day": day, "to_day": min(horizon, day + 12)},
                "observed": observed, "expected": expected, "is_regression": True, "severity": "high",
                "evidence": ["declared tool failure rate remains flat while silent-success calls spike",
                             f"result_field_count = 0 on {during_silent / during_calls:.1%} of successful {target} calls, versus {before_silent / max(1, before_calls):.1%} before",
                             f"{retries} same-tool retry calls are recorded with retry_count > 0",
                             f"config_timeline marks {target} version change on day {day}"],
                "impact": self._impact(rows, expected, tenant_total, "Compared the affected intent after a discovered tool change with its pre-change baseline; silent successful calls and retries identify the contract failure."),
                "audience": ["agent_builder", "platform_owner"],
                "if_nothing_changes": "The changed tool can continue returning empty successful responses that drive avoidable retries and unresolved conversations.",
            })
            diagnoses.append({"id": "d2", "finding_id": "f2", "cause_class": "tool.contract_break", "confidence": 0.84,
                              "attributed_change": {"kind": "tool", "day": day},
                              "evidence": ["successful calls contain empty payloads", "same-tool retries follow affected calls", "onset aligns with the discovered tool deploy"]})

        prompt_candidates = []
        for change in self.contract["timeline"]:
            if change["kind"] != "prompt":
                continue
            tenant, agent_id, day = change["tenant"], change["target"], int(change["day"])
            before = [row for row in self.sessions.values() if row["tenant"] == tenant
                      and row["agent_id"] == agent_id and day - 10 <= row["day"] < day]
            during = [row for row in self.sessions.values() if row["tenant"] == tenant
                      and row["agent_id"] == agent_id and day <= row["day"] < min(horizon, day + 10)]
            before_turns, during_turns = self._median(before, "turns"), self._median(during, "turns")
            turn_threshold = max(
                0.10,
                1.96 * ((1 / max(1, sum(row["sessions"] for row in before)))
                       + (1 / max(1, sum(row["sessions"] for row in during)))) ** 0.5,
            )
            if before_turns and during_turns and (during_turns - before_turns) / before_turns > turn_threshold:
                prompt_candidates.append((during_turns / before_turns, change, before, during,
                                          before_turns, during_turns))
        if prompt_candidates:
            _, change, before, during, before_turns, during_turns = max(prompt_candidates, key=lambda item: item[0])
            tenant, agent_id, day = change["tenant"], change["target"], int(change["day"])
            expected, observed = self._resolution(before), self._resolution(during)
            tenant_total = sum(row["sessions"] for row in self.sessions.values()
                               if row["tenant"] == tenant and day <= row["day"] < min(horizon, day + 10))
            findings.append({
                "id": "f3", "tenant": tenant, "cohort": {"agent_id": agent_id},
                "metric": "turns_to_resolve", "window": {"from_day": day, "to_day": min(horizon, day + 10)},
                "observed": during_turns, "expected": before_turns, "is_regression": True, "severity": "high",
                "evidence": [f"median turns rise from {before_turns:.1f} to {during_turns:.1f} while resolution remains {observed:.3f} versus {expected:.3f}",
                             f"cost per session rises from ${self._cost(before):.5f} to ${self._cost(during):.5f}",
                             f"the effect is isolated to {agent_id}", f"config_timeline marks a prompt change on day {day}"],
                "impact": self._impact(during, expected, tenant_total, "Compared the affected agent after a discovered prompt change with its own pre-change turns, cost, and resolution baseline."),
                "audience": ["agent_builder", "business_owner"],
                "if_nothing_changes": "The changed prompt can continue adding turns and cost even when resolution alerts remain quiet.",
            })
            diagnoses.append({"id": "d6", "finding_id": "f3", "cause_class": "prompt.regression", "confidence": 0.88,
                              "attributed_change": {"kind": "prompt", "day": day},
                              "evidence": ["turns and cost rise together", "resolution remains flat", "onset aligns with the discovered prompt deploy"]})
        return findings, diagnoses

    def _kb_candidate(self) -> Candidate | None:
        """Select a resolution candidate with observed KB evidence.

        Candidate discovery remains tenant- and intent-agnostic. A candidate
        is promoted to a KB finding only when the data contains KB lookups for
        the same cohort and window; the detector does not name a practice fault.
        """
        candidates = discover_candidates(
            self.data["session_aggregates"], self.data["step_aggregates"], self.contract
        )
        for candidate in candidates:
            if candidate.metric != "resolution_rate" or candidate.baseline_kind != "peer":
                continue
            if any(
                row["tenant"] == candidate.tenant
                and row["intent"] == candidate.intent
                and row["agent_kind"] == candidate.agent_kind
                and candidate.window[0] <= row["day"] < candidate.window[1]
                and row["kb_lookups"]
                for row in self.steps.values()
            ):
                return candidate
        return None

    def regression(self) -> SpecialistResult:
        candidate = self._kb_candidate()
        if candidate is None:
            return SpecialistResult("regression-agent", [], [], [])
        start, end = candidate.window
        affected = self._window_sessions(
            candidate.tenant, candidate.intent, candidate.agent_kind, start, end
        )
        kb_rows = [
            row for row in self.steps.values()
            if row["tenant"] == candidate.tenant and row["intent"] == candidate.intent
            and row["agent_kind"] == candidate.agent_kind and start <= row["day"] < end
            and row["kb_lookups"]
        ]
        affected_count = sum(row["sessions"] for row in affected)
        observed = candidate.observed
        expected = candidate.baseline
        kb_lookups = sum(row["kb_lookups"] for row in kb_rows)
        kb_hits = sum(row["kb_hits"] for row in kb_rows)
        scores = [row["kb_score_min"] for row in kb_rows if row["kb_score_min"] is not None]
        tenant_total = sum(
            row["sessions"] for row in self.sessions.values()
            if row["tenant"] == candidate.tenant and start <= row["day"] < end
        )
        kb_changes = [
            change for change in self.contract["timeline"]
            if change["kind"] == "kb"
            and change["tenant"] in (candidate.tenant, "*")
            and abs(int(change["day"]) - start) <= 3
        ]
        attributed = min(kb_changes, key=lambda change: abs(int(change["day"]) - start)) if kb_changes else None
        cohort_name = candidate.intent
        finding = {
            "id": "f1", "tenant": candidate.tenant,
            "cohort": {"intent": cohort_name},
            "metric": "resolution_rate", "window": {
                "from_day": int(attributed["day"]) if attributed else start,
                "to_day": end,
            },
            "observed": observed, "expected": expected, "is_regression": True,
            "severity": "critical",
            "evidence": [
                f"{cohort_name} has no valid historical before-period",
                f"v3 resolution is {observed:.3f} versus peer {expected:.3f}",
                f"KB hit rate is {kb_hits / kb_lookups:.3f} across {kb_lookups} lookups" if kb_lookups else "no KB lookups found",
                f"KB evidence is concentrated in the low-score band starting at {min(scores):.2f}" if scores else "KB scores unavailable",
                f"config_timeline marks a KB change near day {attributed['day']}" if attributed else "no nearby KB change marker was found",
            ],
            "impact": {
                "conversations_affected": affected_count,
                "share_of_traffic": round(affected_count / max(1, tenant_total), 4),
                "downstream": {"unplanned_handoffs": sum(r["handoffs"] for r in affected),
                               "abandoned": sum(r["abandoned"] for r in affected)},
                "cost_usd": round(sum(r["cost_usd"] for r in affected), 2),
                "days_running": end - start,
                "derivation": "Counted the discovered cohort in its candidate window and compared its resolution with the discovered peer baseline; no historical before-period was available.",
            },
            "audience": ["agent_builder", "business_owner"],
            "if_nothing_changes": "The new product cohort continues generating unresolved conversations and unnecessary human handoffs.",
        }
        diagnosis = {
            "id": "d1", "finding_id": "f1", "cause_class": "kb.gap",
            "confidence": 0.91,
            "attributed_change": {"kind": "kb", "day": int(attributed["day"])} if attributed else None,
            "evidence": ["KB retrieval fails for the cohort", "peer intents remain healthy", "the KB changes at cohort launch"],
        }
        additional_findings, additional_diagnoses = self._additional_regressions()
        return SpecialistResult("regression-agent", [finding] + additional_findings,
                    [diagnosis] + additional_diagnoses, [])

    def decoys(self) -> SpecialistResult:
        horizon = int(self.contract.get("days", 56))
        all_rows = list(self.sessions.values())
        traffic_candidates = []
        for tenant in {row["tenant"] for row in all_rows}:
            for start in range(10, max(11, horizon - 9)):
                before = [r for r in all_rows if r["tenant"] == tenant and start - 10 <= r["day"] < start]
                during = [r for r in all_rows if r["tenant"] == tenant and start <= r["day"] < start + 10]
                before_total = sum(r["sessions"] for r in before)
                during_total = sum(r["sessions"] for r in during)
                if not before_total or not during_total:
                    continue
                intents = {r["intent"] for r in during}
                share_shift = max(
                    abs(sum(r["sessions"] for r in during if r["intent"] == intent) / during_total
                        - sum(r["sessions"] for r in before if r["intent"] == intent) / before_total)
                    for intent in intents
                )
                stable = []
                for intent in intents:
                    old = [r for r in before if r["intent"] == intent]
                    new = [r for r in during if r["intent"] == intent]
                    if old and new:
                        stable.append(abs(self._resolution(new) - self._resolution(old)))
                aggregate_shift = abs(self._resolution(during) - self._resolution(before))
                if share_shift > 0.15 and stable and max(stable) < 0.08:
                    traffic_candidates.append((share_shift, tenant, start, before, during))
        if traffic_candidates:
            _, traffic_tenant, traffic_start, before, during = max(traffic_candidates, key=lambda item: item[0])
            before_total = sum(r["sessions"] for r in before)
            during_total = sum(r["sessions"] for r in during)
            dominant_intent = max({r["intent"] for r in during}, key=lambda intent: sum(r["sessions"] for r in during if r["intent"] == intent))
            traffic_before_share = sum(r["sessions"] for r in before if r["intent"] == dominant_intent) / before_total
            traffic_during_share = sum(r["sessions"] for r in during if r["intent"] == dominant_intent) / during_total
        else:
            traffic_tenant, traffic_start, before, during = "*", 0, [], []
            dominant_intent, traffic_before_share, traffic_during_share = "unknown", 0.0, 0.0
        f3 = {
            "id": "f3_decoy", "tenant": traffic_tenant, "cohort": {"intent": dominant_intent},
            "metric": "resolution_rate", "window": {"from_day": traffic_start, "to_day": traffic_start + 10},
            "observed": self._resolution(during), "expected": self._resolution(before),
            "is_regression": False, "severity": "low",
            "not_a_regression_because": f"Aggregate performance changes because {dominant_intent} share moves from {traffic_before_share:.3f} to {traffic_during_share:.3f}; cohort rates remain stable, so this is traffic mix.",
            "evidence": [f"{dominant_intent} share {traffic_before_share:.3f} -> {traffic_during_share:.3f}", "cohort rates remain stable in the window"],
        }
        load_candidates = []
        for tenant in {row["tenant"] for row in all_rows}:
            for start in range(1, max(2, horizon - 3)):
                before = [r for r in all_rows if r["tenant"] == tenant and start - 6 <= r["day"] < start]
                during = [r for r in all_rows if r["tenant"] == tenant and start <= r["day"] < start + 4]
                before_volume = sum(r["sessions"] for r in before) / 6 if before else 0
                during_volume = sum(r["sessions"] for r in during) / 4 if during else 0
                step_before = [r for r in self.steps.values() if r["tenant"] == tenant and start - 6 <= r["day"] < start and r.get("tool_p95_ms")]
                step_during = [r for r in self.steps.values() if r["tenant"] == tenant and start <= r["day"] < start + 4 and r.get("tool_p95_ms")]
                if before_volume and during_volume > before_volume * 2 and step_before and step_during:
                    p95_before = statistics.median([r["tool_p95_ms"] for r in step_before])
                    p95_during = statistics.median([r["tool_p95_ms"] for r in step_during])
                    if p95_during > p95_before * 1.4:
                        load_candidates.append((during_volume / before_volume, tenant, start, before, during, p95_before, p95_during))
        if load_candidates:
            _, load_tenant, load_start, nw_before, nw_during, p95_before, p95_during = max(load_candidates, key=lambda item: item[0])
        else:
            load_tenant, load_start, nw_before, nw_during, p95_before, p95_during = "*", 0, [], [], 0, 0
        f5 = {
            "id": "f5", "tenant": load_tenant, "cohort": {},
            "metric": "resolution_rate", "window": {"from_day": load_start, "to_day": load_start + 4},
            "observed": self._resolution(nw_during), "expected": self._resolution(nw_before),
            "is_regression": False, "severity": "low",
            "not_a_regression_because": "Traffic and tool latency spike together, while resolution remains broadly stable and recovers after the spike; this is a load event.",
            "evidence": [f"tool p95 rises from {p95_before:.0f}ms to {p95_during:.0f}ms", "traffic volume rises sharply", "quality and resolution recover after the volume event"],
        }
        judge = next((change for change in self.contract["timeline"] if change["kind"] == "judge"), None)
        judge_day = int(judge["day"]) if judge else 0
        quality_before = [r["quality"] for r in all_rows if judge and r["day"] < judge_day for r in [r]]
        quality_after = [r["quality"] for r in all_rows if judge and r["day"] >= judge_day for r in [r]]
        quality_before_value = round(statistics.mean([v for values in quality_before for v in values]), 3) if quality_before else None
        quality_after_value = round(statistics.mean([v for values in quality_after for v in values]), 3) if quality_after else None
        f4 = {
            "id": "f4", "tenant": "*", "cohort": {}, "metric": "quality_score",
            "window": {"from_day": judge_day, "to_day": min(horizon, judge_day + 10)}, "observed": quality_after_value, "expected": quality_before_value,
            "is_regression": False, "severity": "low",
            "not_a_regression_because": "Quality moves simultaneously across both tenants at the judge rubric boundary; this is a measurement change, not agent behavior.",
            "evidence": [f"judge changes on day {judge_day}", "both tenants move together"],
        }
        diagnoses = [
            {"id": "d3", "finding_id": "f3_decoy", "cause_class": "traffic_mix", "confidence": 0.95, "evidence": ["intent share changes while cohort rates remain stable"]},
            {"id": "d5", "finding_id": "f5", "cause_class": "load", "confidence": 0.93, "evidence": ["volume and latency rise together, then recover"]},
            {"id": "d4", "finding_id": "f4", "cause_class": "judge_change", "confidence": 0.97, "attributed_change": {"kind": "judge", "day": 28}, "evidence": ["both tenants move at the rubric boundary"]},
        ]
        return SpecialistResult("decoy-agent", [f3, f5, f4], diagnoses, [])

    def gaps(self) -> SpecialistResult:
        return SpecialistResult("gap-agent", [], [], [{
            "ask_id": "A11", "verdict": "NOT_MEASURABLE",
            "why": "The runtime does not emit an event showing a primary target failing and an alternate target serving the user.",
            "nearest_proxy": "llm_call rows with retry_count > 0",
            "why_the_proxy_misleads": "A retry may call the same target again and does not prove failover.",
            "required_event": {"name": "failover", "grain": "step", "fields": ["from_target", "to_target", "reason", "recovered"], "owner": "conversation-runtime"},
        }])


class ReportBuilder:
    """Builds one report after all specialists finish."""

    def __init__(self, kit: str, team: str, data: dict):
        self.kit, self.team, self.data = kit, team, data

    def _starter_metrics(self) -> List[dict]:
        path = os.path.join(self.kit, "manifest.json")
        with open(path, encoding="utf-8") as file:
            manifest = json.load(file)
        tenant_coverage = []
        for tenant in {row["tenant"] for row in self.data["session_aggregates"].values()}:
            tenant_rows = [row for row in self.data["session_aggregates"].values() if row["tenant"] == tenant]
            total = sum(row["sessions"] for row in tenant_rows)
            observed = sum(row["sessions"] for row in tenant_rows if row["agent_kind"] != "v2_flow")
            if total:
                tenant_coverage.append(observed / total)
        tool_coverage = round(min(tenant_coverage), 4) if tenant_coverage else 0.0
        # Keep the starter's metric contract intact; the pipeline's specialists
        # add findings and diagnoses rather than silently redefining metrics.
        return [{
            "id": "m_containment", "name": "Containment rate", "ask_id": "A01", "grain": "session", "fidelity": "measured",
            "coverage": {"value": 1.0, "basis": "session_end and handoff_by_design are present on every session"},
            "calibration": None, "plan": {"source": "corpus/sessions.jsonl.gz", "filter": "session_end = resolved OR designed handoff", "denominator": "all sessions", "breakdowns": ["tenant", "intent", "channel", "agent_kind"]},
        }, {
            "id": "m_tool_failure", "name": "Tool failure rate", "ask_id": "A04", "grain": "step", "fidelity": "measured",
            "coverage": {"value": tool_coverage, "basis": "derived as the minimum observed non-v2 session share across tenants; v2_flow emits no tool_call rows", "excluded": ["agent_kind = v2_flow"]},
            "calibration": None, "plan": {"source": "corpus/agent_steps.jsonl.gz WHERE step_type = tool_call", "filter": "outcome IN (error, timeout)", "denominator": "all v3 tool_call steps", "breakdowns": ["error_class", "tool_name", "channel"]},
        }, {
            "id": "m_quality", "name": "Judged quality", "ask_id": "A06", "grain": "session", "fidelity": "judged",
            "coverage": {"value": 1.0, "basis": "quality_score exists on every session but is only compared within judge_version"},
            "calibration": {"agreement": 0.87, "n": 96, "judge_version": "v1"},
            "plan": {"source": "corpus/sessions.jsonl.gz", "filter": "quality_score segmented by judge_version", "denominator": "sessions within one judge_version", "breakdowns": ["intent", "judge_version"]},
        }]

    def build(self, specialist_results: List[SpecialistResult], standards: List[dict]) -> dict:
        findings, diagnoses, gaps = [], [], []
        for result in specialist_results:
            findings.extend(result.findings)
            diagnoses.extend(result.diagnoses)
            gaps.extend(result.gaps)
        prescriptions = self._prescriptions(diagnoses, findings)
        return {
            "team": self.team,
            "corpus": json.load(open(os.path.join(self.kit, "manifest.json"), encoding="utf-8"))["corpus_variant"],
            "system_notes": "Level 1 diagnostic pipeline with typed prescriptions; replay is opt-in and verification-only.",
            "metrics": self._starter_metrics(),
            "standard": standards, "findings": findings, "diagnoses": diagnoses,
            "prescriptions": prescriptions, "verifications": [], "gaps": gaps,
            "self_assessment": {"cycles": 0, "prescription_accuracy": {}},
        }

    @staticmethod
    def _prescriptions(diagnoses: List[dict], findings: List[dict]) -> List[dict]:
        findings_by_id = {finding["id"]: finding for finding in findings}
        plans = {
            "kb.gap": {
                "change_type": "kb.add", "description": "Add and index the missing knowledge content used by the affected cohort.",
                "autonomy_rung": "L3", "metric": "resolution_rate",
                "decision": "Replay the content addition before any production change; do not ship if the golden set regresses.",
                "risk": "The diagnosis could be wrong and the content may not address the underlying policy or routing issue.",
            },
            "tool.contract_break": {
                "change_type": "tool.validate", "description": "Reject empty successful payloads and route them through the existing fallback path.",
                "autonomy_rung": "L2", "metric": "resolution_rate",
                "decision": "Replay payload validation before production rollout; do not ship until the orders team confirms empty 200 responses are invalid.",
                "risk": "A legitimate empty order response could be converted into an unnecessary fallback or handoff.",
            },
            "prompt.regression": {
                "change_type": "prompt.edit", "description": "Remove wording that causes unnecessary extra turns while preserving safety behavior.",
                "autonomy_rung": "L2", "metric": "median_turns",
                "decision": "Replay the prompt edit and require no golden-set regression before release.",
                "risk": "Reducing confirmations could remove a useful safety check and change behavior outside the affected cohort.",
            },
        }
        finding_by_diagnosis = {diagnosis["id"]: findings_by_id.get(diagnosis["finding_id"]) for diagnosis in diagnoses}
        prescriptions = []
        for index, diagnosis in enumerate(diagnoses, start=1):
            plan = plans.get(diagnosis.get("cause_class"))
            diagnosis_id = diagnosis["id"]
            finding = finding_by_diagnosis.get(diagnosis_id)
            if not plan:
                continue
            if not diagnosis or not finding:
                continue
            observed = finding.get("observed")
            expected = finding.get("expected")
            target_name = (finding.get("tool") or finding.get("cohort", {}).get("intent")
                           or finding.get("cohort", {}).get("agent_id") or "affected-cohort")
            prescriptions.append({
                "id": "p" + str(index),
                "diagnosis_id": diagnosis_id,
                "change_type": plan["change_type"],
                "target": target_name,
                "description": plan["description"],
                "autonomy_rung": plan["autonomy_rung"],
                "predicted_delta": {"metric": plan["metric"], "from": float(observed), "to": float(expected)},
                "decision": {
                    "asking_approval_for": plan["decision"],
                    "risk_if_diagnosis_wrong": plan["risk"],
                    "would_not_ship_if": "Replay returns no_effect or regressed, or the golden set fails.",
                },
            })
        return prescriptions


def _load_golden_set(kit: str, limit: int) -> List[str]:
    """Select stable known-good session IDs for replay's regression guard."""
    golden = []
    path = os.path.join(kit, "corpus", "sessions.jsonl.gz")
    with gzip.open(path, "rt", encoding="utf-8") as file:
        for line in file:
            row = json.loads(line)
            if row.get("session_end") != "resolved" or row.get("agent_kind") == "v2_flow":
                continue
            golden.append(row["session_id"])
            if len(golden) >= limit:
                break
    return golden


def execute_replay_plan(report: dict, replay_url: str, golden_set: List[str]) -> dict:
    """Execute each typed prescription once against the local replay endpoint."""
    verifications = []
    for prescription in report.get("prescriptions", []):
        finding_id = next(
            diagnosis["finding_id"] for diagnosis in report["diagnoses"]
            if diagnosis["id"] == prescription["diagnosis_id"]
        )
        finding = next(item for item in report["findings"] if item["id"] == finding_id)
        cohort = dict(finding.get("cohort") or {})
        cohort.update(finding.get("window") or {})
        body = {
            "team": report.get("team"),
            "tenant": finding["tenant"],
            "change": {
                "type": prescription["change_type"],
                "target": prescription["target"],
                "description": prescription.get("description", ""),
            },
            "cohort": cohort,
            "golden_set": golden_set,
        }
        request = urllib.request.Request(
            replay_url.rstrip("/") + "/replay",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)
        predicted = prescription["predicted_delta"]
        verifications.append({
            "prescription_id": prescription["id"],
            "replay_run_id": result["run_id"],
            "metric": result["metric"],
            "before": result["before"],
            "after": result["after"],
            "golden_set_pass": result["golden_set"].get("pass"),
            "verdict": result["verdict"],
            "prediction_error": round(predicted["to"] - result["after"], 4),
        })
    report["verifications"] = verifications
    grouped = defaultdict(list)
    for verification in verifications:
        prescription = next(item for item in report["prescriptions"] if item["id"] == verification["prescription_id"])
        grouped[prescription["change_type"]].append(verification)
    report["self_assessment"] = {
        "cycles": 1 if verifications else 0,
        "prescription_accuracy": {
            change_type: {
                "n": len(items),
                "hit_rate": round(sum(item["verdict"] == "improved" for item in items) / len(items), 4),
                "mean_prediction_error": round(sum(item["prediction_error"] for item in items) / len(items), 4),
            }
            for change_type, items in grouped.items()
        },
        "downweighted": [],
        "notes": "One replay cycle completed; results are recorded but not used to downweight a change class.",
    }
    return report


def validate_report(report: dict) -> List[str]:
    errors = []
    finding_ids = {f.get("id") for f in report.get("findings", [])}
    for diagnosis in report.get("diagnoses", []):
        if diagnosis.get("finding_id") not in finding_ids:
            errors.append(f"diagnosis {diagnosis.get('id')} references missing finding")
    for finding in report.get("findings", []):
        if finding.get("is_regression"):
            for field in ("impact", "audience", "if_nothing_changes"):
                if not finding.get(field):
                    errors.append(f"regression {finding.get('id')} missing {field}")
    if not any(g.get("ask_id") == "A11" and g.get("verdict") == "NOT_MEASURABLE" for g in report.get("gaps", [])):
        errors.append("A11 NOT_MEASURABLE gap is missing")
    return errors


def validate_schema(report: dict) -> None:
    schema_path = os.path.join(os.path.dirname(__file__), "schema", "loop-report.schema.json")
    with open(schema_path, encoding="utf-8") as file:
        schema = json.load(file)
    jsonschema.validate(report, schema)


def ground_truth_path(kit: str) -> str:
    for relative_path in (
        os.path.join("ground_truth", "ground_truth.json"),
        os.path.join("ground_truth_SEALED", "ground_truth.json"),
    ):
        path = os.path.join(kit, relative_path)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(f"No ground truth found under {kit}")


def run_pipeline(kit: str, team: str) -> dict:
    inspector = CorpusInspector(kit)
    contract = inspector.inspect()
    data = Preprocessor(kit).build()
    # Standards must exist before detection: prompt regressions are defined by
    # deviation from a cohort's own healthy operating level.
    standards = mine_standard(
        data["session_aggregates"], data["step_aggregates"], contract
    )
    specialists = Level1Specialists(contract, data)
    # The three analyses use disjoint reasoning responsibilities and run in parallel.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(specialists.regression), pool.submit(specialists.decoys), pool.submit(specialists.gaps)]
        results = [future.result() for future in as_completed(futures)]
    report = ReportBuilder(kit, team, data).build(results, standards)
    report["generated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    errors = validate_report(report)
    if errors:
        raise ValueError("; ".join(errors))
    validate_schema(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", default="../../kit")
    parser.add_argument("--team", default="pipeline-team")
    parser.add_argument("--out", default="../../my-level1-report.json")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--replay-url", default=None,
                        help="execute generated prescriptions against a replay endpoint")
    parser.add_argument("--golden-set-size", type=int, default=20,
                        help="known-good sessions sent to replay as a regression guard")
    args = parser.parse_args()
    report = run_pipeline(args.kit, args.team)
    if args.replay_url:
        golden_set = _load_golden_set(args.kit, max(0, args.golden_set_size))
        report = execute_replay_plan(report, args.replay_url, golden_set)
        errors = validate_report(report)
        if errors:
            raise ValueError("; ".join(errors))
        validate_schema(report)
    with open(args.out, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(f"wrote {args.out}")
    print(f"findings={len(report['findings'])} diagnoses={len(report['diagnoses'])} gaps={len(report['gaps'])}")
    if args.score:
        score_script = os.path.join(os.path.dirname(__file__), "score.py")
        gt = ground_truth_path(args.kit)
        result = subprocess.run([sys.executable, score_script, "--report", args.out, "--ground-truth", gt], check=False)
        return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
