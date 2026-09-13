# Nexus Loop — Implementation Prompt (Unified Architecture)

**How to use this doc:** This is written to be handed directly to a coding
agent (Claude Code or a human engineer) working inside the existing repo.
It assumes the current build already exists at `tools/nexus-loop-kit/`
(`pipeline.py`, `orchestrator.py`) and scores **38.0/55** on Level 1. Do
NOT rewrite from scratch. Every task below is a diff against what exists,
in priority order. Stop and verify with `score.py` after each priority
tier before moving to the next.

---

## 0. Context to Load Before Starting

Read, in this order:
1. `kit/catalog.json` — the semantic contract. Every join, denominator,
   and capability class is declared here.
2. `tools/nexus-loop-kit/pipeline.py` — current implementation.
3. `tools/nexus-loop-kit/orchestrator.py` — trust/conflict resolver
   (currently unused by pipeline.py, will stay unused for now).
4. `tools/nexus-loop-kit/schema/loop-report.schema.json` — the contract
   the output must satisfy.
5. `tools/nexus-loop-kit/score.py` — treat this as ground truth for what
   "correct" means. When in doubt, read the scoring function, not this
   document.

Do not modify: `generate.py`, `starter.py`, `score.py`, the schema, or
anything under `kit/corpus/`, `kit/labels/`, `kit/ground_truth/`.

---

## 1. PRIORITY 0 (BLOCKING) — Remove Hardcoded Candidate Scope

### Problem
`Level1Specialists.regression()` in `pipeline.py` hardcodes:
```python
affected = self._window_sessions("acme-bank", "premium_card_info", "v3_agent", 35, 45)
peer = self._window_sessions("acme-bank", "product_info", "v3_agent", 35, 45)
```
This will silently produce wrong or empty output against the Day 6 sealed
dataset, which uses different tenants, days, and intents for the same
fault *types*.

### Task
Replace hardcoded window selection with generic candidate discovery.

**New function: `discover_candidates(session_agg, step_agg, contract)`**

Implement as follows:

```
For each (tenant, intent, agent_kind) triple present in session_agg:
    build a weekly time series of:
        - resolution_rate
        - turns_to_resolve (median)
        - cost_per_session
        - tool_failure_rate (if agent_kind has tool_call rows; else skip)
        - kb_hit_rate, kb_top_score (if kb_lookup rows present)

    Determine if the cohort HAS a before-period:
        before-period exists if the cohort has >= N_MIN sessions
        (N_MIN = 30) in at least 2 consecutive weeks BEFORE any
        candidate window under test.

    IF before-period exists:
        baseline = same cohort, pre-change weeks (HISTORICAL baseline)
    ELSE:
        baseline = peer cohorts: same tenant, same agent_kind,
                   same catalog-declared intent CLASS (e.g. both
                   "question_answering" type intents), same window
                   (PEER baseline)

    For each metric x cohort x week-window combination:
        effect_size = abs(observed - baseline) / baseline   (relative)
                      OR abs(observed - baseline)            (absolute,
                      for rate metrics already in [0,1])
        n = session count in the window

        IF effect_size > EFFECT_THRESHOLD (0.05 absolute for rate
           metrics, 0.15 relative for turns/cost) AND n >= N_MIN:
               emit a Candidate{tenant, intent, agent_kind, metric,
                                 window, observed, baseline,
                                 baseline_kind, n, effect_size}

Return: list[Candidate], sorted by effect_size descending.
```

**Critical constraint:** No tenant name, intent name, day number, or
agent_kind string may appear as a literal anywhere in this function or
in the classification stage that follows it. If you find yourself
writing `if intent == "premium_card_info"`, stop — that is the bug
class we are removing. The ONLY way a specific intent should show up in
output is because it was discovered from the data.

