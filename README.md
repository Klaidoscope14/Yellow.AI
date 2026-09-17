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

- **Python 3.10+** (Ensure Python and pip are installed and added to your PATH)
- **Node.js** (v18 or higher recommended, for the frontend)
- **Git** (to clone the repository)
- The dataset (`nexus-loop-kit`) located at `Nexus-Loop/kit`

## Complete Setup Guide (New Device)

Follow these steps to set up the project from scratch on a new device:

### 1. Clone the Repository
```bash
git clone https://github.com/AdityaKuranjekar/Yellow.AI.git
cd Yellow.AI
```

### 2. Set Up the Python Environment
Create and activate a virtual environment, then install the required Python dependencies.

**On Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**On macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

*(Note: Ensure you also have `psutil` installed, as `run_all.py` uses it to clean up orphaned ports: `pip install psutil`)*

### 3. Install Frontend Dependencies
Navigate to the frontend directory and install the Node.js packages:
```bash
cd frontend
npm install
cd ..
```

## How to Run

We have provided a unified Python script to safely spin up the entire multi-service architecture locally. It automatically cleans up any orphaned ports, starts the Replay Service, AI/ML layer, Backend, and Frontend, and automatically generates the initial `loop-report.json`.

Run the following command from the root of the repository:

```bash
python run_all.py
```

- **Frontend**: http://localhost:5173/app/
- **Backend API**: http://127.0.0.1:8801
- **AI/ML API**: http://127.0.0.1:8802
- **Replay Service**: http://127.0.0.1:8719

## Key Features

- **Detection & Diagnosis**: Evaluates real traffic against "good" standards to detect regressions, properly handling denominators and distinguishing real problems from lookalikes (marketing spikes, mix shifts).
- **Honesty & Refusals**: Properly calculates Fidelity and Coverage for every metric. Refuses to answer unanswerable questions (e.g., questions requiring non-logged events) with explicit gap specifications.
- **Verification via Replay**: Proposes concrete configuration changes and validates them against the Replay service before asking the operator for approval.
- **The Screen**: A clean, distraction-free UI that answers: *What happened? How much did it cost? Who needs to act? What happens if they don't?*
