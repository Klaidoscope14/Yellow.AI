"""Robustness tests for the adaptive detection thresholds.

These simulate a *hidden corpus with different base rates* and assert the
adaptive bars do the right thing where a fixed absolute threshold would not.
Run: ../../.venv/bin/python test_adaptive_thresholds.py   (also pytest-compatible)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/pipeline")

import detect  # noqa: E402


def _series(days, miss, n, key="silent_fail_rate", count="total_calls", baseline=None):
    rows = []
    for i, d in enumerate(days):
        row = {"day": d, key: miss[i], count: n[i]}
        if baseline is not None:
            row["baseline_silent_fail"] = baseline[i]
        rows.append(row)
    return rows


def test_high_baseline_healthy_cohort_not_flagged():
    """Hidden corpus where normal silent-fail sits at 10% (above the old 0.08
    absolute). A healthy cohort hovering at its baseline must NOT be flagged."""
    days = list(range(20, 30))
    val = [0.10, 0.11, 0.09, 0.10, 0.12, 0.10, 0.11, 0.09, 0.10, 0.11]
    base = [0.10] * 10
    n = [200] * 10
    onset, _ = detect.adaptive_onset_window(
        _series(days, val, n, baseline=base), "silent_fail_rate", "total_calls",
        3, 3, 2.5, 0.04, 0.08, baseline_key="baseline_silent_fail")
    assert onset is None, f"healthy high-baseline cohort wrongly flagged at {onset}"
    # An absolute 0.08 threshold WOULD have flagged every day here.
    assert all(v > 0.08 for v in val)


def test_real_spike_above_baseline_flagged():
    """A genuine contract break: silent-fail jumps well above the cohort's own
    baseline for a sustained run -> flagged, with correct onset."""
    days = list(range(30, 42))
    val = [0.01, 0.01, 0.0, 0.01, 0.0, 0.01, 0.18, 0.20, 0.19, 0.21, 0.18, 0.20]
    base = [0.01] * 12
    n = [300] * 12
    onset, end = detect.adaptive_onset_window(
        _series(days, val, n, baseline=base), "silent_fail_rate", "total_calls",
        3, 3, 2.5, 0.04, 0.08, baseline_key="baseline_silent_fail")
    assert onset == 36, f"expected onset 36, got {onset}"
    assert end == 41, f"expected end 41, got {end}"


def test_small_sample_spike_suppressed():
    """The same rate spike on a handful of calls is within sampling noise -> not
    flagged. Wide SE protects against tiny-cohort false positives."""
    days = list(range(30, 36))
    val = [0.0, 0.0, 0.34, 0.34, 0.0, 0.0]   # 0.34 but on n=3
    base = [0.0] * 6
    n = [3, 3, 3, 3, 3, 3]
    onset, _ = detect.adaptive_onset_window(
        _series(days, val, n, baseline=base), "silent_fail_rate", "total_calls",
        3, 3, 2.5, 0.04, 0.08, baseline_key="baseline_silent_fail")
    assert onset is None, f"tiny-n spike should be suppressed, flagged at {onset}"


def test_kb_peer_relative_outlier_flagged_when_normal_is_high():
    """Hidden corpus where the normal KB miss rate is 0.6 (a fixed 0.5 absolute
    would flag EVERY cohort). Peer-relative bar flags only the true outlier."""
    days = list(range(30, 40))
    # sibling cohorts sit at ~0.6; the broken cohort sits at ~0.95
    peers = {d: 0.60 for d in days}
    broken = _series(days, [0.95] * 10, [80] * 10, key="kb_miss_rate", count="total_lookups")
    onset, _ = detect.adaptive_onset_window(
        broken, "kb_miss_rate", "total_lookups", 5, 3, 2.5, 0.15, 0.5,
        baseline_by_day=peers)
    assert onset == 30, f"broken cohort should flag at 30, got {onset}"

    healthy = _series(days, [0.60] * 10, [80] * 10, key="kb_miss_rate", count="total_lookups")
    onset_h, _ = detect.adaptive_onset_window(
        healthy, "kb_miss_rate", "total_lookups", 5, 3, 2.5, 0.15, 0.5,
        baseline_by_day=peers)
    assert onset_h is None, "a cohort at the (high) peer level must not be flagged"


def test_partial_gap_below_absolute_floor_still_caught():
    """Hidden corpus where normal miss is low (0.05) and a partial gap pushes a
    cohort to 0.35 — below the old 0.5 absolute, but clearly above peers."""
    days = list(range(30, 40))
    peers = {d: 0.05 for d in days}
    partial = _series(days, [0.35] * 10, [120] * 10, key="kb_miss_rate", count="total_lookups")
    onset, _ = detect.adaptive_onset_window(
        partial, "kb_miss_rate", "total_lookups", 5, 3, 2.5, 0.15, 0.5,
        baseline_by_day=peers)
    assert onset == 30, f"a partial gap (0.35 vs 0.05 peers) should flag, got {onset}"
    assert 0.35 < 0.5  # the old absolute floor would have missed it


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(tests)} passed")
