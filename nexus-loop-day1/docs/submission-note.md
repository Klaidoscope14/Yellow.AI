# Nexus Loop Submission Note

## What Is Real

- The pipeline reads the practice or sealed kit, including sessions, execution steps, turns, feedback, configuration timeline, catalog, labels, and manifest metadata.
- Metrics, coverage, standards, detection candidates, impact, findings, and refusal evidence are computed from the corpus.
- The three planted regressions and three lookalikes are detected on the practice corpus and on a freshly generated sealed-style corpus.
- The report is validated against `tools/nexus-loop-kit/schema/loop-report.schema.json` before it is written.
- Replay verification uses the provided replay endpoint and records before/after values, verdicts, prediction error, and golden-set protection.
- The local screen reads the report through the backend and the approval endpoint persists operator decisions in `.approvals.json`.

## What Is Stubbed or Limited

- The replay server is a deterministic simulator based on the kit ground truth; it does not execute a production agent or mutate a production runtime.
- The current local frontend uses `service/service_backend.py`, which serves the generated report. The FastAPI split in `service/backend.py` and `service/app.py` is also runnable as the three-tier architecture; the legacy service remains the simplest frontend-compatible path.
- Human approval is available through the screen, but a newly generated report starts without a human verdict. A `deferred` or automated placeholder is not treated as a human decision.
- Self-assessment currently represents the replay cycles available in the run; one cycle is not enough to establish durable priors.

## What Is Simulated

- Replay before/after effects and golden-set outcomes are simulated deterministically by `replay/serve.py`.
- The practice corpus and its ground truth are generated fixtures. The sealed corpus changes fault days, tenants, and traffic slices and must be run without access to its answer key during analysis.

## What Breaks at 100x Scale

- The current standard-library preprocessor keeps large aggregate structures in memory and would need streaming or columnar storage.
- A single-process HTTP server is not sufficient for concurrent production traffic, durable multi-user state, authentication, or audit retention.
- Approval storage in `.approvals.json` is local file state, not a transactional database.
- Replay budget, request queues, retries, and observability would need a shared service rather than process-local state.
- The report should be written to versioned object storage and served through a job/status API instead of blocking a request on a full corpus scan.

## Current Evidence

The practice report scores `55/55` on the machine scorer, validates against the supplied JSON schema, and covers all three real faults, all three lookalikes, and the A11 refusal. A sealed-style corpus also reaches the same diagnostic score when scored with its correct sealed ground-truth path.
