"""Backend service package for the Nexus Loop product.

Wraps the deterministic flaggingLogic engine (DuckDB SQL metrics + detectors)
behind a cached, in-process engine and a FastAPI app. No LLMs touch metric
computation (Golden Rule 1); FastAPI is pure transport.
"""
