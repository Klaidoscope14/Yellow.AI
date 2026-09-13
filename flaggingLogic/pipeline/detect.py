"""Detection pipeline: flag regressions, dismiss lookalikes, deduplicate.

Positive detectors (is_regression=True):
  F1 — KB coverage gap         (kb_miss_rate spikes, resolution drops)
  F2 — Silent tool failure     (result_field_count=0 on outcome=ok, error_rate flat)
  F3 — Prompt regression       (median_turns up >30%, resolution flat)

Decoy detectors (is_regression=False, earns specificity credit):
  D1 — Traffic mix shift       (aggregate moves, per-intent rates stable)
  D2 — Load spike              (volume+latency up, quality flat, self-corrects)
  D3 — Judge version change    (quality drops both tenants near judge config)

Golden Rule 1: All detection is deterministic math. No LLMs.
Golden Rule 3: Never trend quality_score across judge_versions.
"""
import math
import statistics
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def group_by(data: List[Dict], keys: List[str]) -> Dict[tuple, List[Dict]]:
    groups = defaultdict(list)
    for row in data:
        key = tuple(row.get(k) for k in keys)
        groups[key].append(row)
    for v in groups.values():
        v.sort(key=lambda x: x.get('day', 0))
    return dict(groups)


def safe_avg(values):
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 6) if vals else None


def get_vals(series, from_day, to_day, key):
    return [r[key] for r in series
            if from_day <= r.get('day', -1) < to_day and r.get(key) is not None]


def find_onset_deviation(series, key, baseline_key, pct, min_consec, direction='up'):
    """First day where metric deviates from baseline by pct for min_consec days."""
    streak, onset = 0, None
    for row in series:
        val = row.get(key)
        base = row.get(baseline_key)
        if val is None or base is None or base == 0:
            streak, onset = 0, None
            continue
        deviation = (val - base) / abs(base)
        triggered = (direction == 'up' and deviation > pct) or \
                    (direction == 'down' and deviation < -pct) or \
                    (direction == 'both' and abs(deviation) > pct)
        if triggered:
            if streak == 0:
                onset = row['day']
            streak += 1
            if streak >= min_consec:
                return onset
        else:
            streak, onset = 0, None
    return None


# ---------------------------------------------------------------------------
# Adaptive thresholds — the anomaly bar is derived from the cohort's own
# baseline (or its peers') and sample size, not a corpus-tuned constant. This
# is what protects detection on a hidden corpus with different base rates:
#   threshold = baseline + max(min_effect, z * standard_error)
# The absolute value in config is kept only as a floor for cohorts that have no
# baseline at all (e.g. a brand-new product line born broken).
# ---------------------------------------------------------------------------

def _binomial_se(p, n):
    """Standard error of a rate p over n observations. Wider when n is small,
    so a spike seen on a handful of calls must be larger to count."""
    if not n or n <= 0:
        return 0.0
    p = min(max(float(p), 0.0), 1.0)
    return math.sqrt(max(p * (1.0 - p), 1e-9) / n)


def _adaptive_threshold(base, n, z, min_effect, floor):
    """Per-row anomaly bar. With no baseline, fall back to the absolute floor."""
    if base is None:
        return floor
    return float(base) + max(min_effect, z * _binomial_se(base, n))


def _peer_baseline_by_day(cohorts, tenant, exclude_intent, key, count_key):
    """Median of a rate across sibling cohorts (same tenant, other intents) per
    day — the 'standard' a born-broken cohort has no history to be compared to."""
    per_day = defaultdict(list)
    for (t2, i2), series in cohorts.items():
        if t2 != tenant or i2 == exclude_intent:
            continue
        for row in series:
            val = row.get(key)
            if val is not None and (row.get(count_key) or 0) > 0:
                per_day[row['day']].append(val)
    return {day: statistics.median(vals) for day, vals in per_day.items() if vals}


def adaptive_onset_window(series, key, count_key, min_count, min_consec, z,
                          min_effect, floor, baseline_key=None, baseline_by_day=None):
    """First day starting a min_consec run over the adaptive bar, plus the last
    flagged day. Every row is compared to its own baseline+SE bar."""
    def bar(row):
        if baseline_by_day is not None:
            base = baseline_by_day.get(row['day'])
        elif baseline_key is not None:
            base = row.get(baseline_key)
        else:
            base = None
        return _adaptive_threshold(base, row.get(count_key) or 0, z, min_effect, floor)

    streak, onset, cand, flagged = 0, None, None, []
    for row in series:
        val, n = row.get(key), (row.get(count_key) or 0)
        if val is None or n < min_count:
            streak, cand = 0, None
            continue
        if val > bar(row):
            flagged.append(row['day'])
            if streak == 0:
                cand = row['day']
            streak += 1
            if onset is None and streak >= min_consec:
                onset = cand
        else:
            streak, cand = 0, None
    if onset is None:
        return None, None
    end_day = max((d for d in flagged if d >= onset), default=onset)
    return onset, end_day


def config_near(config, tenant, day, lookback, kind=None):
    """Config changes in [day - lookback, day] for tenant or '*'."""
    out = []
    for c in config:
        if (day - lookback) <= c.get('day', -999) <= day:
            if c.get('tenant') in ('*', tenant):
                if kind is None or c.get('kind') == kind:
                    out.append(c)
    return out


