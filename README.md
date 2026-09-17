# Nexus Loop

Nexus Loop is a diagnostic pipeline for discovering regressions in agent sessions, explaining their causes, proposing fixes, and verifying those fixes through replay. The current implementation includes a Python agentic pipeline, a replay endpoint, a report service with approval persistence, and a React/Vite dashboard. A FastAPI backend/AI-ML split is also present as the next architecture boundary.

## Architecture

```text
kit/ corpus and metadata
        |
        v
pipeline.py  inspect -> preprocess -> detect -> diagnose -> prescribe -> replay -> validate
        |
        v
loop-report.json  canonical generated report
        |
        v
service/service_backend.py  loads/adapts the report at /report
        |
        v
frontend React/Vite dashboard  http://127.0.0.1:4173/app/
```

The layers have separate responsibilities:

- **Agentic pipeline**: reads the corpus, mines cohort standards, detects F1/F2/F3 and decoys, creates diagnoses and prescriptions, optionally runs replay, and writes a report.
- **Replay service**: evaluates proposed changes against the corpus ground-truth effect model without modifying the corpus.
- **Service backend**: exposes the generated report through a small HTTP API. It uses `loop-report.json` as the canonical frontend payload and persists approvals in `.approvals.json`.
- **Frontend**: consumes the report contract and renders incidents, dismissed patterns, diagnostic gaps, decisions, evidence, and replay verification.

The FastAPI split is represented by `service/backend.py` for deterministic backend transport and `service/app.py` for the AI/ML `/analyze` layer. The support modules in `service/engine.py`, `service/report_fragment.py`, `service/store.py`, and `service/chat.py` provide the deterministic adapter, approval store, and report-grounded chat surface.

## Requirements

- Windows PowerShell
- Python 3.11+ (`py` command available)
- Node.js and npm
- The practice kit at `nexus-loop-day1/kit`

Install the Python service dependencies from the workspace root:

```powershell
cd C:\Users\Samsung\Desktop\nexus-loop-day1
py -m pip install -r .\requirements.txt
```

The pipeline and replay kit use Python's standard library. Frontend dependencies are installed under `frontend/node_modules`.

## Project Paths

The implementation root is:

```text
C:\Users\Samsung\Desktop\nexus-loop-day1\nexus-loop-day1
```

Important files:

| Path | Purpose |
| --- | --- |
| `nexus-loop-day1/tools/nexus-loop-kit/pipeline.py` | Agentic report-generation pipeline |
| `nexus-loop-day1/tools/nexus-loop-kit/score.py` | Machine scoring harness |
| `nexus-loop-day1/tools/nexus-loop-kit/replay/serve.py` | Replay verification server |
| `nexus-loop-day1/service/service_backend.py` | HTTP service for the frontend |
| `nexus-loop-day1/loop-report.json` | Canonical generated report |
| `nexus-loop-day1/frontend/src/` | React dashboard |
| `nexus-loop-day1/frontend/vite.config.ts` | Vite base path and API proxy |
| `nexus-loop-day1/service/service_backend.py` | Verified local report and approval service |
| `nexus-loop-day1/service/backend.py` | FastAPI backend boundary |
| `nexus-loop-day1/service/app.py` | FastAPI AI/ML `/analyze` service |
| `requirements.txt` | FastAPI, HTTPX, and Uvicorn dependencies |
| `nexus-loop-day1/docs/current-pipeline.md` | Detailed pipeline documentation |
| `nexus-loop-day1/docs/V1.1-architecture.md` | Architecture documentation |

## Run the Pipeline

Open PowerShell in the nested implementation root:

```powershell
cd C:\Users\Samsung\Desktop\nexus-loop-day1\nexus-loop-day1
```

Run the pipeline and score a report:

```powershell
py .\tools\nexus-loop-kit\pipeline.py `
  --kit .\kit `
  --team generalized-final-loop `
        --out .\loop-report.json `
        --replay-url http://127.0.0.1:8719 `
  --score
```

The verified report contains six findings, six diagnoses, three prescriptions, and one diagnostic gap. The latest verified machine score is `55.0 / 55`.

## Run Replay Verification

Start replay in a separate PowerShell terminal from the same nested implementation root:

```powershell
cd C:\Users\Samsung\Desktop\nexus-loop-day1\nexus-loop-day1
py .\tools\nexus-loop-kit\replay\serve.py --kit .\kit --port 8719
```

Replay endpoints:

```text
GET  http://127.0.0.1:8719/health
GET  http://127.0.0.1:8719/log
POST http://127.0.0.1:8719/replay
```

The pipeline sends typed prescriptions to `POST /replay`. Replay returns a verdict such as `improved`, `no_effect`, or `regressed`, before/after metrics, a run ID, and a golden-set result. Replay uses a 40-run budget per team and does not mutate `sessions.jsonl.gz`, `agent_steps.jsonl.gz`, `turns.jsonl.gz`, or `ground_truth.json`.

## Run the Service Backend

In another PowerShell terminal:

```powershell
cd C:\Users\Samsung\Desktop\nexus-loop-day1\nexus-loop-day1
py .\service\service_backend.py
```

The service listens on:

```text
http://127.0.0.1:8081
```

Endpoints used by the React dashboard:

```text
GET  /health
GET  /report
POST /run
POST /approvals
```

`GET /report` serves the complete report contract from `loop-report.json`. The adapter preserves the pipeline fields used by the UI, including `metrics`, `standard`, `findings`, `diagnoses`, `prescriptions`, `verifications`, `gaps`, and `self_assessment`. `POST /approvals` validates and persists human decisions in `.approvals.json` and updates the cached report.

To inspect the report from PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8081/report | ConvertTo-Json -Depth 20
```

