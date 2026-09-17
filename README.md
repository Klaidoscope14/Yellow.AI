# Nexus Loop

Building an Autonomous Improvement Loop for AI Agent Deployments.

This repository contains our submission for the **Yellow.ai TechQuest Problem Statement**: *Nexus Loop*. It implements a closed-loop system designed to ingest AI agent logs, detect failures, diagnose their root cause, prescribe configuration fixes, and automatically verify those fixes using the Replay service—putting the final decision in the hands of a human operator.

---

## Prerequisites

Required software and dependencies to run this project:
- **Python 3.10+** (Ensure Python and pip are installed and added to your PATH)
- **Node.js** (v18 or higher recommended)
- **Git** (to clone the repository)

## Installation

Follow these steps to install and configure all dependencies from scratch.

### 1. Clone the Repository
```bash
git clone https://github.com/AdityaKuranjekar/Yellow.AI.git
cd Yellow.AI
```

### 2. Set Up the Python Environment
Create and activate a virtual environment, then install the required Python packages (including `psutil` which the system uses to automatically clean up orphaned ports).

**On Windows:**
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install psutil
```

**On macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install psutil
```

### 3. Install Frontend Dependencies
Navigate to the frontend directory and install the Node.js packages:
```bash
cd frontend
npm install
cd ..
```

## Project Setup

- **Dataset Placement**: Ensure the evaluation dataset folder (`nexus-loop-kit`) is placed exactly at `Nexus-Loop/kit` relative to the root directory.
- **Environment Variables**: No manual configuration or `.env` files are required. The orchestration script dynamically configures all necessary environment variables (e.g., `NEXUS_DATA_DIR`, `NEXUS_CATALOG_PATH`, `NEXUS_LABELS_PATH`) at runtime.

## Execution

We have provided a unified Python orchestration script to safely spin up the entire multi-service architecture locally.

Run the following exact command from the root of the repository:
```bash
python run_all.py
```

*(Optional)*: To run the system against a different kit directory (such as the Day 6 sealed dataset), use the `--kit` flag:
```bash
python run_all.py --kit "D:\path\to\sealed\kit"
```

## Expected Output

After successful execution, the evaluator should expect the following sequence of events:

1. The script will automatically clean up any pre-existing background processes on ports `8719`, `8802`, `8801`, and `5173`.
2. Four local servers will start in the background:
   - **Replay Service**: Port 8719
   - **AI/ML API**: Port 8802
   - **Backend API**: Port 8801
   - **Frontend UI**: Port 5173
3. The system will automatically execute an internal HTTP call to the backend. This triggers the AI/ML diagnostic pipeline and communicates with the Replay Sandbox to verify proposed fixes.
4. The final verified report will be automatically written to `flaggingLogic/output/loop-report.json`.
5. The terminal will print `All services are running!`. The evaluator should then **open http://localhost:5173/app/ in their web browser** to interact with the findings, evidence, and the approve/reject decision UI.

---

## Key Features & Architecture

- **Detection & Diagnosis**: Evaluates real traffic against "good" standards to detect regressions, properly handling denominators and distinguishing real problems from lookalikes (marketing spikes, mix shifts).
- **Honesty & Refusals**: Properly calculates Fidelity and Coverage for every metric. Refuses to answer unanswerable questions (e.g., questions requiring non-logged events) with explicit gap specifications.
- **Verification via Replay**: Proposes concrete configuration changes and validates them against the Replay service before asking the operator for approval.
- **The Screen**: A clean, distraction-free React UI that answers: *What happened? How much did it cost? Who needs to act? What happens if they don't?*