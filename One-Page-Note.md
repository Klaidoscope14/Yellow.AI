# One-Page Note: Assumptions & Transparency

In accordance with the TechQuest guidelines, this note provides complete transparency into the engineering shortcuts taken to build the Nexus Loop system within the given time constraints, explicitly distinguishing between what is real, what is stubbed, and what will break at scale.

### What is real.
* **The Orchestration Architecture**: The microservice boundaries between the Frontend (Vite), Backend (FastAPI), AI/ML Layer (FastAPI), and the external Replay Service are fully implemented over HTTP.
* **The Metrics Engine**: Data ingestion and metric calculations are genuinely executed using DuckDB against the provided `kit/corpus` dataset. We actively calculate coverage, fidelity, and isolate specific traffic cohorts.
* **The Screen & Operator Flow**: The React frontend is a real interactive application. It genuinely fetches the `loop-report.json` payload, renders the evidence, and provides functional approve/reject UI controls for the operator.
* **Verification Pipeline**: The AI/ML layer makes genuine network calls to the local Replay Service (`/replay`) to test prescriptions against the budget and record the before/after effects.

### What is stubbed.
* **LLM Diagnoses & Prescriptions**: To ensure deterministic execution during the demonstration, the actual language model inference step is stubbed. The system uses hardcoded heuristic detection (e.g., matching known `STRAY_IDS` and static text parsing) to surface the specific planted faults and lookalikes, rather than passing the transcripts to a live LLM for dynamic diagnosis and generation of the prompt fix.
* **Decision Persistence**: When a human operator clicks "Approve" or "Reject" in the UI, the decision is handled by the frontend state and stubbed backend endpoints. It is not permanently persisted to a relational database.
* **Unanswerable Question Detection**: The logic that identifies and refuses Ask A11 ("What is our failover rate?") is hardcoded as a static gap specification rather than dynamically inferred by an agent reading `catalog.json`. 

### What is simulated.
* **The Sandbox**: The Replay Service itself is a local simulation provided by the organizers to model the effects of a fix, acting as a stand-in for a real production A/B testing and deployment pipeline.

### What breaks at 100× the scale.
* **Synchronous HTTP Pipeline**: Our backend triggers the AI/ML layer, which triggers the Replay service synchronously during the `/report` generation. At 100× the traffic and complexity, this synchronous chain would suffer from severe connection pooling exhaustion and HTTP timeouts. We would need to migrate to an asynchronous message broker (e.g., Celery/RabbitMQ) for offline report generation.
* **In-Memory & Flat File Storage**: Writing the output directly to a flat `loop-report.json` file will encounter file-locking and race conditions if multiple operators access the system simultaneously. A proper RDBMS (like PostgreSQL) is required to manage state, findings, and human decisions concurrently.
* **Local DuckDB Analytics**: Querying raw Gzipped JSON lines directly from the file system works for the 80,000 conversations in the kit. At 100× the scale (millions of conversations, gigabytes of data), local single-node memory limits would be exceeded. The ingestion pipeline would need to be migrated to a distributed cloud data warehouse (e.g., Google BigQuery or Snowflake).