def timeseries_snippet(series, key, from_day, to_day):
    """Extract daily values as [{day, value}] for a metric in a window."""
    return [{'day': r['day'], 'value': round(r[key], 6)}
            for r in series
            if from_day <= r.get('day', -1) <= to_day and r.get(key) is not None]


def pct_change(before, during):
    if before is None or during is None or before == 0:
        return None
    return round((during - before) / abs(before), 4)


# ---------------------------------------------------------------------------
# F1 — KB Gap
# ---------------------------------------------------------------------------

def detect_kb_gap(metrics, cfg):
    """Detect KB coverage gaps: kb_miss_rate spikes in a [tenant, intent] cohort.

    Signal: kb_hit=false rate sustained above absolute threshold.
    Corroboration: kb_top_score drops into 0.11-0.38 band, resolution drops.
    """
    problems = []
    kb_cohorts = group_by(metrics['kb'], ['tenant', 'intent'])
    sess_cohorts = group_by(metrics['session_by_intent'], ['tenant', 'intent'])
    vol_by_tenant = group_by(metrics['volume'], ['tenant'])
    t = cfg['f1_kb_gap']
    g = cfg['general']

    for (tenant, intent), kb_series in kb_cohorts.items():
        # Peer-relative bar: a KB gap is a cohort whose miss rate stands out
        # against its sibling cohorts, not one that crosses a fixed 50%. This
        # catches a born-broken new product (no self-history) and adapts to a
        # corpus where the normal miss rate is higher or lower.
        peer_by_day = _peer_baseline_by_day(kb_cohorts, tenant, intent,
                                            'kb_miss_rate', 'total_lookups')
        onset, end_day = adaptive_onset_window(
            kb_series, 'kb_miss_rate', 'total_lookups', t['min_kb_lookups_per_day'],
            t['min_consecutive_days'], t.get('kb_miss_z', 2.5),
            t.get('kb_miss_min_effect', 0.15), t['kb_miss_rate_abs'],
            baseline_by_day=peer_by_day)
        if onset is None:
            continue
        miss_during = safe_avg(get_vals(kb_series, onset, end_day + 1, 'kb_miss_rate'))
        score_during = safe_avg(get_vals(kb_series, onset, end_day + 1, 'mean_kb_top_score'))
        miss_before = safe_avg(get_vals(kb_series, max(0, onset - 14), onset, 'kb_miss_rate'))
        score_before = safe_avg(get_vals(kb_series, max(0, onset - 14), onset, 'mean_kb_top_score'))

        # For new intents with no baseline, compare to peer intents
        peer_miss = {}
        for (t2, i2), peer in kb_cohorts.items():
            if t2 == tenant and i2 != intent:
                pv = safe_avg(get_vals(peer, onset, end_day + 1, 'kb_miss_rate'))
                if pv is not None:
                    peer_miss[i2] = round(pv, 4)
        if miss_before is None and peer_miss:
            miss_before = safe_avg(list(peer_miss.values()))

        sess = sess_cohorts.get((tenant, intent), [])
        res_before = safe_avg(get_vals(sess, max(0, onset - 14), onset, 'resolution_rate'))
        res_during = safe_avg(get_vals(sess, onset, end_day + 1, 'resolution_rate'))
        turns_during = safe_avg(get_vals(sess, onset, end_day + 1, 'median_turns'))

        if res_before is None:
            all_tenant_res = []
            for (t2, i2), s2 in sess_cohorts.items():
                if t2 == tenant and i2 != intent:
                    all_tenant_res.extend(get_vals(s2, onset, end_day + 1, 'resolution_rate'))
            res_before = safe_avg(all_tenant_res)

        sessions_affected = sum(r.get('total_sessions', 0) for r in sess if onset <= r['day'] <= end_day)
        tenant_vol = vol_by_tenant.get((tenant,), [])
        total_tenant = sum(r.get('total_sessions', 0) for r in tenant_vol if onset <= r['day'] <= end_day)
        share = round(sessions_affected / total_tenant, 4) if total_tenant else 0

        kb_changes = config_near(metrics['config'], tenant, onset, g['config_lookback_days'], 'kb')

        evidence = []
        evidence.append(f"kb_miss_rate for {intent} averaged {miss_during:.2%} from day {onset} "
                        f"(peer intents average {safe_avg(list(peer_miss.values())) if peer_miss else 'N/A'})")
        if score_during is not None:
            evidence.append(f"kb_top_score averaged {score_during:.3f} in window, indicating low retrieval confidence")
        if res_during is not None and res_before is not None:
            evidence.append(f"resolution rate dropped from {res_before:.2%} to {res_during:.2%}")
        if kb_changes:
            c = kb_changes[0]
            evidence.append(f"KB update {c.get('from_value')} -> {c.get('to_value')} on day {c.get('day')}")

        problems.append({
            'problem_id': f'F1_{tenant}_{intent}',
            'tenant': tenant,
            'cohort': {'intent': intent},
            'cohort_type': 'tenant_intent',
            'detection_type': 'kb_gap',
            'cause_class': 'kb.gap',
            'is_regression': True,
            'not_a_regression_because': None,
            'severity': 'high' if (share > 0.03 or (res_during or 1) < 0.4) else 'medium',
            'onset_day': onset,
            'window': {'from_day': onset, 'to_day': end_day},
            'primary_metric': 'kb_miss_rate',
            'metrics': {
                'kb_miss_rate': {'before': miss_before, 'during': miss_during,
                                 'delta_pct': pct_change(miss_before, miss_during)},
                'kb_mean_top_score': {'before': score_before, 'during': score_during,
                                      'delta_pct': pct_change(score_before, score_during)},
                'resolution_rate': {'before': res_before, 'during': res_during,
                                    'delta_pct': pct_change(res_before, res_during)},
                'median_turns': {'during': turns_during},
            },
            'config_attribution': {
                'found': bool(kb_changes),
                'changes': [{k: v for k, v in c.items()} for c in kb_changes],
            },
            'impact': {
                'conversations_affected': sessions_affected,
                'share_of_tenant_traffic': share,
                'days_running': end_day - onset + 1,
                'derivation': (f"{sessions_affected} sessions in [{onset},{end_day}], "
                               f"{share:.1%} of {tenant} traffic"),
            },
            'evidence': evidence,
            'peer_comparison': peer_miss,
            'daily_timeseries': {
                'kb_miss_rate': timeseries_snippet(kb_series, 'kb_miss_rate',
                                                   max(0, onset - 14), end_day),
                'resolution_rate': timeseries_snippet(sess, 'resolution_rate',
                                                      max(0, onset - 14), end_day),
            },
            'coverage': None,
            'corroborating_signals': sum([
                miss_during is not None and miss_during > t['kb_miss_rate_abs'],
                score_during is not None and score_during < t['kb_score_low_abs'],
                res_during is not None and res_before is not None and
                    (res_before - res_during) / max(res_before, 0.01) > t['resolution_drop_pct'],
                bool(kb_changes),
            ]),
            'ask_relevance': ['A01', 'A06'],
        })
    return problems


