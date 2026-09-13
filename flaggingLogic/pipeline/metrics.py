"""Compute daily metrics by cohort using DuckDB SQL.

Golden Rule 1: All metric computation is deterministic SQL. No LLMs.
Golden Rule 3: Quality metrics partitioned by judge_version to avoid yardstick trap.
"""
from typing import Any, Dict, List


def _to_python(val):
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    try:
        if hasattr(val, 'item'):
            return val.item()
        f = float(val)
        return int(f) if f == int(f) and not isinstance(val, float) else f
    except (TypeError, ValueError):
        return str(val)


def _query(con, sql: str) -> List[Dict[str, Any]]:
    result = con.execute(sql)
    columns = [desc[0] for desc in result.description]
    return [
        {col: _to_python(val) for col, val in zip(columns, row)}
        for row in result.fetchall()
    ]


def session_metrics_by_intent(con) -> List[Dict]:
    """Daily session metrics by [tenant, intent, day].

    Metrics: resolution_rate, containment_rate, median_turns, mean_cost (v3 only).
    Rolling 14-day baselines computed via window functions.
    """
    return _query(con, """
    WITH daily AS (
        SELECT
            tenant, intent, day,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN agent_kind = 'v3_agent' THEN 1 ELSE 0 END) as v3_count,
            SUM(CASE WHEN agent_kind = 'v2_flow' THEN 1 ELSE 0 END) as v2_count,
            SUM(CASE WHEN session_end = 'resolved' THEN 1 ELSE 0 END) as resolved_count,
            SUM(CASE WHEN session_end = 'resolved'
                OR (session_end = 'handoff' AND handoff_by_design = true)
                THEN 1 ELSE 0 END) as contained_count,
            SUM(CASE WHEN session_end = 'handoff' THEN 1 ELSE 0 END) as handoff_count,
            SUM(CASE WHEN session_end = 'abandoned' THEN 1 ELSE 0 END) as abandon_count,
            CAST(SUM(CASE WHEN session_end = 'resolved' THEN 1 ELSE 0 END) AS DOUBLE)
                / COUNT(*) as resolution_rate,
            CAST(SUM(CASE WHEN session_end = 'resolved'
                OR (session_end = 'handoff' AND handoff_by_design = true)
                THEN 1 ELSE 0 END) AS DOUBLE) / COUNT(*) as containment_rate,
            MEDIAN(turns) as median_turns,
            AVG(turns) as mean_turns,
            AVG(CASE WHEN agent_kind = 'v3_agent' THEN cost_usd ELSE NULL END) as mean_cost_v3,
            AVG(duration_s) as mean_duration_s
        FROM sessions
        GROUP BY tenant, intent, day
    )
    SELECT *,
        AVG(resolution_rate) OVER w as baseline_resolution,
        AVG(containment_rate) OVER w as baseline_containment,
        AVG(median_turns) OVER w as baseline_median_turns,
        AVG(mean_cost_v3) OVER w as baseline_cost
    FROM daily
    WINDOW w AS (PARTITION BY tenant, intent ORDER BY day
                 ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
    ORDER BY tenant, intent, day
    """)


def session_metrics_by_agent(con) -> List[Dict]:
    """Daily session metrics by [tenant, agent_id, day].

    Primary use: F3 prompt regression detection on median_turns per agent.
    """
    return _query(con, """
    WITH daily AS (
        SELECT
            tenant, agent_id, agent_kind, day,
            COUNT(*) as total_sessions,
            SUM(CASE WHEN session_end = 'resolved' THEN 1 ELSE 0 END) as resolved_count,
            CAST(SUM(CASE WHEN session_end = 'resolved' THEN 1 ELSE 0 END) AS DOUBLE)
                / COUNT(*) as resolution_rate,
            MEDIAN(turns) as median_turns,
            AVG(turns) as mean_turns,
            AVG(cost_usd) as mean_cost,
            AVG(duration_s) as mean_duration_s
        FROM sessions
        GROUP BY tenant, agent_id, agent_kind, day
    )
    SELECT *,
        AVG(resolution_rate) OVER w as baseline_resolution,
        AVG(median_turns) OVER w as baseline_median_turns,
        AVG(mean_cost) OVER w as baseline_cost
    FROM daily
    WINDOW w AS (PARTITION BY tenant, agent_id ORDER BY day
                 ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
    ORDER BY tenant, agent_id, day
    """)


