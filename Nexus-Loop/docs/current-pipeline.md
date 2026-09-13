# Current Nexus Loop Pipeline

## Purpose

This document explains the implemented Level 1 pipeline, the responsibility of each component, the data flow, representative code, the current output, and the next work needed for later levels.

The pipeline is intentionally separate from the challenge generator and scorer. It analyzes the generated practice kit and produces a Level 1 report.

## End-to-End Flow

```text
manifest.json + catalog.json + config_timeline.csv
                         |
                         v
                 CorpusInspector
                         |
                         v
                  analysis contract
                         |
                         v
                   Preprocessor
                         |
                         v
              reusable in-memory aggregates
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
   Regression Agent  Decoy Agent    Gap Agent
          |              |              |
          +--------------+--------------+
                         |
                         v
                   ReportBuilder
                         |
                         v
                  report validation
                         |
                         v
                       score.py
```

The current implementation is in:


The existing generator, starter, scorer, schema, and corpus remain unchanged.

## Component 1: CorpusInspector

Class: `CorpusInspector`

### Responsibility

The inspector creates the rules that every later analysis must follow. It does not perform the expensive full-corpus scan.

### Reads


### Produces

A contract containing:


Important rules currently declared:

```text
Tool metrics exclude v2_flow because v2_flow emits no tool_call rows.
Quality comparisons stay within one judge_version.
premium_card_info has no valid before-period.
customer_ref is not a valid breakdown because of high cardinality.
```

Representative code:

```python
return {
    "corpus": manifest["corpus_variant"],
    "days": manifest["days"],
    "sources": manifest["files"],
    "rules": [
        "tool metrics exclude v2_flow because it emits no tool_call rows",
        "quality comparisons stay within one judge_version",
        "premium_card_info has no valid before-period",
        "customer_ref is not a valid breakdown because of cardinality",
    ],
    "timeline": timeline,
    "capabilities": catalog.get("capabilities", []),
}
```

### Why it exists

Without a shared contract, different agents may use different denominators. For example, one agent could calculate premium-card resolution using v3 traffic only while another silently includes legacy v2 traffic. Those numbers must not be treated as comparable.

## Component 2: Preprocessor

Class: `Preprocessor`

### Responsibility

The preprocessor scans the compressed corpus once and creates reusable aggregates. Specialists consume these aggregates instead of repeatedly decompressing raw files.

### Reads


### Session aggregate

The grouping key is:

```python
(
  tenant,
  intent,
  agent_kind,
  agent_id,
  day,
)
```

Each group stores:

```text
session count
resolved count
handoff count
abandoned count
turn values
quality values
cost total
```

Representative code:

```python
key = (
    row["tenant"],
    row["intent"],
    row["agent_kind"],
    row["day"],
)

session_agg["|".join(map(str, key))] = {
    "tenant": tenant,
    "intent": intent,
    "agent_kind": agent_kind,
    "day": day,
    "sessions": len(rows),
    "resolved": sum(r["session_end"] == "resolved" for r in rows),
    "handoffs": sum(r["session_end"] == "handoff" for r in rows),
    "abandoned": sum(r["session_end"] == "abandoned" for r in rows),
    "turns": [r["turns"] for r in rows],
    "quality": [r["quality_score"] for r in rows],
    "cost_usd": sum(r.get("cost_usd") or 0 for r in rows),
}
```

### Step aggregate

For each tenant, intent, agent kind, and day, the preprocessor calculates:

```text
tool calls
tool errors
tool failure rate
tool p95 latency
KB lookups
KB hits
KB hit rate
KB score minimum and maximum
```

Representative code:

```python
if row["step_type"] == "tool_call":
    item["tool_calls"] += 1
    item["tool_errors"] += row["outcome"] != "ok"
    item["durations"].append(row.get("duration_ms") or 0)
elif row["step_type"] == "kb_lookup":
    item["kb_lookups"] += 1
    item["kb_hits"] += bool(row.get("kb_hit"))
    item["kb_scores"].append(row["kb_top_score"])
```

The aggregate keeps its dimensions when finalized. This is important because specialists must be able to filter by tenant, intent, agent kind, and day.

## Component 3: Regression Agent

Method: `Level1Specialists.regression()`

### Responsibility

Find the real Level 1 regression: the Acme Bank premium-card knowledge-base gap.

### Scope

