"""Query-aware multi-agent orchestration for Nexus Loop analysis.

This module is deliberately separate from the corpus generator and scoring
harness. It is an orchestration reference: specialist agents return claims,
the orchestrator checks whether those claims are comparable, and only then
does trust influence the decision.

Run the built-in demonstration with:

    py orchestrator.py

Trust is learned from reviewer or validator feedback. It is not learned from
the hidden ground truth at runtime, and it never overrides incompatible scope
or missing evidence.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from math import log
from threading import Lock
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


AgentFn = Callable[["AnalysisQuery"], "EvidencePacket"]


@dataclass(frozen=True)
class AnalysisQuery:
    """The contract every specialist receives.

    Scope is explicit so two agents cannot disagree merely because one used
    v3 traffic and the other silently included v2 traffic.
    """

    query_id: str
    question: str
    metric: str
    grain: str
    scope: Dict[str, Any]

    @property
    def scope_key(self) -> str:
        encoded = json.dumps(self.scope, sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()[:12]


@dataclass
class EvidencePacket:
    """A specialist's claim plus enough provenance to audit it."""

    agent: str
    query_id: str
    metric: str
    grain: str
    scope: Dict[str, Any]
    value: Any
    claim: str
    evidence: List[str]
    confidence: float
    denominator: str
    source: List[str]
    limitations: List[str] = field(default_factory=list)

    @property
    def scope_key(self) -> str:
        encoded = json.dumps(self.scope, sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()[:12]

    def validate(self, query: AnalysisQuery) -> List[str]:
        errors = []
        if self.query_id != query.query_id:
            errors.append("query_id does not match the requested query")
        if self.metric != query.metric:
            errors.append("metric does not match the requested query")
        if self.grain != query.grain:
            errors.append("grain does not match the requested query")
        if self.scope_key != query.scope_key:
            errors.append("scope differs from the requested scope")
        if not self.denominator:
            errors.append("denominator is missing")
        if not self.source:
            errors.append("source provenance is missing")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be between 0 and 1")
        if not self.evidence:
            errors.append("at least one evidence item is required")
        return errors


@dataclass
class TrustState:
    """Beta-style posterior for one agent and one query family.

    The prior is seeded from the agent's known specialization. Feedback from a
    reviewer updates successes or failures. The posterior mean is deliberately
    conservative: early feedback cannot instantly make an agent dominant.
    """

    prior_success: float
    prior_failure: float
    successes: int = 0
    failures: int = 0

    @property
    def score(self) -> float:
        return (self.prior_success + self.successes) / (
            self.prior_success
            + self.prior_failure
            + self.successes
            + self.failures
        )

    @property
    def observations(self) -> int:
        return self.successes + self.failures

    def update(self, accepted: bool) -> None:
        if accepted:
            self.successes += 1
        else:
            self.failures += 1


class TrustRegistry:
    """Thread-safe query-conditioned trust registry.

    Trust keys use ``(agent, query_id)`` rather than one global score. An agent
    can be excellent at tool analysis and weak at judge-version analysis.
    """

    def __init__(self) -> None:
        self._states: Dict[Tuple[str, str], TrustState] = {}
        self._lock = Lock()

    def register(self, agent: str, query_id: str, prior: float = 0.70) -> None:
        if not 0.0 < prior < 1.0:
            raise ValueError("prior must be between 0 and 1")
        with self._lock:
            self._states.setdefault(
                (agent, query_id),
                TrustState(prior_success=prior * 10, prior_failure=(1 - prior) * 10),
            )

    def score(self, agent: str, query_id: str) -> float:
        with self._lock:
            state = self._states.get((agent, query_id))
            return state.score if state else 0.5

    def update(self, agent: str, query_id: str, accepted: bool) -> None:
        with self._lock:
            state = self._states.setdefault(
                (agent, query_id), TrustState(prior_success=5.0, prior_failure=5.0)
            )
            state.update(accepted)

    def snapshot(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        with self._lock:
            return {
                agent: {
                    query: {
                        "score": round(state.score, 4),
                        "observations": state.observations,
                    }
                    for (known_agent, query), state in self._states.items()
                    if known_agent == agent
                }
                for agent, _ in self._states
            }


@dataclass
class RankedClaim:
    packet: EvidencePacket
    trust: float
    evidence_quality: float
    decision_score: float


@dataclass
class Resolution:
    status: str
    decision: Optional[EvidencePacket]
    ranked_claims: List[RankedClaim]
    conflicts: List[str]
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        def ranked(item: RankedClaim) -> Dict[str, Any]:
            return {
                "agent": item.packet.agent,
                "value": item.packet.value,
                "claim": item.packet.claim,
                "trust": round(item.trust, 4),
                "evidence_quality": round(item.evidence_quality, 4),
                "decision_score": round(item.decision_score, 4),
            }

        return {
            "status": self.status,
            "decision": asdict(self.decision) if self.decision else None,
            "ranked_claims": [ranked(item) for item in self.ranked_claims],
            "conflicts": self.conflicts,
            "reason": self.reason,
        }


class ConflictResolver:
    """Resolves comparable claims and escalates incomparable ones.

    Trust is only a ranking signal after hard compatibility checks. This is
    the guard against a high-trust agent winning with the wrong denominator or
    time window.
    """

    def __init__(self, registry: TrustRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _evidence_quality(packet: EvidencePacket) -> float:
        quality = 0.0
        quality += min(len(packet.evidence), 4) / 4 * 0.40
        quality += min(len(packet.source), 3) / 3 * 0.25
        quality += 0.20 if packet.denominator else 0.0
        quality += 0.15 if packet.limitations else 0.05
        return min(1.0, quality)

    def resolve(self, query: AnalysisQuery,
                packets: Sequence[EvidencePacket]) -> Resolution:
        valid: List[EvidencePacket] = []
        conflicts: List[str] = []
        hard_conflict = False
        for packet in packets:
            errors = packet.validate(query)
            if errors:
                conflicts.append(f"{packet.agent}: rejected packet ({'; '.join(errors)})")
                # A competing claim with a different scope, metric, grain, or
                # query contract is not merely lower quality evidence. Ranking
                # the remaining packets would hide an unresolved disagreement.
                if any(error in {
                    "query_id does not match the requested query",
                    "metric does not match the requested query",
                    "grain does not match the requested query",
                    "scope differs from the requested scope",
                } for error in errors):
                    hard_conflict = True
            else:
                valid.append(packet)

        if hard_conflict:
            return Resolution("escalate", None, [], conflicts,
                              "A competing claim violates the query contract; reconcile scope "
                              "and denominator before ranking trust.")

        if not valid:
            return Resolution("escalate", None, [], conflicts,
                              "No claim satisfied the query contract.")

        scope_keys = {packet.scope_key for packet in valid}
        if len(scope_keys) > 1:
            conflicts.append("valid claims use incompatible scopes")
            return Resolution("escalate", None, [], conflicts,
                              "Do not rank claims until scope and denominator are reconciled.")

        ranked = []
        for packet in valid:
            trust = self.registry.score(packet.agent, query.query_id)
            evidence_quality = self._evidence_quality(packet)
            # Confidence is supplied by the specialist; trust is learned from
            # feedback; evidence quality rewards auditable claims. None alone
            # can override a hard scope mismatch.
            score = trust * packet.confidence * evidence_quality
            ranked.append(RankedClaim(packet, trust, evidence_quality, score))
        ranked.sort(key=lambda item: item.decision_score, reverse=True)

        if len(ranked) > 1:
            gap = ranked[0].decision_score - ranked[1].decision_score
            if gap < 0.05:
                return Resolution("escalate", None, ranked,
                                  ["top claims are too close to resolve automatically"],
                                  "Human or deterministic adjudication is required.")

        return Resolution("resolved", ranked[0].packet, ranked, conflicts,
                          "Claims share scope; trust ranked otherwise comparable evidence.")


@dataclass
class AgentSpec:
    name: str
    query_ids: List[str]
    handler: AgentFn
    prior_trust: float = 0.70


class Orchestrator:
    """Runs specialists in parallel and centralizes reconciliation."""

    def __init__(self, agents: Iterable[AgentSpec], max_workers: int = 4) -> None:
        self.agents = list(agents)
        self.max_workers = max_workers
        self.trust = TrustRegistry()
        for agent in self.agents:
            for query_id in agent.query_ids:
                self.trust.register(agent.name, query_id, agent.prior_trust)
        self.resolver = ConflictResolver(self.trust)

    def run(self, query: AnalysisQuery) -> Resolution:
        eligible = [agent for agent in self.agents if query.query_id in agent.query_ids]
        packets: List[EvidencePacket] = []
        # Agents only return evidence packets. They never edit the shared report,
        # which makes this fan-out safe and keeps the merge deterministic.
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(eligible)))) as pool:
            futures = {pool.submit(agent.handler, query): agent for agent in eligible}
            for future in as_completed(futures):
                agent = futures[future]
                try:
                    packets.append(future.result())
                except Exception as error:  # one specialist must not kill the run
                    packets.append(EvidencePacket(
                        agent=agent.name, query_id=query.query_id, metric=query.metric,
                        grain=query.grain, scope=query.scope, value=None,
                        claim="agent failed", evidence=[], confidence=0.0,
                        denominator="", source=[], limitations=[str(error)],
                    ))
        return self.resolver.resolve(query, packets)

    def learn(self, query_id: str, agent: str, accepted: bool) -> None:
        """Update trust from review, replay, or a validated report outcome."""
        self.trust.update(agent, query_id, accepted)