### Acceptance test (write this before moving on)
Create `tests/test_no_hardcoding.py`:
```python
def test_pipeline_survives_renamed_tenants(tmp_corpus_with_renamed_tenants):
    """
    Take corpus_sample/, rewrite tenant strings
    (acme-bank -> tenant_x, northwind -> tenant_y) and shift every day
    value by +100, WITHOUT changing anything else about the data
    (same relative structure, same faults, same decoys).
    Run the full pipeline against this. Assert:
      - the same NUMBER of real findings and decoys is produced
      - none of the original literal strings appear anywhere in the
        candidate discovery code path
      - effect sizes and cohort ns match within tolerance to a run
        against the un-renamed original
    """
```
Do not proceed to Priority 1 until this test passes. This is the single
highest-leverage fix in the entire project — it is what makes the Day 6
sealed run trustworthy at all.

---

## 2. PRIORITY 1 — Extend Preprocessor for F2 (Silent Tool Failure)

### Problem
The step aggregate currently tracks `tool_calls`, `tool_errors`
(`outcome != ok`), and latency. It does NOT track the case where a tool
call returns `outcome == 'ok'` (status 200) but with an empty or
malformed payload — a "silent" failure that no error-rate metric can
see, by design (this is the F2 planted fault).

### Task
In the step aggregate builder (`Preprocessor`), add:

```python
if row["step_type"] == "tool_call":
    item["tool_calls"] += 1
    item["tool_errors"] += row["outcome"] != "ok"
    item["durations"].append(row.get("duration_ms") or 0)
    # NEW: derive silent success
    is_silent_failure = (
        row["outcome"] == "ok"
        and row.get("status_code") == 200
        and (row.get("response_bytes", 0) == 0
             or row.get("result_field_count", 0) == 0)
    )
    item["silent_failures"] += is_silent_failure
    if is_silent_failure:
        item["silent_failure_session_ids"].add(row["session_id"])
```

Also track, per session, whether a **retry on the same tool_name**
occurred within the session after a silent failure, and whether that
session ended unresolved. This linkage (silent failure → same-tool
retry → unresolved end) is the evidence chain for D-SILENT-TOOL, and it
is what makes this finding's derivation string credible rather than a
bare correlation.

Declare this derivation explicitly in the AnalysisContract rules list:
```
"silent_tool_success is DERIVED (class derivable_not_declared per
 catalog.json): status_code==200 AND response_bytes==0 is treated as
 a tool failure even though outcome=='ok'. This is a declared
 derivation, not a raw field — cite it as such in system_notes."
```

### Acceptance test
Run against `corpus_sample/`. Confirm `silent_failures` is nonzero for
at least one tool_name/tenant combination, and that plain
`tool_failure_rate` (based on `outcome != ok`) is FLAT for that same
tool over the same window — this flatness is the signature that proves
the fault is genuinely invisible to naive error-rate monitoring.

---

## 3. PRIORITY 2 — Move Standard Mining Before Detection

### Problem
In `orchestrator.py` / the intended state machine, standard mining is
sequenced AFTER detection. But the F3 fault (outcome-flat,
efficiency-degraded prompt regression) can only be detected by
comparing a cohort against its OWN standard — there is no other valid
baseline for it (peer comparison doesn't apply; it's not a new intent,
and the outcome metric doesn't move, so historical baseline shows
nothing wrong). Standard mining is a **dependency** of detection, not a
downstream step.

### Task
**New module: `mine_standard(session_agg, step_agg, contract)`**

```
For each (tenant, agent_id or intent) cohort with n >= N_MIN sessions:
    for each metric in {resolution_rate, turns_to_resolve, cost_per_session}:
        sort session-level values for the cohort
        best = value at the 90th percentile (top-decile, direction-aware:
               for resolution_rate, top decile = HIGH values;
               for turns_to_resolve / cost, top decile = LOW values)
        median = cohort median
        deficit = |median - best|
        exemplar_session_ids = the sessions contributing to the top decile
    freeze golden_set_version = a hash of (exemplar_session_ids, metric_
        definitions_version) — this must not change once computed, per
        Rule 2 (never move the yardstick).

Emit standard[] entries per schema:
    {tenant, cohort, metric, best, median, deficit, exemplar_n,
     golden_set_version, derivation}
```