def tool_metrics(con) -> List[Dict]:
    """Daily tool call metrics by [tenant, intent, tool_name, day].

    Key fields:
      error_rate = outcome != 'ok' / total_calls
      silent_fail_rate = (outcome='ok' AND result_field_count=0) / ok_calls
    The silent_fail_rate is INVISIBLE to standard error monitoring.
    """
    return _query(con, """
    WITH daily AS (
        SELECT
            tenant, intent, tool_name, day,
            COUNT(*) as total_calls,
            SUM(CASE WHEN outcome != 'ok' THEN 1 ELSE 0 END) as error_count,
            SUM(CASE WHEN outcome = 'ok' THEN 1 ELSE 0 END) as ok_count,
            SUM(CASE WHEN outcome = 'ok' AND result_field_count = 0
                THEN 1 ELSE 0 END) as silent_fail_count,
            CAST(SUM(CASE WHEN outcome != 'ok' THEN 1 ELSE 0 END) AS DOUBLE)
                / COUNT(*) as error_rate,
            CASE WHEN SUM(CASE WHEN outcome = 'ok' THEN 1 ELSE 0 END) > 0
                THEN CAST(SUM(CASE WHEN outcome = 'ok' AND result_field_count = 0
                    THEN 1 ELSE 0 END) AS DOUBLE)
                    / SUM(CASE WHEN outcome = 'ok' THEN 1 ELSE 0 END)
                ELSE 0 END as silent_fail_rate,
            MEDIAN(duration_ms) as p50_latency,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_latency,
            AVG(duration_ms) as mean_latency
        FROM steps
        WHERE step_type = 'tool_call'
        GROUP BY tenant, intent, tool_name, day
    )
    SELECT *,
        AVG(error_rate) OVER w as baseline_error_rate,
        AVG(silent_fail_rate) OVER w as baseline_silent_fail,
        AVG(p50_latency) OVER w as baseline_p50_latency
    FROM daily
    WINDOW w AS (PARTITION BY tenant, intent, tool_name ORDER BY day
                 ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
    ORDER BY tenant, intent, tool_name, day
    """)


def kb_metrics(con) -> List[Dict]:
    """Daily KB lookup metrics by [tenant, intent, day].

    Key fields:
      kb_miss_rate = kb_hit=false / total_lookups
      mean_kb_top_score = average retrieval confidence
    F1 signature: kb_miss_rate spikes, kb_top_score drops to 0.11-0.38 band.
    """
    return _query(con, """
    WITH daily AS (
        SELECT
            tenant, intent, day,
            COUNT(*) as total_lookups,
            SUM(CASE WHEN kb_hit = false THEN 1 ELSE 0 END) as miss_count,
            CAST(SUM(CASE WHEN kb_hit = false THEN 1 ELSE 0 END) AS DOUBLE)
                / COUNT(*) as kb_miss_rate,
            AVG(kb_top_score) as mean_kb_top_score,
            AVG(CASE WHEN kb_hit = true THEN kb_top_score ELSE NULL END) as mean_score_hit,
            AVG(CASE WHEN kb_hit = false THEN kb_top_score ELSE NULL END) as mean_score_miss
        FROM steps
        WHERE step_type = 'kb_lookup'
        GROUP BY tenant, intent, day
    )
    SELECT *,
        AVG(kb_miss_rate) OVER w as baseline_kb_miss_rate,
        AVG(mean_kb_top_score) OVER w as baseline_kb_score
    FROM daily
    WINDOW w AS (PARTITION BY tenant, intent ORDER BY day
                 ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
    ORDER BY tenant, intent, day
    """)


def volume_metrics(con) -> List[Dict]:
    """Daily volume and quality by tenant. Used for D2 load spike detection."""
    return _query(con, """
    WITH daily AS (
        SELECT
            tenant, day,
            COUNT(*) as total_sessions,
            AVG(quality_score) as mean_quality
        FROM sessions
        GROUP BY tenant, day
    )
    SELECT *,
        AVG(total_sessions) OVER w as baseline_volume,
        AVG(mean_quality) OVER w as baseline_quality
    FROM daily
    WINDOW w AS (PARTITION BY tenant ORDER BY day
                 ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
    ORDER BY tenant, day
    """)