def demo() -> Dict[str, Any]:
    """Show the intended behavior without reading the hidden ground truth."""
    query = AnalysisQuery(
        query_id="premium_kb_regression",
        question="Is premium_card_info underperforming because of retrieval?",
        metric="resolution_rate",
        grain="session",
        scope={"tenant": "acme-bank", "agent_kind": "v3_agent", "from_day": 35,
               "to_day": 45, "intent": "premium_card_info"},
    )

    def kb_agent(request: AnalysisQuery) -> EvidencePacket:
        return EvidencePacket(
            agent="kb-specialist", query_id=request.query_id, metric=request.metric,
            grain=request.grain, scope=request.scope, value=0.31,
            claim="resolution is low and KB retrieval is failing",
            evidence=["kb_hit=false for the affected cohort", "kb_top_score is low"],
            confidence=0.92, denominator="all v3 sessions in the window",
            source=["sessions.jsonl.gz", "agent_steps.jsonl.gz"],
            limitations=["cohort has no before-period"],
        )

    def generic_agent(request: AnalysisQuery) -> EvidencePacket:
        return EvidencePacket(
            agent="generic-metrics-agent", query_id=request.query_id, metric=request.metric,
            grain=request.grain, scope=request.scope, value=0.31,
            claim="resolution is low",
            evidence=["resolution rate is below peer baseline"], confidence=0.70,
            denominator="all v3 sessions in the window",
            source=["sessions.jsonl.gz"], limitations=["cause not identified"],
        )

    orchestrator = Orchestrator([
        AgentSpec("kb-specialist", [query.query_id], kb_agent, prior_trust=0.75),
        AgentSpec("generic-metrics-agent", [query.query_id], generic_agent, prior_trust=0.65),
    ])
    resolved = orchestrator.run(query)
    orchestrator.learn(query.query_id, "kb-specialist", accepted=True)

    incompatible = EvidencePacket(
        agent="legacy-metrics-agent", query_id=query.query_id, metric=query.metric,
        grain=query.grain,
        scope={"tenant": "acme-bank", "agent_kind": "v2_flow", "from_day": 35,
               "to_day": 45, "intent": "premium_card_info"},
        value=0.58, claim="resolution is moderate", evidence=["legacy sessions"],
        confidence=0.99, denominator="all sessions including v2_flow",
        source=["sessions.jsonl.gz"], limitations=[],
    )
    rejected = orchestrator.resolver.resolve(query, [resolved.decision, incompatible]
                                              if resolved.decision else [incompatible])
    return {
        "resolved_same_scope": resolved.as_dict(),
        "escalated_scope_conflict": rejected.as_dict(),
        "trust_after_feedback": orchestrator.trust.snapshot(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="run the orchestration demo")
    args = parser.parse_args()
    # The module has no production service entrypoint yet; running it without
    # flags remains a useful local smoke test, while --demo documents intent.
    print(json.dumps(demo(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())