**Sequencing fix:** In the pipeline entrypoint, call `mine_standard()`
immediately after `Preprocessor` completes and BEFORE
`discover_candidates()` / the specialist dispatch. Pass the standard
output into the regression specialist so D-STANDARD has a baseline to
compare against.

### Why this matters (state explicitly in code comments)
This is not a stylistic reordering. D-STANDARD literally has no
baseline to compare against if standard mining runs after detection —
the detector would either not fire or fire against a null baseline.
Any implementation that runs these in the original order is not a
different design choice, it's a broken dependency graph.

---

## 4. PRIORITY 3 — Add the Two Missing Real-Fault Detectors

Current build has D-KB (F1) only. Add D-SILENT-TOOL (F2) and
D-STANDARD (F3) as new methods on `Level1Specialists` (or its Level-2
successor class — naming is your call, but keep them as siblings of the
existing `regression()` method, not bolted onto it as an if/else).

### D-SILENT-TOOL(cause_class = tool.contract_break)
```
Input: preprocessed step_agg with silent_failures (Priority 1),
       candidates from discover_candidates() filtered to metric in
       {tool-related}.

Signal:
    - tool_failure_rate (outcome != ok) is FLAT across the window
      (this flatness is required evidence, not incidental)
    - silent_failures for a specific tool_name rises sharply in the
      window
    - sessions with a silent failure show retry_count > 0 on the SAME
      tool_name later in the session
    - those sessions' resolution rate is measurably below the cohort's
      peer/historical baseline

Attribution:
    Find a config change with kind='tool', target == tool_name, within
    onset ± 3 days. If none found within tolerance, cause_class remains
    tool.contract_break but attributed_change is omitted and this MUST
    be stated honestly in the diagnosis (do not force a match).

Emit finding:
    is_regression: true
    cohort: {intent, tool_name}
    metric: resolution_rate (primary), silent_failures (supporting
            evidence, cited in derivation)
    evidence must explicitly state: "tool_failure_rate remained flat
    at X; the fault is only visible via the derived silent_success
    signal" — this sentence IS the specificity/honesty point, write it
    verbatim into the finding's evidence field, not just into your
    own understanding of the code.
```

### D-STANDARD (cause_class = prompt.regression)
```
Input: standard[] from Priority 2, candidates from discover_candidates()
       for cohorts on turns_to_resolve / cost_per_session.

Signal:
    - resolution_rate for the cohort is FLAT (within noise) across the
      window — this flatness is required; if resolution_rate also
      moved, this is not this fault type, re-route to another detector.
    - turns_to_resolve and/or cost_per_session are elevated RELATIVE TO
      THE COHORT'S OWN STANDARD (not relative to a fixed threshold, not
      relative to peers).

Attribution:
    Find config change kind='prompt' on the cohort's agent_id, within
    onset ± 3 days. MISATTRIBUTION GUARD: if there is also a
    kind='routing' change on the SAME agent_id within the window,
    explicitly reject it as a candidate cause in the diagnosis's
    rejected_candidates field, and state why (the behavior tracks the
    prompt marker's timing more closely than the routing marker's —
    show the day deltas for both).

Emit finding:
    is_regression: true
    cohort: {agent_id}
    metric: turns_to_resolve (this is the metric that must ALSO be used
            later at replay time — see Priority 6, metric mismatch trap)
    replay_metric: median_turns   # NOT resolution_rate
```

### Acceptance test
Run on full `corpus_sample/`, then full corpus. Confirm all 3 real
findings (F1, F2, F3) are emitted with `is_regression=true`, each with a
non-null `impact`, `audience`, `if_nothing_changes`. Run `score.py` —
Diagnostic Accuracy (20 pts) and Specificity (15 pts) should both rise
substantially. Target after this tier: **>45/55** machine score.

---

## 5. PRIORITY 4 — Precedence-Ordered Classification (Replaces Trust Model)