def quality_by_judge(con) -> List[Dict]:
    """Daily quality by [tenant, day, judge_version].

    Rule 3: quality_score only comparable within one judge_version.
    A cross-version trend measures the rubric, not the agent.
    """
    return _query(con, """
    SELECT
        tenant, day, judge_version,
        COUNT(*) as n_sessions,
        AVG(quality_score) as mean_quality,
        MEDIAN(quality_score) as median_quality
    FROM sessions
    GROUP BY tenant, day, judge_version
    ORDER BY tenant, day, judge_version
    """)


def latency_by_tenant_day(con) -> List[Dict]:
    """Daily tool call latency by tenant. Used for D2 corroboration."""
    return _query(con, """
    WITH daily AS (
        SELECT
            tenant, day,
            COUNT(*) as total_calls,
            MEDIAN(duration_ms) as p50_latency,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_latency
        FROM steps
        WHERE step_type = 'tool_call'
        GROUP BY tenant, day
    )
    SELECT *,
        AVG(p50_latency) OVER w as baseline_p50,
        AVG(p95_latency) OVER w as baseline_p95
    FROM daily
    WINDOW w AS (PARTITION BY tenant ORDER BY day
                 ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING)
    ORDER BY tenant, day
    """)


def intent_share(con) -> List[Dict]:
    """Daily intent share by [tenant, intent, day]. Used for D1 mix shift detection."""
    return _query(con, """
    WITH totals AS (
        SELECT tenant, day, COUNT(*) as day_total
        FROM sessions GROUP BY tenant, day
    ),
    by_intent AS (
        SELECT tenant, intent, day, COUNT(*) as intent_count
        FROM sessions GROUP BY tenant, intent, day
    )
    SELECT
        b.tenant, b.intent, b.day,
        b.intent_count,
        t.day_total,
        CAST(b.intent_count AS DOUBLE) / t.day_total as intent_share,
        AVG(CAST(b.intent_count AS DOUBLE) / t.day_total) OVER (
            PARTITION BY b.tenant, b.intent ORDER BY b.day
            ROWS BETWEEN 14 PRECEDING AND 1 PRECEDING
        ) as baseline_share
    FROM by_intent b
    JOIN totals t ON b.tenant = t.tenant AND b.day = t.day
    ORDER BY b.tenant, b.intent, b.day
    """)


def coverage_by_tenant(con) -> List[Dict]:
    """V3 coverage per tenant (v3_sessions / total). v2_flow emits no tool/kb steps."""
    return _query(con, """
    SELECT
        tenant,
        COUNT(*) as total,
        SUM(CASE WHEN agent_kind = 'v3_agent' THEN 1 ELSE 0 END) as v3_count,
        CAST(SUM(CASE WHEN agent_kind = 'v3_agent' THEN 1 ELSE 0 END) AS DOUBLE)
            / COUNT(*) as v3_coverage
    FROM sessions
    GROUP BY tenant
    """)


def config_timeline(con) -> List[Dict]:
    return _query(con, "SELECT * FROM config_timeline ORDER BY day")


def compute_all(con) -> Dict[str, Any]:
    print("  session_by_intent...")
    sbi = session_metrics_by_intent(con)
    print(f"    {len(sbi)} rows")

    print("  session_by_agent...")
    sba = session_metrics_by_agent(con)
    print(f"    {len(sba)} rows")

    print("  tool_metrics...")
    tm = tool_metrics(con)
    print(f"    {len(tm)} rows")

    print("  kb_metrics...")
    kb = kb_metrics(con)
    print(f"    {len(kb)} rows")

    print("  volume_metrics...")
    vol = volume_metrics(con)
    print(f"    {len(vol)} rows")

    print("  quality_by_judge...")
    qj = quality_by_judge(con)
    print(f"    {len(qj)} rows")

    print("  latency_by_tenant_day...")
    lat = latency_by_tenant_day(con)
    print(f"    {len(lat)} rows")

    print("  intent_share...")
    ish = intent_share(con)
    print(f"    {len(ish)} rows")

    print("  coverage_by_tenant...")
    cov = coverage_by_tenant(con)
    print(f"    {len(cov)} rows")

    print("  config_timeline...")
    cfg = config_timeline(con)
    print(f"    {len(cfg)} rows")

    return {
        'session_by_intent': sbi,
        'session_by_agent': sba,
        'tool': tm,
        'kb': kb,
        'volume': vol,
        'quality': qj,
        'latency': lat,
        'intent_share': ish,
        'coverage': cov,
        'config': cfg,
    }