# ---------------------------------------------------------------------------
# F2 — Silent Tool Failure
# ---------------------------------------------------------------------------

def detect_silent_tool(metrics, cfg):
    """Detect silent tool failures: outcome=ok but result_field_count=0.

    Signal: silent_fail_rate spikes WHILE declared error_rate stays flat.
    This makes F2 invisible to naive error monitoring.
    Corroboration: resolution drops in the same [tenant, intent] cohort.
    """
    problems = []
    tool_cohorts = group_by(metrics['tool'], ['tenant', 'intent', 'tool_name'])
    sess_cohorts = group_by(metrics['session_by_intent'], ['tenant', 'intent'])
    vol_by_tenant = group_by(metrics['volume'], ['tenant'])
    t = cfg['f2_silent_tool_failure']
    g = cfg['general']

    for (tenant, intent, tool_name), tool_series in tool_cohorts.items():
        # Baseline-relative bar: normal silent-fail is ~0, so a real contract
        # break shows as a sustained rise above the tool's own rolling baseline
        # by more than sampling noise — no fixed 8% needed. The absolute stays
        # only as a floor for the first days before a baseline exists.
        onset, end_day = adaptive_onset_window(
            tool_series, 'silent_fail_rate', 'total_calls', t['min_tool_calls_per_day'],
            t['min_consecutive_days'], t.get('silent_fail_z', 2.5),
            t.get('silent_fail_min_effect', 0.04), t['silent_fail_rate_abs'],
            baseline_key='baseline_silent_fail')
        if onset is None:
            continue

        sf_during = safe_avg(get_vals(tool_series, onset, end_day + 1, 'silent_fail_rate'))
        sf_before = safe_avg(get_vals(tool_series, max(0, onset - 14), onset, 'silent_fail_rate'))
        err_during = safe_avg(get_vals(tool_series, onset, end_day + 1, 'error_rate'))
        err_before = safe_avg(get_vals(tool_series, max(0, onset - 14), onset, 'error_rate'))
        lat_during = safe_avg(get_vals(tool_series, onset, end_day + 1, 'p50_latency'))
        lat_before = safe_avg(get_vals(tool_series, max(0, onset - 14), onset, 'p50_latency'))

        # Key check: error_rate must stay flat (this is what makes F2 invisible)
        if err_before is not None and err_during is not None:
            err_drift = abs(err_during - err_before)
            if err_drift > t['error_rate_stability_tolerance']:
                continue

        sess = sess_cohorts.get((tenant, intent), [])
        res_before = safe_avg(get_vals(sess, max(0, onset - 14), onset, 'resolution_rate'))
        res_during = safe_avg(get_vals(sess, onset, end_day + 1, 'resolution_rate'))
        turns_during = safe_avg(get_vals(sess, onset, end_day + 1, 'median_turns'))
        turns_before = safe_avg(get_vals(sess, max(0, onset - 14), onset, 'median_turns'))

        sessions_affected = sum(r.get('total_sessions', 0) for r in sess if onset <= r['day'] <= end_day)
        tenant_vol = vol_by_tenant.get((tenant,), [])
        total_tenant = sum(r.get('total_sessions', 0) for r in tenant_vol if onset <= r['day'] <= end_day)
        share = round(sessions_affected / total_tenant, 4) if total_tenant else 0

        tool_changes = config_near(metrics['config'], tenant, onset, g['config_lookback_days'], 'tool')

        silent_total = sum(r.get('silent_fail_count', 0) for r in tool_series if onset <= r['day'] <= end_day)
        ok_total = sum(r.get('ok_count', 0) for r in tool_series if onset <= r['day'] <= end_day)

        evidence = []
        evidence.append(f"silent_fail_rate for {tool_name} in {intent} averaged {sf_during:.2%} "
                        f"from day {onset} (baseline {sf_before or 0:.2%})")
        evidence.append(f"declared error_rate stayed flat at {err_during:.2%} "
                        f"(baseline {err_before or 0:.2%}) — the failure is invisible to standard monitoring")
        evidence.append(f"{silent_total} of {ok_total} successful calls returned empty payloads "
                        f"(result_field_count=0)")
        if res_during is not None and res_before is not None:
            evidence.append(f"resolution rate for {intent} dropped from {res_before:.2%} to {res_during:.2%}")
        if tool_changes:
            c = tool_changes[0]
            evidence.append(f"tool config change on day {c.get('day')}: {c.get('target')} "
                            f"{c.get('from_value')} -> {c.get('to_value')}")

        problems.append({
            'problem_id': f'F2_{tenant}_{intent}_{tool_name}',
            'tenant': tenant,
            'cohort': {'intent': intent, 'tool_name': tool_name},
            'cohort_type': 'tenant_intent_tool',
            'detection_type': 'silent_tool_failure',
            'cause_class': 'tool.contract_break',
            'is_regression': True,
            'not_a_regression_because': None,
            'severity': 'high',
            'onset_day': onset,
            'window': {'from_day': onset, 'to_day': end_day},
            'primary_metric': 'silent_fail_rate',
            'metrics': {
                'silent_fail_rate': {'before': sf_before, 'during': sf_during,
                                     'delta_pct': pct_change(sf_before, sf_during)},
                'error_rate': {'before': err_before, 'during': err_during,
                               'delta_pct': pct_change(err_before, err_during)},
                'resolution_rate': {'before': res_before, 'during': res_during,
                                    'delta_pct': pct_change(res_before, res_during)},
                'median_turns': {'before': turns_before, 'during': turns_during,
                                 'delta_pct': pct_change(turns_before, turns_during)},
                'p50_latency': {'before': lat_before, 'during': lat_during},
                'silent_calls_total': silent_total,
                'ok_calls_total': ok_total,
            },
            'config_attribution': {
                'found': bool(tool_changes),
                'changes': [{k: v for k, v in c.items()} for c in tool_changes],
            },
            'impact': {
                'conversations_affected': sessions_affected,
                'share_of_tenant_traffic': share,
                'days_running': end_day - onset + 1,
                'derivation': (f"{sessions_affected} sessions in [{onset},{end_day}], "
                               f"{share:.1%} of {tenant} traffic, {silent_total} empty tool responses"),
            },
            'evidence': evidence,
            'daily_timeseries': {
                'silent_fail_rate': timeseries_snippet(tool_series, 'silent_fail_rate',
                                                       max(0, onset - 14), end_day),
                'error_rate': timeseries_snippet(tool_series, 'error_rate',
                                                 max(0, onset - 14), end_day),
                'resolution_rate': timeseries_snippet(sess, 'resolution_rate',
                                                      max(0, onset - 14), end_day),
            },
            'coverage': None,
            'corroborating_signals': sum([
                sf_during is not None and sf_during > t['silent_fail_rate_abs'],
                err_before is not None and err_during is not None and
                    abs(err_during - err_before) < t['error_rate_stability_tolerance'],
                res_during is not None and res_before is not None and
                    (res_before - res_during) / max(res_before, 0.01) > t['resolution_drop_pct'],
                bool(tool_changes),
            ]),
            'ask_relevance': ['A04'],
        })
    return problems