### Decision being made here
`orchestrator.py`'s Beta-posterior trust model is NOT being ported into
the Level 2 pipeline. It solves inter-agent conflict ranking, which
`score.py` does not reward and which mostly does not occur here because
detectors operate on disjoint signal types. Keep `orchestrator.py`
in the repo untouched (it can still be shown as a demo/discussion
artifact), but do not wire it into the scoring-critical path.

### Task
Instead, implement classification as **fixed precedence, not learned
trust**:

```python
def classify(candidate, contract, step_agg, session_agg, config_timeline):
    # Check decoy signatures FIRST — cheaper to test, and the PS states
    # explicitly that a false regression flag costs more than a missed
    # one. Precedence order encodes that asymmetry directly.
    if matches_traffic_mix(candidate, session_agg):
        return decoy_finding(candidate, cause_class="traffic_mix")
    if matches_load_event(candidate, step_agg):
        return decoy_finding(candidate, cause_class="load")
    if matches_judge_boundary(candidate, config_timeline):
        return decoy_finding(candidate, cause_class="judge_change")

    # Only if no decoy signature matches, attempt real-fault classification
    if matches_kb_gap_signature(candidate, step_agg):
        return real_finding(candidate, detector="D-KB")
    if matches_silent_tool_signature(candidate, step_agg):
        return real_finding(candidate, detector="D-SILENT-TOOL")
    if matches_standard_deviation_signature(candidate, standard):
        return real_finding(candidate, detector="D-STANDARD")

    # Matches nothing confidently — do NOT force a classification.
    return None  # drop the candidate; under-reporting beats a stray finding
```

