# Nexus Loop Problem-Solving Guide

## 1. Purpose

The corpus contains deliberate problems and deliberate lookalikes. The pipeline must do more than report metric movement:

```text
find the problem
  -> identify the traffic slice
  -> identify the cause
  -> link the cause to configuration evidence
  -> quantify impact
  -> propose a safe action
  -> verify the action without changing the corpus
```

The implementation is in:

```text
tools/nexus-loop-kit/pipeline.py
tools/nexus-loop-kit/critic.py
tools/nexus-loop-kit/replay/serve.py
```

The current generalized, replay-verified report is:

```text
my-generalized-final-loop.json
```

It reaches `55.0 / 55` machine points and passes the reliability critic.

## 2. Shared Analysis Method

### 2.1 Build an analysis contract

`CorpusInspector` reads:

```text
manifest.json
catalog.json
config_timeline.csv
```

It creates common rules for every detector:

```text
tool metrics exclude flows that emit no tool_call rows
quality comparisons stay within judge_version
new cohorts require a peer baseline when no history exists
high-cardinality dimensions are not valid breakdowns
```

This prevents different detectors from using different scopes or denominators.

### 2.2 Preprocess once

`Preprocessor` reads the compressed session and step streams and creates two reusable aggregate families.

Session grain:

```python
(
    tenant,
    intent,
    agent_kind,
    agent_id,
    day,
)
```

Session aggregates retain:

```text
sessions
resolved
handoffs
abandoned
session_ids
turns
cost values
quality values
```

Step grain:

```python
(
    tenant,
    intent,
    agent_kind,
    day,
)
```

Step aggregates retain:

```text
tool calls and errors
p95 tool latency
KB lookups and hits
per-tool silent successful calls
per-tool retries
```

The per-tool silent signal is:

```python
row["outcome"] == "ok" and row.get("result_field_count") == 0
```

### 2.3 Compare against the right baseline

The pipeline uses:

```text
historical baseline for established cohorts
peer baseline for new cohorts
cohort standards for directional performance
```

Resolution is higher-is-better. Turns and cost are lower-is-better.

### 2.4 Keep detection separate from diagnosis

A candidate means that a metric moved. A diagnosis explains why it moved.

```text
candidate -> evidence checks -> diagnosis -> finding -> prescription
```

This separation prevents a metric change from being automatically labelled as a regression.

## 3. The Three Real Problems

## 3.1 New product with no knowledge-base content

### Problem shape

A new product cohort appears without a valid historical before-period. Its retrievals fail and its resolution rate falls below comparable traffic.

### Detection

Generic candidate discovery groups observed cohorts by tenant, intent, agent kind, and agent ID. For a new cohort, it selects a peer with the same catalog-declared milestone signature.

```python
if len(before) >= 2:
    baseline_rows = [item for group in before[-2:] for item in group]
    baseline_kind = "historical"
else:
    baseline_rows = [item for group in peers for item in group]
    baseline_kind = "peer"
```

The KB promotion path requires:

```text
resolution_rate candidate
peer baseline
KB lookup rows in the candidate window
```

### Finding and cause

The finding names:

```text
tenant
intent slice
agent kind
observed resolution
peer expected resolution
KB hit rate
KB score evidence
nearby KB timeline change
```

The diagnosis is:

```json
{
  "cause_class": "kb.gap",
  "attributed_change": {
    "kind": "kb",
    "day": 34
  }
}
```

### Impact

The report computes:

```text
conversations affected
share of tenant traffic
handoffs
abandoned sessions
cost
number of days running
```

The traffic share uses the full tenant window as denominator, not the cohort itself.

### Proposed change and replay

The prescription is generated from the diagnosis class:

```json
{
  "change_type": "kb.add",
  "target": "detected intent",
  "predicted_delta": {
    "metric": "resolution_rate",
    "from": 0.2432,
    "to": 0.751
  }
}
```

Replay checks whether the proposed KB addition improves the affected cohort and avoids golden-set regressions.

## 3.2 API returns empty results while reporting success

### Problem shape

The tool reports a successful outcome, but its payload contains no result fields. The normal tool-error metric therefore stays flat.

### Detection

The preprocessor counts per-tool calls, errors, silent successful calls, and retries:

```python
item["silent_tool_calls_by_name"][tool_name] += (
    row["outcome"] == "ok"
    and row.get("result_field_count") == 0
)
item["retried_tool_calls_by_name"][tool_name] += (
    row.get("retry_count", 0) > 0
)
```

