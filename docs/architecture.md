# Nexus Loop — Product Architecture

A three-tier system that turns raw agent telemetry into an operator-ready
diagnostic report (`loop-report.json`): it finds real regressions, dismisses
look-alikes, verifies fixes, and refuses what cannot be measured.

```
┌────────────┐        ┌─────────────────────────┐        ┌───────────────────────────┐
│  Frontend  │  HTTP  │  Backend (flaggingLogic) │  HTTP  │  AI/ML layer (Nexus-Loop) │
│  (browser) │ ─────▶ │  DuckDB · deterministic  │ ─────▶ │  agentic decision loop    │
│            │ ◀───── │  metrics · detection ·   │ ◀───── │  reconcile→diagnose→      │
│            │  JSON  │  standards · coverage    │  JSON  │  prescribe→verify→gaps    │
└────────────┘        └─────────────────────────┘        └────────────┬──────────────┘
                                                                       │ HTTP
                                                                       ▼
                                                            ┌────────────────────┐
                                                            │  Replay endpoint    │
                                                            │  verify w/o corpus  │
                                                            └────────────────────┘
```

The data flow the product enforces: **frontend → backend → ai/ml → replay.**
The frontend never talks to the ai/ml layer directly; the ai/ml layer is the
only caller of replay.

---

## 1. Design goals

1. **Equal performance on the hidden (sealed) corpus.** On day 6 the organiser
   re-runs against a sealed corpus where *every fault moves* — different days,
   cohorts, tenants. The system must not depend on any practice-corpus literal.
2. **No production regression.** The original standalone pipelines keep working
   and keep their score; the service layer is additive.
3. **Rule compliance.** Golden Rule 1 (metrics are deterministic, never a model)
   and Golden Rule 3 (never trend quality across `judge_version`) hold end to end.

Machine score: the new three-tier `/report` path scores **55.0 / 55**; the
untouched legacy batch CLI scores **54.8 / 55**. The 0.2 difference is a single
reporting choice — the service path anchors a regression's window to its
attributed config-deploy day (causally correct, and generic), removing F1's
1-day detection lag. The three-tier path also adds real replay verifications,
generically-mined standards, dynamic coverage, real judge calibration, and a
cardinality-refusal gap.

---

## 2. Tiers and ownership

### Backend — `flaggingLogic/` (the measurement system of record)

Owns the data and every deterministic number. DuckDB reads the gzipped corpus
directly; metrics are SQL; detection is threshold math over 14-day rolling
baselines.

| Module | Role |
|---|---|
| `pipeline/ingest.py` | DuckDB views over `sessions/steps/turns/config_timeline` |
| `pipeline/metrics.py` | SQL metric family (session/tool/kb/volume/quality/…) |
| `pipeline/detect.py` | 6 detectors → cause-typed **candidates** (3 faults + 3 decoys) |
| `pipeline/standards.py` | **generic** top-decile standard miner (replaces hardcoded standards) |
| `service/engine.py` | ingest-once cache; computes coverage, calibration, cardinality |
| `service/report_fragment.py` | `metrics[]`, `standard[]`, `findings[]` — dynamic, literal-free |
| `service/app.py` | FastAPI: `/metrics /standards /candidates /findings /coverage /report` |

The backend’s `/report` is the frontend entry point: it builds its own
fragment, calls the ai/ml layer once, and assembles the full report.

### AI/ML layer — `Nexus-Loop/` (the agentic decision loop)

Consumes the backend’s candidates and reasons over them. **It never re-reads the
corpus** and never asks a model to compute a metric — its value is reconciliation,
diagnosis, prescription, verification, and honest refusal.

| Module | Role |
|---|---|
| `tools/nexus-loop-kit/orchestrator.py` | trust-aware evidence reconciliation (now wired in) |
| `service/reasoner.py` | reconcile · diagnose · prescribe · author gaps (all generic) |
| `service/verifier.py` | replay each prescription; compute self-assessment from real results |
| `service/app.py` | FastAPI: `POST /analyze` returns diagnoses/prescriptions/verifications/gaps/self-assessment |
| `tools/nexus-loop-kit/replay/serve.py` | verification endpoint (loads effect model from ground truth) |