## Run the React Frontend

In a separate PowerShell terminal:

```powershell
cd C:\Users\Samsung\Desktop\nexus-loop-day1\frontend
.\node_modules\.bin\vite.cmd --host 127.0.0.1 --port 4173
```

Open:

```text
http://127.0.0.1:4173/app/
```

The Vite configuration uses `/app/` as the base path and proxies report requests to the service on port `8081`.

## FastAPI Architecture

The repository also contains the intended split architecture:

```text
frontend -> service/backend.py -> service/app.py (/analyze) -> replay
```

`service/app.py` is the AI/ML reasoning service. `service/backend.py` is the deterministic backend boundary that owns the report adapter, standards, candidates, coverage, approvals, and report assembly. The legacy `service/service_backend.py` remains the simplest frontend-compatible file-backed service on port `8081`.

Build the frontend:

```powershell
cd C:\Users\Samsung\Desktop\nexus-loop-day1\frontend
npm run build
```

## Verification Checklist

Run these checks after starting the services:

```powershell
Invoke-WebRequest http://127.0.0.1:8719/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8081/report -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:4173/app/ -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:4173/report -UseBasicParsing
```

Expected results:

- Replay health responds with HTTP `200` and `ok: true`.
- Service report responds with HTTP `200` and the full report fields.
- Frontend responds with HTTP `200` and renders the dashboard.
- Vite's `/report` proxy responds with the same report data.
- `npm run build` completes successfully.

## Data and Detection Flow

The pipeline is deliberately evidence-driven:

1. `CorpusInspector` loads the manifest, semantic catalog, and configuration timeline.
2. The preprocessor creates reusable aggregates from sessions, turns, tool calls, KB lookups, and configuration changes.
3. Specialists inspect different failure classes:
   - knowledge-base gaps and missing cohort history,
   - silent tool contract failures such as successful empty responses,
   - prompt regressions visible through turns and cost even when resolution is flat.
4. Decoys are examined and dismissed when they represent traffic mix, load, or judge-version changes rather than quality regressions.
5. The orchestrator reconciles evidence under comparability and coverage rules.
6. The report builder creates findings, diagnoses, typed prescriptions, impact blocks, and refusal/gap blocks.
7. Replay verifies prescriptions and protects a golden set.
8. The validator and `score.py` check relationships, completeness, specificity, and honesty.

The pipeline does not rely on the frontend for detection. The dashboard is a presentation and decision surface over the generated report.

## Troubleshooting

### Blank dashboard

Confirm that `/report` returns the full contract. A summary-only response is insufficient because the React screens use `gaps`, `diagnoses`, `prescriptions`, and complete finding fields.

```powershell
$r = Invoke-RestMethod http://127.0.0.1:8081/report
$r.findings.Count
$r.diagnoses.Count
$r.prescriptions.Count
$r.gaps.Count
```

Expected values for the current report are `6`, `6`, `3`, and `1`.

### `not_found` from replay

Use the correct method and route:

```text
POST /replay
GET  /health
GET  /log
```

`GET /replay` is not a valid replay request.

### `ECONNREFUSED` from Vite

Start the service backend first on port `8081`, then start Vite from the `frontend` directory. Use the locally installed binary shown above so npm does not resolve a different Vite installation from the parent directory.

### Approval requests return `404`

Start the relocated service with:

```powershell
py .\service\service_backend.py
```

The approval route is `POST /approvals` and requires a valid prescription ID, a verdict, and a non-empty reason. Decisions are stored in `.approvals.json`.

### Relative-path errors

Run Python commands from the nested directory containing both `kit` and `tools`. Running them from the workspace parent makes `--kit .\kit` resolve to the wrong location.

## Further Documentation

- [Current pipeline](nexus-loop-day1/docs/current-pipeline.md)
- [V1.1 architecture](nexus-loop-day1/docs/V1.1-architecture.md)
- [Pipeline conclusion and replay](nexus-loop-day1/docs/colclusion.md)
- [Submission note](nexus-loop-day1/docs/submission-note.md)
- [Kit README](nexus-loop-day1/tools/nexus-loop-kit/README.md)