The detector discovers tool changes from the configuration timeline. For each tool change it compares a pre-change window and a post-change window across observed tenants, intents, and agent kinds.

It promotes a candidate when:

```text
post-change silent-success rate rises materially
there are enough calls to support the comparison
same-tool retries appear
resolution or downstream behavior worsens
```

The sample-size requirement prevents a handful of calls from becoming a regression finding.

### Finding and cause

The evidence separates:

```text
ordinary error: outcome = error or timeout
silent contract failure: outcome = ok and result_field_count = 0
retry evidence: retry_count > 0 for the same tool
```

The diagnosis is:

```json
{
  "cause_class": "tool.contract_break",
  "attributed_change": {
    "kind": "tool",
    "day": 40
  }
}
```

### Proposed change and replay

The prescription is generated from the detected tool name:

```json
{
  "change_type": "tool.validate",
  "target": "detected tool",
  "predicted_delta": {
    "metric": "resolution_rate",
    "from": 0.7738,
    "to": 0.8586
  }
}
```

The proposed validation rejects empty successful payloads and uses a fallback path. Replay verifies that resolution improves and that known-good sessions remain safe.

## 3.3 Prompt makes conversations longer without changing outcomes

### Problem shape

Resolution remains broadly stable, but median turns and cost rise after a prompt deployment. An outcome-only alert will miss this fault.

### Detection

The detector discovers prompt changes from the configuration timeline and joins each change to the affected agent ID. It compares pre-change and post-change session windows.

```python
before = [
    row for row in self.sessions.values()
    if row["tenant"] == tenant
    and row["agent_id"] == agent_id
    and day - 10 <= row["day"] < day
]
during = [
    row for row in self.sessions.values()
    if row["tenant"] == tenant
    and row["agent_id"] == agent_id
    and day <= row["day"] < day + 10
]
```

It measures:

```text
median turns
cost per session
resolution rate
```

The turn threshold is sample-size-aware rather than a fixed practice percentage:

```python
turn_threshold = max(
    0.10,
    1.96 * (
        1 / max(1, before_session_count)
        + 1 / max(1, during_session_count)
    ) ** 0.5,
)
```

### Finding and cause

The finding is promoted when turns rise materially and cost supports the same direction while resolution remains broadly flat.

The diagnosis is:

```json
{
  "cause_class": "prompt.regression",
  "attributed_change": {
    "kind": "prompt",
    "day": 46
  }
}
```

### Proposed change and replay

```json
{
  "change_type": "prompt.edit",
  "target": "detected agent",
  "predicted_delta": {
    "metric": "median_turns",
    "from": 6.0,
    "to": 4.0
  }
}
```

Replay verifies the effort metric and checks the golden set so removing confirmation wording does not damage healthy conversations.

## 4. The Three Lookalikes

Lookalikes are investigated and written into the report as `is_regression: false`.

## 4.1 Marketing traffic-mix shift

### What it looks like

Aggregate resolution changes because one intent becomes a much larger share of traffic.

### How we detect it

The decoy detector scans observed tenants and adjacent windows. It compares:

```text
intent share before versus during
aggregate resolution before versus during
per-intent resolution stability
```

A large intent-share change with stable cohort rates is classified as:

```text
traffic_mix
```

The report explicitly states that the aggregate movement is composition, not a quality regression.

## 4.2 Flash-sale load event

### What it looks like

Traffic volume and tool latency spike for a short period, while quality recovers afterward.

### How we detect it

The detector scans observed tenants and short windows and compares:

```text
sessions per day
median tool p95 latency
resolution and recovery
```

A large volume increase combined with a latency increase is classified as:

```text
load
```

It is not promoted to an agent-quality regression unless cohort quality remains degraded after the load event.

## 4.3 Judge-rubric boundary

### What it looks like

Quality drops across tenants at the same time because the evaluation rubric becomes stricter.

### How we detect it

The detector reads judge changes from the timeline and compares quality before and after the boundary. A synchronized movement across tenants is classified as:

```text
judge_change
```

The contract also requires judged quality to be compared within one `judge_version`.

## 5. The Unanswerable Failover Question

### Question

```text
What is our failover rate?
```

### Why it cannot be measured

The runtime does not emit an event proving:

```text
primary target failed
alternate target was selected
reason for switching
whether recovery succeeded
```

A retry is not failover. It may call the same target again.

### Correct response

The gap specialist returns:

