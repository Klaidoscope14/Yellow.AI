"""Generic cohort-standard miner.

Replaces the hard-coded standards in build_report.build_standard(), which
named specific tenants, intents, agents and day cut-offs (day<34, day<40,
day<46). Those literals are correct only for the practice corpus; on the
sealed corpus every fault moves and the cut-offs are wrong.

This miner discovers standards from the data itself, with NO tenant/intent/
agent/day literals:

  * one standard per cohort that has enough resolved sessions,
  * "good" = the top decile of the cohort's own weekly performance
    (p90 of weekly resolution_rate; p10 of per-session turns / cost),
    which naturally selects the cohort's healthy weeks even when some
    weeks are degraded by a fault,
  * a deterministic golden_set_version hashed from the exemplar session
    ids, so a rerun on identical input yields an identical yardstick.

The output matches the loop-report `standard[]` schema exactly.
"""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Dict, List

# A cohort needs at least this many resolved sessions before it is worth
# publishing a standard for. Kept modest so small-but-real cohorts still
# get a yardstick; large enough that a handful of sessions cannot define one.
MIN_RESOLVED_SESSIONS = 30


def _golden_version(metric: str, exemplar_ids: List[str]) -> str:
    payload = json.dumps(["standard-v1", metric, sorted(exemplar_ids)],
                         separators=(",", ":"))
    return "gs_" + sha256(payload.encode("utf-8")).hexdigest()[:16]


def _rows(con, sql: str) -> List[tuple]:
    return con.execute(sql).fetchall()


def mine_standards(con) -> List[Dict[str, Any]]:
    """Mine top-decile standards for every qualifying cohort.

    Two cohort grains are mined, matching how findings are cohorted:
      - (tenant, intent)      -> resolution_rate, turns_to_resolve
      - (tenant, agent_id)    -> turns_to_resolve  (prompt-regression grain)
    """
    standards: List[Dict[str, Any]] = []
    standards.extend(_mine_intent_standards(con))
    standards.extend(_mine_agent_turns_standards(con))
    return standards


def _mine_intent_standards(con) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # Cohorts with enough resolved sessions to define a standard.
    cohorts = _rows(con, f"""
        SELECT tenant, intent, COUNT(*) AS resolved_n
        FROM sessions
        WHERE session_end = 'resolved'
        GROUP BY tenant, intent
        HAVING COUNT(*) >= {MIN_RESOLVED_SESSIONS}
        ORDER BY tenant, intent
    """)

    for tenant, intent, resolved_n in cohorts:
        # resolution_rate standard: top-decile weekly rate vs median weekly rate.
        res = con.execute("""
            WITH weekly AS (
                SELECT day / 7 AS week,
                       CAST(SUM(CASE WHEN session_end='resolved' THEN 1 ELSE 0 END) AS DOUBLE)
                           / COUNT(*) AS res
                FROM sessions
                WHERE tenant = ? AND intent = ?
                GROUP BY week
                HAVING COUNT(*) >= 20
            )
            SELECT COUNT(*),
                   PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY res),
                   MEDIAN(res)
            FROM weekly
        """, [tenant, intent]).fetchone()
        weeks_n, best_res, med_res = res
        if weeks_n and best_res is not None and med_res is not None:
            exemplar_ids = [r[0] for r in con.execute("""
                SELECT session_id FROM sessions
                WHERE tenant = ? AND intent = ? AND session_end = 'resolved'
                ORDER BY session_id
            """, [tenant, intent]).fetchall()]
            out.append({
                "tenant": tenant,
                "cohort": {"intent": intent},
                "metric": "resolution_rate",
                "exemplar_n": int(resolved_n),
                "golden_set_version": _golden_version("resolution_rate", exemplar_ids),
                "best": round(float(best_res), 4),
                "median": round(float(med_res), 4),
                "deficit": round(float(best_res) - float(med_res), 4),
                "derivation": ("top-decile weekly resolution_rate for this cohort vs its own "
                               "median week; mined from the cohort's own history, no fault "
                               "window assumed"),
            })

        # turns_to_resolve standard: p10 (fewest turns) vs median, resolved only.
        turns = con.execute("""
            SELECT COUNT(*),
                   PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY turns),
                   MEDIAN(turns)
            FROM sessions
            WHERE tenant = ? AND intent = ? AND session_end = 'resolved'
        """, [tenant, intent]).fetchone()
        turns_n, best_turns, med_turns = turns
        if turns_n and best_turns is not None and med_turns is not None:
            exemplar_ids = [r[0] for r in con.execute("""
                SELECT session_id FROM sessions
                WHERE tenant = ? AND intent = ? AND session_end = 'resolved'
                ORDER BY session_id
            """, [tenant, intent]).fetchall()]
            out.append({
                "tenant": tenant,
                "cohort": {"intent": intent},
                "metric": "turns_to_resolve",
                "exemplar_n": int(turns_n),
                "golden_set_version": _golden_version("turns_to_resolve", exemplar_ids),
                "best": round(float(best_turns), 3),
                "median": round(float(med_turns), 3),
                "deficit": round(float(med_turns) - float(best_turns), 3),
                "derivation": ("top-decile (fewest-turn) resolved sessions for this cohort vs its "
                               "own median; lower is better"),
            })

    return out


def _mine_agent_turns_standards(con) -> List[Dict[str, Any]]:
    """turns_to_resolve standard per v3 agent — the prompt-regression grain."""
    out: List[Dict[str, Any]] = []
    cohorts = _rows(con, f"""
        SELECT tenant, agent_id, COUNT(*) AS resolved_n
        FROM sessions
        WHERE session_end = 'resolved' AND agent_kind = 'v3_agent'
        GROUP BY tenant, agent_id
        HAVING COUNT(*) >= {MIN_RESOLVED_SESSIONS}
        ORDER BY tenant, agent_id
    """)
    for tenant, agent_id, resolved_n in cohorts:
        row = con.execute("""
            SELECT PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY turns),
                   MEDIAN(turns)
            FROM sessions
            WHERE tenant = ? AND agent_id = ? AND session_end = 'resolved'
        """, [tenant, agent_id]).fetchone()
        best_turns, med_turns = row
        if best_turns is None or med_turns is None:
            continue
        exemplar_ids = [r[0] for r in con.execute("""
            SELECT session_id FROM sessions
            WHERE tenant = ? AND agent_id = ? AND session_end = 'resolved'
            ORDER BY session_id
        """, [tenant, agent_id]).fetchall()]
        out.append({
            "tenant": tenant,
            "cohort": {"agent_id": agent_id},
            "metric": "turns_to_resolve",
            "exemplar_n": int(resolved_n),
            "golden_set_version": _golden_version("turns_to_resolve", exemplar_ids),
            "best": round(float(best_turns), 3),
            "median": round(float(med_turns), 3),
            "deficit": round(float(med_turns) - float(best_turns), 3),
            "derivation": ("top-decile (fewest-turn) resolved sessions for this agent vs its own "
                           "median; the yardstick for prompt-regression turn inflation"),
        })
    return out