```text
tenant: acme-bank
intent: premium_card_info
agent kind: v3_agent
window: days 35-45
metric: resolution_rate
```

### Comparison logic

The premium-card intent is new, so it has no valid before-period. The agent compares it with `product_info` traffic in the same tenant and time window.

```python
affected = self._window_sessions(
    "acme-bank", "premium_card_info", "v3_agent", 35, 45
)
peer = self._window_sessions(
    "acme-bank", "product_info", "v3_agent", 35, 45
)

observed = self._resolution(affected)
expected = self._resolution(peer)
```

It also checks KB aggregates:

```python
kb_rows = [
    row for row in self.steps.values()
    if row["tenant"] == "acme-bank"
    and row["intent"] == "premium_card_info"
    and row["agent_kind"] == "v3_agent"
    and 34 <= row["day"] < 45
    and row["kb_lookups"]
]
```

### Output

The agent emits:

```text
finding f1
 diagnosis d1
```

The diagnosis is:

```json
{
  "finding_id": "f1",
  "cause_class": "kb.gap",
  "confidence": 0.91,
  "attributed_change": {
    "kind": "kb",
    "day": 34
  }
}
```

The finding contains the observed value, expected value, evidence, impact, audience, and cost of inaction.

### F2: Silent tool contract failure

The ordinary tool failure metric counts only rows whose outcome is `error` or
`timeout`. That misses the injected fault because the tool returns `outcome =
"ok"` with an empty payload. The preprocessor therefore keeps per-tool
counters:

```python
tool_name = row.get("tool_name") or "unknown"
item["tool_calls_by_name"].setdefault(tool_name, 0)
item["silent_tool_calls_by_name"].setdefault(tool_name, 0)
item["retried_tool_calls_by_name"].setdefault(tool_name, 0)

item["tool_calls_by_name"][tool_name] += 1
item["silent_tool_calls_by_name"][tool_name] += (
  row["outcome"] == "ok"
  and row.get("result_field_count") == 0
)
item["retried_tool_calls_by_name"][tool_name] += (
  row.get("retry_count", 0) > 0
)
```

The regression specialist compares `get_order_status` before and after the
day-40 deployment. It promotes F2 when silent successful calls exceed 5%, then
checks same-tool retries and the order-status resolution baseline:

```python
before_tools = [row for row in tool_rows if 28 <= row["day"] < 40]
during_tools = [row for row in tool_rows if 40 <= row["day"] < 52]
during_calls = sum(
  row["tool_calls_by_name"].get("get_order_status", 0)
  for row in during_tools
)
during_silent = sum(
  row["silent_tool_calls_by_name"].get("get_order_status", 0)
  for row in during_tools
)

if during_calls and during_silent / during_calls > 0.05:
  # emit f2 with cause class tool.contract_break
  ...
```

The finding evidence separates:

```text
declared tool error rate: outcome error/timeout
silent failure rate:      outcome ok and result_field_count = 0
retry evidence:           retry_count > 0 on the same tool
```

This distinction is the reason F2 can be detected even though the obvious
tool-error metric remains flat.

### F3: Prompt regression

F3 is not an outcome-rate regression. Resolution stays broadly flat, while
turns and cost increase for `acme_main_v3`. The detector compares ten days
before and after the day-46 prompt change:

```python
rows = [
  row for row in self.sessions.values()
  if row["tenant"] == "acme-bank"
  and row["agent_id"] == "acme_main_v3"
]
before = [row for row in rows if 36 <= row["day"] < 46]
during = [row for row in rows if 46 <= row["day"] < 56]

before_turns = self._median(before, "turns")
during_turns = self._median(during, "turns")
before_cost = self._cost(before)
during_cost = self._cost(during)
```

The promotion rule is:

```python
if before_turns and during_turns \
    and during_turns > before_turns * 1.2:
  # emit f3 with cause class prompt.regression
  ...
```

The finding reports turns, cost, resolution, agent isolation, and the nearby
prompt change. This catches efficiency regressions that resolution-only
alerting would miss.

### Shared impact calculation

Every real regression receives an impact block. The denominator is the full
tenant window, not merely the affected cohort:

```python
def _impact(self, rows, expected_resolution, tenant_total, description):
  affected = sum(row["sessions"] for row in rows)
  return {
    "conversations_affected": affected,
    "share_of_traffic": round(affected / max(1, tenant_total), 4),
    "downstream": {
      "would_have_resolved_at_baseline": round(
        affected * expected_resolution
        - sum(row["resolved"] for row in rows)
      ),
      "unplanned_handoffs": sum(row["handoffs"] for row in rows),
      "abandoned": sum(row["abandoned"] for row in rows),
    },
    "cost_usd": round(sum(row["cost_usd"] for row in rows), 2),
    "days_running": max(1, len({row["day"] for row in rows})),
    "derivation": description,
  }
```

The `impact`, `audience`, and `if_nothing_changes` fields are required before a
finding marked `is_regression: true` is allowed into the final report.

## Component 4: Decoy Agent

Method: `Level1Specialists.decoys()`

### Responsibility

Investigate patterns that look like regressions but should not be reported as agent-quality regressions.

### D1: Traffic mix

The agent compares aggregate performance with the distribution of intents.

```text
branch_locator share increases sharply
aggregate resolution moves
per-intent rates stay stable
```

Conclusion:

```text
traffic_mix
is_regression: false
```

Output:

```text
finding f3_decoy
 diagnosis d3
```

### D2: Load event

The agent compares traffic volume, tool latency, resolution, and recovery.

```text
sessions per day increase
p95 tool latency increases
quality and resolution stay broadly stable
values recover after the event
```

Conclusion:

```text
load
is_regression: false
```

Output:

```text
finding f5
 diagnosis d5
```

### D3: Judge-version boundary

The agent compares quality scores with the judge version and configuration timeline.

```text
quality changes across both tenants
judge version changes from v1 to v2
```

Conclusion:

```text
judge_change
is_regression: false
```

Output:

```text
finding f4
 diagnosis d4
```

Explicitly recording these as non-regressions is necessary for specificity scoring.

## Component 5: Gap Agent

Method: `Level1Specialists.gaps()`

### Responsibility

Refuse questions that the available telemetry cannot answer honestly.

For A11, the corpus does not emit a failover event with:

```text
from_target
to_target
reason
recovered
```

The agent therefore returns:

```json
{
  "ask_id": "A11",
  "verdict": "NOT_MEASURABLE",
  "nearest_proxy": "llm_call rows with retry_count > 0",
  "why_the_proxy_misleads": "A retry does not prove that an alternate target served the user."
}
```

This prevents the pipeline from mislabeling retries as failovers.

## Component 6: Orchestrator and Trust

File: `tools/nexus-loop-kit/orchestrator.py`

The current Level 1 pipeline invokes specialists directly in parallel. The separate orchestrator module provides the reusable trust-aware conflict mechanism.

### Trust model

Trust is keyed by:

```text
(agent_name, query_id)
```

It uses a Beta-style posterior:

```python
score = (prior_success + successes) / (
    prior_success
    + prior_failure
    + successes
    + failures
)
```

Feedback can come from a reviewer, validator, replay result, or accepted report outcome.

### Conflict policy

The resolver validates claims before ranking them:

```python
if packet.scope_key != query.scope_key:
    errors.append("scope differs from the requested scope")
```

A scope, metric, grain, or query mismatch is a hard conflict:

```python
if hard_conflict:
    return Resolution(
        "escalate",
        None,
        [],
        conflicts,
        "A competing claim violates the query contract; reconcile scope "
        "and denominator before ranking trust.",
    )
```

Only compatible claims are ranked using:

```python
score = trust * packet.confidence * evidence_quality
```

The rule is:

> Trust can rank comparable evidence. Trust cannot make incompatible evidence comparable.

## Component 7: Parallel Execution

The three Level 1 specialists run concurrently:

```python
with ThreadPoolExecutor(max_workers=3) as pool:
    futures = [
        pool.submit(specialists.regression),
        pool.submit(specialists.decoys),
        pool.submit(specialists.gaps),
    ]
    results = [future.result() for future in as_completed(futures)]
```

They return `SpecialistResult` objects. They do not edit the report, preventing write conflicts.

## Component 8: ReportBuilder

Class: `ReportBuilder`

The builder is the only component that writes the final report.

It combines:

```text
starter-compatible metrics
f1 real regression
f3 traffic-mix decoy
f5 load decoy
f4 judge-version decoy
d1, d3, d5, d4 diagnoses
A11 gap
```

For Level 1, these sections remain empty:

```json
{
  "standard": [
    "216 direction-aware cohort standards mined from observed session values"
  ],
  "prescriptions": [],
  "verifications": [],
  "self_assessment": {
    "cycles": 0,
    "prescription_accuracy": {}
  }
}
```

## Component 9: Validator

Function: `validate_report()`

The validator checks:


This catches report assembly errors before the scorer runs.

## Current Run Command

From the repository root:

```powershell
py .\tools\nexus-loop-kit\pipeline.py `
  --kit .\kit `
  --team pipeline-demo `
  --out .\my-level1-pipeline-report.json `
  --score
```

To execute the generated prescriptions against the local practice replay
endpoint, add `--replay-url`:

```powershell
py .\tools\nexus-loop-kit\pipeline.py `
  --kit .\kit `
  --team analyst-loop `
  --out .\my-executed-loop-report.json `
  --replay-url http://127.0.0.1:8719 `
  --score
```

This mode sends one request per typed prescription. It stores the replay run
ID, before and after values, verdict, golden-set result, and prediction error
under `verifications`. It also creates one `self_assessment` cycle grouped by
change type. By default it sends 20 known-good session IDs as the replay
regression guard; override that with `--golden-set-size`. The local replay
endpoint must be started separately from the directory containing `kit`:

```powershell
py .\tools\nexus-loop-kit\replay\serve.py --kit .\kit --port 8719
```

Current verified result:

```text
findings=6
diagnoses=6
gaps=1
SUBTOTAL 53.7 / 55
```

Expected executed-loop output:

```text
wrote .\my-executed-loop-report.json
findings=6 diagnoses=6 gaps=1
verification: 3 replayed, 3 improved
SUBTOTAL 54.2 / 55
```

The corrected run records `golden_set_pass: true` for all three replayed
prescriptions. Run the commands from the nested project directory that
contains both `kit` and `tools`; otherwise relative paths such as `--kit .\kit`
resolve against the workspace parent.

The six findings are:

```text
f1: premium-card KB regression
f2: silent tool contract regression
f3: prompt regression
f3_decoy: traffic-mix decoy dismissed
f5: load decoy dismissed
f4: judge-version decoy dismissed
```

## What Is Complete

The current pipeline completes the Level 1 workflow:

```text
metadata inspection
raw corpus preprocessing
parallel specialist analysis
report assembly
basic report validation
practice scoring
```

It does not alter:


## Current Limitations

1. `pipeline.py` computes the Level 1 finding windows directly instead of discovering all candidate windows dynamically.
2. The report builder has a compact starter-compatible metric set rather than reproducing every metric in the supplied Level 1 reference.
3. The pipeline does not yet use `Orchestrator.run()` to reconcile specialist evidence packets; the trust-aware resolver is implemented separately and demonstrated in `orchestrator.py`.
4. The preprocessor keeps lists such as turns and quality scores in memory, which is acceptable for this corpus but should be replaced with streaming distribution summaries at larger scale.
5. The validator performs structural checks but does not yet validate against the full JSON schema.

## Next Work: Level 2

Level 2 should add standards and prescriptions.

### Step 1: Mine a standard

For each relevant cohort, calculate a healthy top-decile or peer benchmark. Preserve the cohort, metric, sample size, and derivation.

### Step 2: Add a prescription

For the KB diagnosis, propose a typed action:

```json
{
  "diagnosis_id": "d1",
  "change_type": "kb.add",
  "target": "premium_card_info knowledge content",
  "predicted_delta": {
    "metric": "resolution_rate",
    "from": 0.31,
    "to": 0.80
  }
}
```

### Step 3: Add a decision gate

Record what a human is approving, the risk if the diagnosis is wrong, and the condition that prevents shipping.

### Step 4: Use replay verification

Start the replay server and submit the proposed change. Store the returned `run_id`, before value, after value, verdict, and golden-set result.

### Step 5: Update self-assessment

After several cycles, record prediction error by change type and downweight actions that repeatedly fail.

## Operating Principle

The pipeline should follow this order:

```text
inspect contract
    -> preprocess once
    -> analyze in parallel
    -> validate scope and provenance
    -> resolve compatible claims
    -> build one report
    -> validate
    -> score
    -> propose and verify fixes later
```

The critical safety boundary is that learned trust is a ranking signal, not permission to override incompatible scope, denominator, metric, or grain.