```json
{
  "ask_id": "A11",
  "verdict": "NOT_MEASURABLE",
  "nearest_proxy": "llm_call rows with retry_count > 0",
  "why_the_proxy_misleads": "A retry may call the same target again and does not prove failover.",
  "required_event": {
    "name": "failover",
    "grain": "step",
    "fields": [
      "from_target",
      "to_target",
      "reason",
      "recovered"
    ],
    "owner": "conversation-runtime"
  }
}
```

The pipeline refuses to invent a failover rate.

## 6. Denominator Trap: Legacy Traffic Has No Tool Rows

### Risk

Legacy traffic emits no `tool_call` rows. Counting tool rows alone would make tool coverage appear better than it is.

### Current handling

The tool metric declares measured fidelity and derives coverage from observed session counts:

```python
tenant_rows = [
    row for row in session_aggregates.values()
    if row["tenant"] == tenant
]
total = sum(row["sessions"] for row in tenant_rows)
observed = sum(
    row["sessions"]
    for row in tenant_rows
    if row["agent_kind"] != "v2_flow"
)
coverage = observed / total
```

The report uses the minimum observed non-legacy share across tenants and states the exclusion explicitly:

```json
{
  "fidelity": "measured",
  "coverage": {
    "value": 0.7205,
    "basis": "derived from observed non-v2 session share",
    "excluded": ["agent_kind = v2_flow"]
  }
}
```

This prevents a tool metric from silently claiming coverage over traffic that emits no tool events.

## 7. Denominator Trap: Near-Unique Customer Field

### Risk

A near-unique customer field creates a breakdown with almost one group per customer. That is not a useful operational cohort and violates the catalog cardinality budget.

### Correct handling

The pipeline must refuse the breakdown rather than produce a misleading chart:

```text
verdict: CARDINALITY_REFUSED
field: custom_dims.customer_ref
reason: declared cardinality budget exceeded
```

The refusal should cite:

```text
requested field
observed or declared cardinality
allowed cardinality budget
recommended lower-cardinality alternatives
```

Recommended alternatives include:

```text
intent
agent kind
channel
coarse customer segment, if declared in the catalog
```

### Current implementation status

The analysis contract records the high-cardinality rule, but the current Level 1 report does not yet emit a separate `CARDINALITY_REFUSED` gap for this ask. This is the remaining denominator-trap hardening item and should be added before claiming complete support for arbitrary operator breakdown requests.

## 8. Reliability and Replay

The replay endpoint verifies proposed changes without changing the corpus.

It accepts:

```text
team
tenant
change type and target
cohort window
golden-set session IDs
```

It returns:

```text
run ID
metric before and after
delta
verdict
golden-set replay count
regressed count
pass/fail
```

Replay does not modify:

```text
sessions.jsonl.gz
agent_steps.jsonl.gz
turns.jsonl.gz
ground_truth.json
```

The current replay-backed report contains:

```text
3 prescriptions
3 improved outcomes
3 golden-set passes
1 self-assessment cycle
```

## 9. Reliability Critic

Before accepting a report, run:

```powershell
py .\tools\nexus-loop-kit\critic.py `
  --pipeline .\tools\nexus-loop-kit\pipeline.py `
  --report .\my-generalized-final-loop.json `
  --strict
```

The critic checks that implementation assumptions are not quietly tied to the practice corpus and that the report has:

```text
standards
matching prescriptions and verifications
golden-set passes
self-assessment results
```

The generalized current implementation passes:

```text
critical: 0
high:     0
medium:   0
low:      0
status:   pass
```

## 10. Final Conclusion

The pipeline solves the planted problems through evidence-specific detectors rather than one generic outcome alert:

```text
KB gap              -> peer resolution + KB retrieval evidence
silent API failure  -> successful empty payload + retry evidence
prompt regression   -> turns/cost change with flat resolution
traffic shift       -> intent-share change with stable cohorts
load event          -> volume/latency spike with recovery
judge change        -> synchronized quality movement at rubric boundary
failover question   -> honest NOT_MEASURABLE refusal
tool denominator    -> explicit non-legacy coverage
customer breakdown  -> cardinality refusal required
```

The current report demonstrates complete handling of the three regressions,
three lookalikes, failover refusal, and tool-coverage trap. The near-unique
customer field remains the one explicit gap: the contract knows it is invalid,
but a dedicated `CARDINALITY_REFUSED` report entry should be added for a fully
complete end product.