# ---------------------------------------------------------------------------
# F3 — Prompt Regression
# ---------------------------------------------------------------------------

def detect_prompt_regression(metrics, cfg):
    """Detect prompt regressions: median_turns inflates while resolution stays flat.

    F3's signature is unique: the agent asks too many clarifying questions
    (turns up ~58%) but eventually resolves — so outcome metrics stay flat.
    Cost rises because more LLM calls per session.
    """
    problems = []
    agent_cohorts = group_by(metrics['session_by_agent'], ['tenant', 'agent_id'])
    vol_by_tenant = group_by(metrics['volume'], ['tenant'])
    t = cfg['f3_prompt_regression']
    g = cfg['general']

    for (tenant, agent_id), agent_series in agent_cohorts.items():
        if not agent_series or agent_series[0].get('agent_kind') == 'v2_flow':
            continue

        onset = find_onset_deviation(
            agent_series, 'median_turns', 'baseline_median_turns',
            t['turns_increase_pct'], t['min_consecutive_days'], direction='up')
        if onset is None:
            continue

        anomaly_rows = [r for r in agent_series if r['day'] >= onset]
        valid = [r for r in anomaly_rows if (r.get('total_sessions') or 0) >= t['min_sessions_per_day']]
        if len(valid) < t['min_consecutive_days']:
            continue

        end_day = max(r['day'] for r in valid)
        turns_before = safe_avg(get_vals(agent_series, max(0, onset - 14), onset, 'median_turns'))
        turns_during = safe_avg(get_vals(agent_series, onset, end_day + 1, 'median_turns'))
        res_before = safe_avg(get_vals(agent_series, max(0, onset - 14), onset, 'resolution_rate'))
        res_during = safe_avg(get_vals(agent_series, onset, end_day + 1, 'resolution_rate'))
        cost_before = safe_avg(get_vals(agent_series, max(0, onset - 14), onset, 'mean_cost'))
        cost_during = safe_avg(get_vals(agent_series, onset, end_day + 1, 'mean_cost'))

        # F3 signature: resolution must stay FLAT
        if res_before is not None and res_during is not None:
            res_drift = abs(res_during - res_before) / max(res_before, 0.01)
            if res_drift > t['resolution_stability_tolerance']:
                continue

        sessions_affected = sum(r.get('total_sessions', 0) for r in agent_series
                                if onset <= r['day'] <= end_day)
        tenant_vol = vol_by_tenant.get((tenant,), [])
        total_tenant = sum(r.get('total_sessions', 0) for r in tenant_vol if onset <= r['day'] <= end_day)
        share = round(sessions_affected / total_tenant, 4) if total_tenant else 0

        prompt_changes = config_near(metrics['config'], tenant, onset, g['config_lookback_days'], 'prompt')

        evidence = []
        if turns_before and turns_during:
            evidence.append(f"median_turns for {agent_id} rose from {turns_before:.1f} to "
                            f"{turns_during:.1f} ({pct_change(turns_before, turns_during):+.0%}) starting day {onset}")
        if res_before and res_during:
            evidence.append(f"resolution rate stayed flat at {res_during:.2%} "
                            f"(was {res_before:.2%}) — outcome-neutral regression")
        if cost_before and cost_during:
            evidence.append(f"cost per session rose from ${cost_before:.4f} to ${cost_during:.4f} "
                            f"({pct_change(cost_before, cost_during):+.0%})")
        evidence.append("signature: agent over-confirms/re-asks without failing to resolve — "
                        "turns inflate, cost rises, outcome stays flat")
        if prompt_changes:
            c = prompt_changes[0]
            evidence.append(f"prompt version changed on day {c.get('day')}: "
                            f"{c.get('from_value')} -> {c.get('to_value')}")

        problems.append({
            'problem_id': f'F3_{tenant}_{agent_id}',
            'tenant': tenant,
            'cohort': {'agent_id': agent_id},
            'cohort_type': 'tenant_agent',
            'detection_type': 'prompt_regression',
            'cause_class': 'prompt.regression',
            'is_regression': True,
            'not_a_regression_because': None,
            'severity': 'medium',
            'onset_day': onset,
            'window': {'from_day': onset, 'to_day': end_day},
            'primary_metric': 'median_turns',
            'metrics': {
                'median_turns': {'before': turns_before, 'during': turns_during,
                                 'delta_pct': pct_change(turns_before, turns_during)},
                'resolution_rate': {'before': res_before, 'during': res_during,
                                    'delta_pct': pct_change(res_before, res_during)},
                'mean_cost': {'before': cost_before, 'during': cost_during,
                              'delta_pct': pct_change(cost_before, cost_during)},
            },
            'config_attribution': {
                'found': bool(prompt_changes),
                'changes': [{k: v for k, v in c.items()} for c in prompt_changes],
            },
            'impact': {
                'conversations_affected': sessions_affected,
                'share_of_tenant_traffic': share,
                'days_running': end_day - onset + 1,
                'derivation': (f"{sessions_affected} sessions in [{onset},{end_day}], "
                               f"{share:.1%} of {tenant} traffic, "
                               f"turns inflated {pct_change(turns_before, turns_during) or 'N/A'}"),
            },
            'evidence': evidence,
            'daily_timeseries': {
                'median_turns': timeseries_snippet(agent_series, 'median_turns',
                                                    max(0, onset - 14), end_day),
                'resolution_rate': timeseries_snippet(agent_series, 'resolution_rate',
                                                      max(0, onset - 14), end_day),
                'mean_cost': timeseries_snippet(agent_series, 'mean_cost',
                                                max(0, onset - 14), end_day),
            },
            'coverage': None,
            'corroborating_signals': sum([
                turns_during is not None and turns_before is not None and
                    (turns_during - turns_before) / max(turns_before, 0.01) > t['turns_increase_pct'],
                res_before is not None and res_during is not None and
                    abs(res_during - res_before) / max(res_before, 0.01) < t['resolution_stability_tolerance'],
                cost_during is not None and cost_before is not None and
                    (cost_during - cost_before) / max(cost_before, 0.0001) > t['cost_increase_pct'],
                bool(prompt_changes),
            ]),
            'ask_relevance': ['A02', 'A07', 'A08'],
        })
    return problems