### Frontend — `frontend/` (operator UI, served by the backend)

A dependency-free single-page app (vanilla HTML/CSS/JS) served by the backend at
`/app` — same origin as the API, so no CORS in practice. Built for a
non-technical operator: one neutral base + one accent, plain-language claim
first, technical detail (fidelity/coverage/derivation) muted and one expand
away. Four screens plus a chatbot, per `UI.txt`:

| Screen | Purpose | Data |
|---|---|---|
| Home | "is something wrong, does it need me" — status line + finding cards + honesty strip | `GET /report` |
| Finding detail | the decision screen: claim, facts, cause + config change, receipts, **Approve/Reject + reason** | `POST /approvals` |
| Dismissed | look-alikes examined and ruled out (read-only) | findings where `is_regression=false` |
| Refusals | the unanswerable questions, distinct (not alarming) treatment | `gaps[]` |
| Chatbot | bottom sheet; suggested chips; claim-first answers with jump links | `POST /chat` |

The **approval gate** persists a human `approval.verdict` + reason per
prescription (`store.py` → `output/approvals.json`), re-attached to the report
on every build — this is the human-decision element the scorer counts.

The **chatbot is Rule-1-safe by construction**: `chat.py` is a keyword intent
router over the finished `loop-report.json` — it *retrieves and phrases* the
already-computed metrics/findings/diagnoses/gaps and refuses anything outside
the 11 asks. No LLM, no log access, no fresh analysis.

New backend endpoints for the UI: `GET /report?refresh=false` (cached, no replay
spend), `POST /approvals`, `GET /approvals`, `POST /chat`, `GET /chat/suggestions`.
The report is cached after the first build so chat/approvals never re-trigger a
replay run.

---

## 3. The backend ↔ ai/ml contract

Backend `POST`s to ai/ml `/analyze`:

```jsonc
{
  "candidates": [ /* detect.py output: cause_class, cohort, window, metrics{before,during}, evidence, impact, config_attribution */ ],
  "standards":  [ /* mined top-decile cohort standards */ ],
  "context": {
    "tool_coverage": 0.7205,            // computed min non-legacy share
    "coverage_by_tenant": { "...": 0.72 },
    "cardinality":  [ { "field": "...customer_ref", "budget": 200, "distinct": N, "refuse": true } ],
    "catalog":      { /* capabilities + cardinality_budgets */ },
    "golden_set":   [ "s_...", ... ],   // known-good sessions for replay's guard
    "findings":     [ /* for verification cohort/window; avoids a corpus re-read */ ]
  },
  "team": "nexus-detection-squad"
}
```

ai/ml returns `{ reconciliation, diagnoses, prescriptions, verifications, self_assessment, gaps }`.
The evidence packet shape reuses `orchestrator.EvidencePacket`, so scope,
metric, grain and denominator are validated before a claim becomes a finding.

---

## 4. How robustness on the hidden corpus is guaranteed

Everything below is derived at runtime — there are **no** tenant/intent/tool/
agent/day/version literals in the logic path.

| Concern | Old (fragile) | Now (generic) |
|---|---|---|
| Standards | hardcoded cohorts + `day<34/40/46` | `standards.py` mines every cohort’s own top-decile |
| Coverage | fixed `0.725` | computed min non-legacy session share (`engine.tool_coverage`) |
| Calibration | fabricated `n=400, 0.925` | real agreement of model vs human labels within one `judge_version` |
| Diagnoses | hardcoded prose (`3.2.0→3.3.0`, `+52%`) | detector’s own data-derived evidence strings |
| Prescriptions | per-fault hardcoded targets/text | `cause_class → change_type`; target from the cohort; recovery target from the mined standard |
| Gaps | 2, partly static | `NOT_MEASURABLE` from catalog capabilities; `COVERAGE_TOO_LOW` from computed coverage; `CARDINALITY_REFUSED` from catalog budget vs measured distinct count |
| Verification | none (`verifications: []`) | real replay per prescription; self-assessment computed from results |
| Detection thresholds | fixed absolutes (`kb_miss>0.5`, `silent_fail>0.08`, `quality_drop>0.3`) | **adaptive**: `baseline + max(min_effect, z·SE)` — see below |

