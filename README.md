# Nexus Loop

Building an Autonomous Improvement Loop for AI Agent Deployments. 

This repository contains our submission for the **Yellow.ai TechQuest Problem Statement**: *Nexus Loop*. It implements a closed-loop system designed to ingest AI agent logs, detect failures, diagnose their root cause, prescribe configuration fixes, and automatically verify those fixes using the Replay service—putting the final decision in the hands of a human operator.

## Architecture

Our system is divided into three distinct operational layers, wrapped together by a robust pipeline:

1. **Frontend (React + Vite + TypeScript)**: A polished, operator-focused UI that presents the findings, evidence, and proposed fixes in an actionable "approve/reject" screen.
2. **Backend (FastAPI)**: The orchestration layer. It handles metric generation via DuckDB, builds candidate cohorts, and serves the frontend. 
3. **AI/ML Layer (FastAPI)**: The analytical engine. It receives cohorts from the backend, diagnoses the underlying cause (e.g., prompt regressions, API failures), prescribes a fix, and communicates with the Replay Service to verify the proposed fix's efficacy before presenting it.
4. **Replay Service**: The sandbox provided by the kit to test our fixes against the 40-run budget and prove they work without regressing the golden set.

## Prerequisites

- Python 3.10+
- Node.js (for the frontend)
- The dataset (`nexus-loop-kit`) located at `Nexus-Loop/kit`

## Setup (one-time)

```bash
# 1. Python virtual env + backend/ai-ml deps (includes psutil, used by run_all.py
#    to kill orphaned processes on our ports before (re)starting)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Frontend deps
cd frontend && npm install && cd ..
```

## How to Run

We have provided a unified Python script to safely spin up the entire multi-service architecture locally. It automatically kills any orphaned processes still holding our ports, starts the Replay Service, AI/ML layer, Backend, and Frontend, and automatically generates the initial `loop-report.json`.

Run the following command from the root of the repository, with the venv activated:

```bash
source .venv/bin/activate   # if not already active
python run_all.py
```

- **Frontend**: http://localhost:5173/app/
- **Backend API**: http://127.0.0.1:8801
- **AI/ML API**: http://127.0.0.1:8802
- **Replay Service**: http://127.0.0.1:8719

**Wait ~20-30 seconds after launching** before opening the frontend. The backend
imports DuckDB and computes the first full metrics pass (`/report`) on first
request. You can just open the page right away, though — the frontend now
shows a loading spinner ("Starting services…") and auto-retries the report
fetch for up to ~40s instead of immediately showing an error, so it recovers
on its own once the backend finishes booting. If it's still failing after
that window, a **Retry** button and the actual error message are shown —
that's the point to move to the troubleshooting steps below.

### If it fails to start / "Failed to load report" (demo troubleshooting)

The most common cause is **stale processes from a previous run still holding
the ports** — `python run_all.py` was already run once (e.g. earlier in the
day, or a prior terminal that was closed without stopping it) and the old
Replay/AI-ML/Backend servers are still bound to 8719/8802/8801/5173. The new
run then fails to bind those ports, the frontend still comes up (on 5173 or a
fallback port like 5174), but it's pointed at a dead or half-started backend
-> **HTTP 500**.

`run_all.py` now cleans this up automatically on every run (via `lsof`, no
sudo needed on macOS/Linux). If you still hit issues:

1. **Kill anything on our ports manually, then retry:**
   ```bash
   for p in 8719 8802 8801 5173 5174; do lsof -ti tcp:$p | xargs -r kill -9; done
   python run_all.py
   ```
2. **Check each service came up**, from another terminal:
   ```bash
   curl -s -o /dev/null -w "Replay:%{http_code}\n"  http://127.0.0.1:8719/
   curl -s -o /dev/null -w "AIML:%{http_code}\n"    http://127.0.0.1:8802/
   curl -s -o /dev/null -w "Backend:%{http_code}\n" http://127.0.0.1:8801/report
   curl -s -o /dev/null -w "Frontend:%{http_code}\n" http://localhost:5173/app/
   ```
   Replay/AI-ML return `404` on `/` (that's fine, they have no root route —
   just means the server is up). Backend `/report` and the frontend should
   both return `200`.
3. **Only one instance of `run_all.py` at a time.** Don't run it again in a
   new terminal to "restart" — stop the existing one first (`Ctrl+C` in the
   terminal running it, which also shuts down all 4 child services), *then*
   re-run.
4. **Before a live demo**, do a clean dry run 5-10 minutes ahead of time:
   kill stale ports (step 1), start `run_all.py`, wait 30s, and confirm the
   frontend loads the report end-to-end. Leave that instance running for the
   actual demo rather than restarting right before you go on.

## Key Features

- **Detection & Diagnosis**: Evaluates real traffic against "good" standards to detect regressions, properly handling denominators and distinguishing real problems from lookalikes (marketing spikes, mix shifts).
- **Honesty & Refusals**: Properly calculates Fidelity and Coverage for every metric. Refuses to answer unanswerable questions (e.g., questions requiring non-logged events) with explicit gap specifications.
- **Verification via Replay**: Proposes concrete configuration changes and validates them against the Replay service before asking the operator for approval.
- **The Screen**: A clean, distraction-free UI that answers: *What happened? How much did it cost? Who needs to act? What happens if they don't?*