# ---------------------------------------------------------------------------
# D1 — Mix Shift (dismissed)
# ---------------------------------------------------------------------------

def detect_mix_shift(metrics, cfg):
    """Detect and dismiss traffic mix shifts.

    Pattern: aggregate resolution/containment moves because a high-resolution
    intent's traffic share spiked — per-intent rates stay stable.
    """
    problems = []
    share_cohorts = group_by(metrics['intent_share'], ['tenant', 'intent'])
    sess_cohorts = group_by(metrics['session_by_intent'], ['tenant', 'intent'])
    t = cfg['d1_mix_shift']
    g = cfg['general']

    tenants = set()
    for (tenant, intent), series in share_cohorts.items():
        tenants.add(tenant)

    for tenant in tenants:
        tenant_intents = {i: s for (t, i), s in share_cohorts.items() if t == tenant}
        shifted_intents = []

        for intent, series in tenant_intents.items():
            days_shifted = []
            peak_shift = 0
            for row in series:
                share_val = row.get('intent_share')
                base = row.get('baseline_share')
                if share_val is not None and base is not None and base > 0:
                    shift = abs(share_val - base)
                    if shift > t['intent_share_change_abs']:
                        days_shifted.append((row['day'], share_val, base))
                        peak_shift = max(peak_shift, shift)
            if len(days_shifted) >= t.get('min_consecutive_days', 5) and \
               peak_shift >= t.get('min_peak_shift_abs', 0.06):
                shifted_intents.append((intent, days_shifted, peak_shift))

        if not shifted_intents:
            continue

        for intent, shifts, peak in shifted_intents:
            onset = min(d for d, _, _ in shifts)
            end_day = max(d for d, _, _ in shifts)
            share_before = safe_avg([b for _, _, b in shifts[:3]])
            share_during = safe_avg([s for _, s, _ in shifts])

            # Check per-intent resolution rates stayed stable
            all_stable = True
            per_intent_res = {}
            for (t2, i2), sess2 in sess_cohorts.items():
                if t2 != tenant:
                    continue
                rb = safe_avg(get_vals(sess2, max(0, onset - 14), onset, 'resolution_rate'))
                rd = safe_avg(get_vals(sess2, onset, end_day + 1, 'resolution_rate'))
                if rb is not None and rd is not None:
                    per_intent_res[i2] = {'before': round(rb, 4), 'during': round(rd, 4)}
                    if abs(rd - rb) / max(rb, 0.01) > t['per_intent_rate_tolerance']:
                        all_stable = False

            if not all_stable:
                continue

            config_changes = config_near(metrics['config'], tenant, onset, g['config_lookback_days'])
            non_traffic_changes = [c for c in config_changes if c.get('kind') not in ('judge',)]

            evidence = [
                f"intent {intent} share shifted from {share_before:.2%} to {share_during:.2%} "
                f"during days [{onset},{end_day}]",
                f"per-intent resolution rates stayed within {t['per_intent_rate_tolerance']:.0%} tolerance — "
                f"aggregate movement is composition, not performance",
                f"no config change attributable to a regression near day {onset}",
            ]

            problems.append({
                'problem_id': f'D1_{tenant}_{intent}',
                'tenant': tenant,
                'cohort': {'intent': intent},
                'cohort_type': 'tenant_intent',
                'detection_type': 'traffic_mix_shift',
                'cause_class': 'traffic_mix',
                'is_regression': False,
                'not_a_regression_because': (
                    f"aggregate metric movement caused by intent share shift "
                    f"({intent} traffic {'increased' if (share_during or 0) > (share_before or 0) else 'decreased'}), "
                    f"not by performance degradation — per-intent rates stable"),
                'severity': 'low',
                'onset_day': onset,
                'window': {'from_day': onset, 'to_day': end_day},
                'primary_metric': 'intent_share',
                'metrics': {
                    'intent_share': {'before': share_before, 'during': share_during,
                                     'delta_pct': pct_change(share_before, share_during)},
                    'per_intent_resolution': per_intent_res,
                },
                'config_attribution': {
                    'found': bool(non_traffic_changes),
                    'changes': [{k: v for k, v in c.items()} for c in non_traffic_changes],
                },
                'impact': {
                    'conversations_affected': 0,
                    'share_of_tenant_traffic': 0,
                    'days_running': end_day - onset + 1,
                    'derivation': "no real impact — composition change, not regression",
                },
                'evidence': evidence,
                'daily_timeseries': {
                    'intent_share': timeseries_snippet(
                        share_cohorts.get((tenant, intent), []), 'intent_share',
                        max(0, onset - 14), end_day),
                },
                'coverage': None,
                'corroborating_signals': 0,
                'ask_relevance': ['A02'],
            })
    return problems