The detectors (`detect.py`, `metrics.py`) carry no tenant/intent/day literals;
the fragile report logic lived in the old `build_report.py`, which the service
path no longer uses. Point every layer at a different corpus via environment
variables (`NEXUS_DATA_DIR`, `NEXUS_CATALOG_PATH`, `NEXUS_LABELS_PATH`,
`--kit`/`--ground-truth` for replay) — no code changes for the sealed run.

### 4.1 Adaptive detection thresholds

The base-rate-dependent thresholds are no longer absolute constants. Each is
derived from the data's own baseline and sample size, so it tracks a corpus
where the normal rates differ:

- **F1 (KB gap)** — **peer-relative**: a cohort is flagged when its KB-miss rate
  exceeds its *sibling cohorts'* rate by `max(15 pts, 2.5·SE)`. This is what
  catches a **born-broken new product** (no self-history) and adapts when the
  corpus-wide miss rate is high or low. The old `0.5` is kept only as a no-peer
  floor.
- **F2 (silent tool failure)** — **self-baseline-relative**: flagged when
  silent-fail rises above the tool's own rolling baseline by
  `max(4 pts, 2.5·SE)`. Normal is ~0, so this stays sensitive without a fixed 8%.
- **D3 (judge change)** — the required cross-tenant drop is
  `max(0.2, 2.0·before-window σ)`; the structural signal (all tenants move at
  once) carries the decision, not a fixed magnitude.
- **Sample-size guard**: `SE = sqrt(p(1-p)/n)` widens the bar for small cohorts,
  so a spike on a handful of calls does not become a finding.

Detectors already scale-invariant (F3 turns are baseline-relative %, D1 shares
are normalised 0-1, D2 volume/latency are %) were left as-is. All parameters
live in `config.json`. `tests/test_adaptive_thresholds.py` proves the behaviour
on shifted base rates (e.g. a healthy cohort at 10% silent-fail is *not* flagged
though it exceeds the old 0.08; a partial KB gap at 0.35 *is* flagged though it
is below the old 0.5).

---

## 5. Rule compliance

- **Golden Rule 1 (no model computes a metric).** All metrics/detection are
  DuckDB SQL and arithmetic. FastAPI and the ai/ml layer are transport and
  reasoning only; neither computes a metric value.
- **Golden Rule 3 (judge-version safety).** Quality is segmented by
  `judge_version`; calibration compares model vs human *within one version*; the
  judge-boundary decoy is dismissed, not reported.
- **Coverage honesty.** Every tool/kb/cost metric states computed coverage and
  excludes `v2_flow` from the denominator.
- **Cardinality.** A breakdown over a near-unique budgeted field is refused with
  the budget cited.

---

## 6. Running it

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./run_product.sh                          # starts replay + ai/ml + backend, warms the cache
open http://127.0.0.1:8801/app/           # the operator UI
curl http://127.0.0.1:8801/report         # or the raw loop-report.json
```

Point at another corpus:

```bash
NEXUS_KIT=/path/to/sealed-kit NEXUS_DATA_DIR=/path/to/sealed/corpus \
NEXUS_GROUND_TRUTH=/path/to/sealed/ground_truth.json ./run_product.sh
```

Legacy standalone batch (unchanged, still 54.8/55 standalone):

```bash
cd flaggingLogic/pipeline && python run_pipeline.py
python score.py --report ../output/loop-report.json --ground-truth ground_truth.json
```

### Ports & operational notes

| Service | Port | Notes |
|---|---|---|
| backend | 8801 | warms once (~6–35s first request), then cached; overridable `NEXUS_BACKEND_PORT` |
| ai/ml | 8802 | stateless; `NEXUS_AIML_PORT` |
| replay | 8719 | **40-run budget per team** — each `/report` spends 3 runs verifying; verification degrades gracefully to empty when the budget is exhausted or the endpoint is down |

Performance: the backend ingests the ~880k-row corpus once into memory and
caches all derived outputs, so serving `/report` is cache lookups plus one
ai/ml round trip — it does not rescan per request.