**One-line safety guard to port from `orchestrator.py`** (keep this
part, it's cheap and correct): if two classifiers claim the SAME
candidate with different `scope_key` (different denominator or grain),
do not silently pick one — write both to `system_notes` under an
"escalated" list and exclude the candidate from findings until resolved
by a human reading the note. This preserves the useful principle
("trust cannot make incompatible evidence comparable") without the
posterior machinery.

### Acceptance test
Confirm no candidate is ever emitted as BOTH a decoy and a real finding.
Confirm the `system_notes.escalated` list is empty on a clean run
against `corpus_sample/` and full corpus (if it's non-empty, a
detector's signature is too loose — tighten it, don't rank around it).

---

## 6. PRIORITY 5 — Level 2: Prescribe, Verify, Decide

Only start this once Priority 0–4 are done and `score.py` shows the
Level 1 categories (Diagnostic Accuracy, Specificity, Honesty, Loop
Completeness) are near their ceiling.

### Prescribe
```python
CAUSE_TO_FIX = {
    "kb.gap": ("kb.add", "kb.synonym"),          # (primary, fallback)
    "tool.contract_break": ("tool.validate", "tool.fallback"),
    "prompt.regression": ("prompt.edit", "revert"),
}
CAUSE_TO_AUDIENCE = {
    "kb.gap": ["agent_builder", "business_owner"],
    "tool.contract_break": ["platform_owner"],
    "tool.outage": ["platform_owner"],
    "prompt.regression": ["agent_builder"],
}
```
`predicted_delta.to` MUST come from the mined standard/peer baseline
for that cohort — never from the LLM, never asserted. The LLM (if used
at all in this stage) may only draft the human-readable risk statement
and ship-blocker condition, not the number.

### Verify (replay)
```
metric_for_replay = "median_turns" if cause_class == "prompt.regression"
                     else "resolution_rate"
POST /replay {team, tenant, change:{type, target, description},
              cohort:{intent, from_day, to_day}, golden_set:[...]}
```
Maintain a persisted counter file (`replay_budget.json`) and a cache
keyed by `(tenant, change, cohort)` so a re-run of the pipeline never
re-spends budget. **Call replay exactly once per diagnosed fix.** A
`verdict: no_effect` result is written to the report as-is — do not
retry with a different `change` in a loop; that is explicitly
disqualifying behavior per the PS ("the budget is the point").

### Decision gate
```
POST /api/findings/{id}/decision  {verdict, reason, decided_by}
  -> append to decisions.json (append-only, never mutate report.json
     in place)
GET /api/report merges decisions.json into prescriptions[].approval
A "finalize" step bakes decisions into the submitted loop-report.json
```

### Self-assessment
```
Aggregate ACROSS all verified fixes so far:
    prediction_error = predicted_delta.to - observed_delta
    hit = 1 if verdict == "improved" else 0
self_assessment = {
    cycles: count of completed prescribe->verify cycles,
    prescription_accuracy: {change_type: hit_rate},
    downweighted: [change_types with hit_rate < 0.5, if any],
    notes: "true measured accuracy, not inflated"
}
```
score.py rewards `cycles >= 3`. If you cannot honestly reach 3 cycles by
Day 5, report the true (smaller) number — a fabricated or rounded-up
cycle count is a Rule 2 violation risk and a credibility risk in the
demo Q&A.

---

## 7. PRIORITY 6 — Sealed-Run Hardening (Do This on Day 3, Not Day 6)

### Task
Write `run_sealed.sh`:
```bash
#!/usr/bin/env bash
set -e
python3 tools/nexus-loop-kit/pipeline.py \
    --kit "$SEALED_KIT" \
    --team "our-team" \
    --out loop-report.json \
    --validate
# Optional, best-effort, never blocks the scoring report:
python3 -m agent.orchestrator --report loop-report.json \
    --replay-url "$REPLAY_URL" || echo "enrichment skipped, backbone report already valid"
```
Requirements this script must satisfy:
- Zero interactive prompts.
- Zero hardcoded paths outside `$SEALED_KIT` and `$REPLAY_URL` env vars.
- If the LLM/enrichment stage fails or times out, the script still
  exits 0 with a valid, already-written `loop-report.json` from the
  backbone stage. The enrichment stage must never be able to corrupt or
  block emission of the backbone report — write the backbone report to
  disk BEFORE attempting any LLM call, not after.

### Test before Day 6
Run the renamed-tenant / shifted-day test from Priority 0's acceptance
criteria against this exact script, end to end, including the
`--validate` flag and a `score.py` run against a manually-adjusted
ground truth (or just confirm structural validity + finding count if
you don't have a second ground truth file). This is your actual dress
rehearsal for Day 6, and it should happen with days to spare, not hours.

---

## 8. Explicit Non-Goals (Do Not Build These)

To keep the team from losing days to scope creep, do NOT build:
- A provider-agnostic multi-LLM gateway. One provider, one retry, one
  documented fallback path is sufficient.
- The distributed/queue-based 100x architecture. Document it in the
  one-page note only. Zero lines of code.
- Schema-generated TypeScript types for the frontend. Hand-write the
  interfaces matching `loop-report.schema.json`; it's a few dozen lines.
- Any database. Files (`report.json`, `decisions.json`) are sufficient
  at this data scale and keep the sealed run trivially reproducible.
- Full restoration/use of the Beta-posterior trust resolver in the
  scoring-critical path (see Priority 4's reasoning).

---

## 9. Definition of Done, Per Tier

| Tier | Done when |
|---|---|
| Priority 0 | Renamed-tenant/shifted-day test passes; zero hardcoded literals in candidate discovery |
| Priority 1 | `silent_failures` nonzero on sample; plain tool_failure_rate confirmed flat over same window |
| Priority 2 | `standard[]` non-empty in report; golden_set_version frozen and stable across re-runs |
| Priority 3 | All 3 real findings (F1, F2, F3) emitted with impact/audience/if_nothing_changes; score.py > 45/55 |
| Priority 4 | No candidate double-classified as both decoy and real; `system_notes.escalated` empty on clean data |
| Priority 5 | At least 1 fix replayed with real `rp_` run_id; decision gate writes back; self_assessment.cycles reflects true count |
| Priority 6 | `run_sealed.sh` runs unattended on renamed/shifted test data and produces a valid, scoring report even with `$REPLAY_URL` unreachable |

Work top to bottom. Do not start Priority N+1 until Priority N's
acceptance test passes and is committed.