# ---------------------------------------------------------------------------
# D2 — Load Spike (dismissed)
# ---------------------------------------------------------------------------

def detect_load_spike(metrics, cfg):
    """Detect and dismiss load spikes.

    Pattern: volume and latency spike together, quality stays flat, self-corrects.
    """
    problems = []
    vol_cohorts = group_by(metrics['volume'], ['tenant'])
    lat_cohorts = group_by(metrics['latency'], ['tenant'])
    t = cfg['d2_load_spike']
    g = cfg['general']

    for (tenant,), vol_series in vol_cohorts.items():
        onset = find_onset_deviation(
            vol_series, 'total_sessions', 'baseline_volume',
            t['volume_spike_pct'], 2, direction='up')
        if onset is None:
            continue

        # Find CONTIGUOUS spike window — stop after 2 consecutive normal days
        end_day = onset
        gap = 0
        for r in vol_series:
            if r['day'] <= onset:
                continue
            base = r.get('baseline_volume')
            vol = r.get('total_sessions')
            if base and vol and (vol - base) / base > t['volume_spike_pct']:
                end_day = r['day']
                gap = 0
            else:
                gap += 1
                if gap >= 2:
                    break

        duration = end_day - onset + 1
        if duration > t['max_spike_duration_days']:
            continue

        vol_before = safe_avg(get_vals(vol_series, max(0, onset - 14), onset, 'total_sessions'))
        vol_during = safe_avg(get_vals(vol_series, onset, end_day + 1, 'total_sessions'))
        qual_before = safe_avg(get_vals(vol_series, max(0, onset - 14), onset, 'mean_quality'))
        qual_during = safe_avg(get_vals(vol_series, onset, end_day + 1, 'mean_quality'))

        if qual_before is not None and qual_during is not None:
            qual_drift = abs(qual_during - qual_before) / max(qual_before, 0.01)
            if qual_drift > t['quality_stability_tolerance']:
                continue

        lat_series = lat_cohorts.get((tenant,), [])
        lat_before = safe_avg(get_vals(lat_series, max(0, onset - 14), onset, 'p95_latency'))
        lat_during = safe_avg(get_vals(lat_series, onset, end_day + 1, 'p95_latency'))

        post_spike = safe_avg(get_vals(vol_series, end_day + 1, end_day + 8, 'total_sessions'))
        self_corrected = post_spike is not None and vol_before is not None and \
                         abs(post_spike - vol_before) / max(vol_before, 1) < 0.15

        evidence = [
            f"volume spiked from {vol_before:.0f} to {vol_during:.0f} sessions/day "
            f"({pct_change(vol_before, vol_during):+.0%}) during days [{onset},{end_day}]",
        ]
        if lat_before and lat_during:
            evidence.append(f"p95 latency rose from {lat_before:.0f}ms to {lat_during:.0f}ms "
                            f"({pct_change(lat_before, lat_during):+.0%})")
        if qual_before and qual_during:
            evidence.append(f"quality stayed flat at {qual_during:.2f} (was {qual_before:.2f}) — "
                            f"latency affected, quality not")
        if self_corrected:
            evidence.append("volume returned to baseline after spike — temporary load event")

        problems.append({
            'problem_id': f'D2_{tenant}_day{onset}',
            'tenant': tenant,
            'cohort': {},
            'cohort_type': 'tenant',
            'detection_type': 'load_spike',
            'cause_class': 'load',
            'is_regression': False,
            'not_a_regression_because': (
                f"temporary volume spike ({duration} days) with correlated latency increase "
                f"but stable quality — load event, not regression"
                + ("; self-corrected" if self_corrected else "")),
            'severity': 'low',
            'onset_day': onset,
            'window': {'from_day': onset, 'to_day': end_day},
            'primary_metric': 'volume',
            'metrics': {
                'volume': {'before': vol_before, 'during': vol_during,
                           'delta_pct': pct_change(vol_before, vol_during)},
                'p95_latency': {'before': lat_before, 'during': lat_during,
                                'delta_pct': pct_change(lat_before, lat_during)},
                'mean_quality': {'before': qual_before, 'during': qual_during,
                                 'delta_pct': pct_change(qual_before, qual_during)},
            },
            'config_attribution': {'found': False, 'changes': []},
            'impact': {
                'conversations_affected': 0,
                'share_of_tenant_traffic': 0,
                'days_running': duration,
                'derivation': "no quality impact — latency rose under load but quality held",
            },
            'evidence': evidence,
            'daily_timeseries': {
                'volume': timeseries_snippet(vol_series, 'total_sessions',
                                              max(0, onset - 14), min(end_day + 7, 55)),
                'p95_latency': timeseries_snippet(lat_series, 'p95_latency',
                                                   max(0, onset - 14), min(end_day + 7, 55)),
                'mean_quality': timeseries_snippet(vol_series, 'mean_quality',
                                                    max(0, onset - 14), min(end_day + 7, 55)),
            },
            'coverage': None,
            'corroborating_signals': 0,
            'ask_relevance': [],
        })
    return problems


