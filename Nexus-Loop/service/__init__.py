"""AI/ML (agentic) service for the Nexus Loop product.

Consumes detection candidates from the backend, reconciles them through the
trust-aware orchestrator, diagnoses cause, prescribes typed fixes, verifies
them against the replay endpoint, and authors the gap specs. It never re-reads
the raw corpus and never asks a model to compute a metric (Golden Rule 1); its
job is reasoning over the backend's deterministic evidence.
"""