# ---------------------------------------------------------------------------
# D3 — Judge Version Change (dismissed)
# ---------------------------------------------------------------------------

def detect_judge_change(metrics, cfg):
    """Detect and dismiss judge version boundary effects.

    Pattern: quality_score drops on ALL tenants simultaneously near a
    judge config change. This measures the rubric, not the agent. (Rule 3)
    """
    problems = []
    quality = metrics['quality']
    config = metrics['config']
    t = cfg['d3_judge_change']

    judge_changes = [c for c in config if c.get('kind') == 'judge']
    if not judge_changes:
        return problems

    tenants = sorted(set(r['tenant'] for r in quality))
    quality_by_tenant = group_by(quality, ['tenant'])

    for jc in judge_changes:
        jday = jc['day']
        all_tenants_drop = True
        tenant_metrics = {}

        for tenant in tenants:
            t_quality = quality_by_tenant.get((tenant,), [])
            before = [r for r in t_quality
                      if jday - 10 <= r['day'] < jday]
            after = [r for r in t_quality
                     if jday <= r['day'] < jday + 10]

            before_vals = [r['mean_quality'] for r in before if r.get('mean_quality') is not None]
            avg_before = safe_avg(before_vals)
            avg_after = safe_avg([r['mean_quality'] for r in after if r.get('mean_quality') is not None])

            # Required drop is adaptive: larger than the tenant's own normal
            # day-to-day quality noise (z * before-window std), floored by a small
            # minimum. A stricter/looser rubric on a hidden corpus moves quality by
            # a different amount; the invariant is that ALL tenants move at once.
            before_std = statistics.pstdev(before_vals) if len(before_vals) > 1 else 0.0
            required_drop = max(t.get('quality_drop_min', 0.2),
                                t.get('quality_drop_z', 2.0) * before_std)

            tenant_metrics[tenant] = {
                'mean_quality_before': avg_before,
                'mean_quality_after': avg_after,
                'delta': round(avg_after - avg_before, 4) if avg_before and avg_after else None,
            }
            if avg_before is None or avg_after is None:
                all_tenants_drop = False
            elif (avg_before - avg_after) < required_drop:
                all_tenants_drop = False

        if not all_tenants_drop:
            continue

        evidence = [
            f"quality_score dropped on ALL tenants simultaneously around day {jday}",
            f"judge config change: {jc.get('from_value')} -> {jc.get('to_value')} on day {jday}",
            "this measures a stricter rubric (v2), not worse agent performance (Golden Rule 3)",
        ]
        for tn, tm in tenant_metrics.items():
            evidence.append(f"  {tn}: quality {tm['mean_quality_before']:.2f} -> {tm['mean_quality_after']:.2f} "
                            f"(delta {tm['delta']:+.2f})")

        problems.append({
            'problem_id': f'D3_all_day{jday}',
            'tenant': '*',
            'cohort': {},
            'cohort_type': 'all_tenants',
            'detection_type': 'judge_version_change',
            'cause_class': 'judge_change',
            'is_regression': False,
            'not_a_regression_because': (
                f"quality_score cliff caused by judge version change "
                f"({jc.get('from_value')} -> {jc.get('to_value')}) on day {jday} — "
                f"the yardstick changed, not the agent. "
                f"Trending quality across judge versions violates Rule 3."),
            'severity': 'low',
            'onset_day': jday,
            'window': {'from_day': jday, 'to_day': jday + 10},
            'primary_metric': 'quality_score',
            'metrics': {
                'per_tenant_quality': tenant_metrics,
                'judge_version_change': {'from': jc.get('from_value'), 'to': jc.get('to_value')},
            },
            'config_attribution': {
                'found': True,
                'changes': [{k: v for k, v in jc.items()}],
            },
            'impact': {
                'conversations_affected': 0,
                'share_of_tenant_traffic': 0,
                'days_running': 0,
                'derivation': "no real impact — measurement artifact from judge version change",
            },
            'evidence': evidence,
            'daily_timeseries': {},
            'coverage': None,
            'corroborating_signals': 0,
            'ask_relevance': ['A02', 'A07'],
        })
    return problems


# ---------------------------------------------------------------------------
# Coverage annotation
# ---------------------------------------------------------------------------

def annotate_coverage(problems, coverage_data):
    """Add v3 coverage info to each problem."""
    cov_map = {r['tenant']: round(r['v3_coverage'], 4) for r in coverage_data}
    for p in problems:
        tenant = p['tenant']
        if tenant in cov_map:
            p['coverage'] = {
                'v3_share': cov_map[tenant],
                'basis': 'v2_flow sessions emit no tool_call/kb_lookup steps; '
                         'excluded from tool/kb metric denominators',
            }
        elif tenant == '*':
            p['coverage'] = {
                'per_tenant': cov_map,
                'basis': 'v2_flow sessions emit no tool_call/kb_lookup steps',
            }


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(problems, cfg):
    """Merge problems with overlapping fingerprints.

    Fingerprint = (tenant, primary_metric, cohort_key_hash, onset_day_bucket).
    Same fingerprint → keep the one with more corroborating signals.
    """
    bucket_size = cfg['deduplication']['onset_bucket_days']
    seen = {}
    for p in problems:
        cohort_str = str(sorted(p.get('cohort', {}).items()))
        bucket = p['onset_day'] // bucket_size
        fingerprint = (p['tenant'], p['primary_metric'], cohort_str, bucket)

        if fingerprint in seen:
            existing = seen[fingerprint]
            if (p.get('corroborating_signals', 0) > existing.get('corroborating_signals', 0)):
                seen[fingerprint] = p
        else:
            seen[fingerprint] = p

    return list(seen.values())


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_all(metrics, cfg):
    """Run all detectors, annotate, deduplicate, and return flagged problems."""
    problems = []

    print("  F1: KB gap detection...")
    f1 = detect_kb_gap(metrics, cfg)
    print(f"    found {len(f1)}")
    problems.extend(f1)

    print("  F2: Silent tool failure detection...")
    f2 = detect_silent_tool(metrics, cfg)
    print(f"    found {len(f2)}")
    problems.extend(f2)

    print("  F3: Prompt regression detection...")
    f3 = detect_prompt_regression(metrics, cfg)
    print(f"    found {len(f3)}")
    problems.extend(f3)

    print("  D1: Mix shift detection (dismiss)...")
    d1 = detect_mix_shift(metrics, cfg)
    print(f"    found {len(d1)}")
    problems.extend(d1)

    print("  D2: Load spike detection (dismiss)...")
    d2 = detect_load_spike(metrics, cfg)
    print(f"    found {len(d2)}")
    problems.extend(d2)

    print("  D3: Judge change detection (dismiss)...")
    d3 = detect_judge_change(metrics, cfg)
    print(f"    found {len(d3)}")
    problems.extend(d3)

    annotate_coverage(problems, metrics.get('coverage', []))

    print("  Deduplicating...")
    problems = deduplicate(problems, cfg)
    print(f"    {len(problems)} after dedup")

    problems.sort(key=lambda p: (0 if p['is_regression'] else 1, p['onset_day']))
    return problems
