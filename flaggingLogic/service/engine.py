"""Cached backend engine.

Ingests the corpus ONCE into an in-memory DuckDB, computes the metric family,
runs the detectors, mines standards, and derives coverage + calibration. All
results are cached for the life of the process, so serving a request is a dict
lookup, not an 880k-row rescan — this is what keeps the API from dipping the
6-second batch performance under load.

Everything here is deterministic SQL / arithmetic. No model is consulted to
produce any number (Golden Rule 1).
"""
from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any, Dict, List, Optional

from . import settings

# The existing engine modules live in pipeline/ and import each other by bare
# name (import ingest, ...). Put that dir on the path and import them as-is so
# the batch CLI and the service share one code path.
_PIPELINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline")
if _PIPELINE_DIR not in sys.path:
    sys.path.insert(0, _PIPELINE_DIR)

import duckdb  # noqa: E402
import metrics as metrics_mod  # noqa: E402
import detect as detect_mod  # noqa: E402
import standards as standards_mod  # noqa: E402


def _connect(data_dir: str) -> duckdb.DuckDBPyConnection:
    data = data_dir.replace("\\", "/")
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW sessions AS SELECT * FROM read_json_auto('{data}/sessions.jsonl.gz')")
    con.execute(f"CREATE VIEW steps AS SELECT * FROM read_json_auto('{data}/agent_steps.jsonl.gz')")
    con.execute(f"CREATE VIEW turns AS SELECT * FROM read_json_auto('{data}/turns.jsonl.gz')")
    con.execute(f"CREATE VIEW config_timeline AS SELECT * FROM read_csv_auto('{data}/config_timeline.csv')")
    return con


class BackendEngine:
    """Loads and caches all deterministic outputs. Thread-safe, compute-once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = False
        self._con: Optional[duckdb.DuckDBPyConnection] = None
        self._cfg: Dict[str, Any] = {}
        self._catalog: Dict[str, Any] = {}
        self._metrics: Dict[str, Any] = {}
        self._candidates: List[Dict[str, Any]] = []
        self._standards: List[Dict[str, Any]] = []
        self._coverage: List[Dict[str, Any]] = []
        self._calibration: Optional[Dict[str, Any]] = None
        self._cardinality: List[Dict[str, Any]] = []
        self._row_counts: Dict[str, int] = {}

    # -- lifecycle ---------------------------------------------------------

    def warm(self) -> None:
        """Idempotently compute and cache everything. Safe to call repeatedly."""
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            self._con = _connect(settings.DATA_DIR)
            with open(settings.CONFIG_PATH) as fh:
                self._cfg = json.load(fh)
            self._catalog = self._load_catalog()

            self._row_counts = {
                "sessions": self._scalar("SELECT COUNT(*) FROM sessions"),
                "steps": self._scalar("SELECT COUNT(*) FROM steps"),
                "turns": self._scalar("SELECT COUNT(*) FROM turns"),
                "config": self._scalar("SELECT COUNT(*) FROM config_timeline"),
            }

            self._metrics = metrics_mod.compute_all(self._con)
            self._candidates = detect_mod.run_all(self._metrics, self._cfg)
            self._standards = standards_mod.mine_standards(self._con)
            self._coverage = self._metrics.get("coverage", [])
            self._calibration = self._compute_calibration()
            self._cardinality = self._compute_cardinality()
            self._ready = True

    def _load_catalog(self) -> Dict[str, Any]:
        try:
            with open(settings.CATALOG_PATH) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    # -- derived, deterministic signals ------------------------------------

    def _compute_calibration(self) -> Optional[Dict[str, Any]]:
        """Real judge calibration: model quality_score vs human labels, within
        one judge_version. Returns None if labels are unavailable rather than
        publishing a fabricated agreement number."""
        path = settings.LABELS_PATH
        if not os.path.exists(path):
            return None
        try:
            rows = self._con.execute("""
                WITH lab AS (
                    SELECT * FROM read_json_auto(?)
                )
                SELECT s.judge_version AS jv,
                       COUNT(*) AS n,
                       AVG(CASE WHEN abs(s.quality_score - lab.human_quality) <= ?
                                THEN 1.0 ELSE 0.0 END) AS agreement
                FROM lab
                JOIN sessions s USING (session_id)
                WHERE lab.judge_version_at_label_time = s.judge_version
                GROUP BY s.judge_version
                ORDER BY n DESC
            """, [path.replace("\\", "/"), settings.CALIBRATION_TOLERANCE]).fetchall()
        except duckdb.Error:
            return None
        if not rows:
            return None
        jv, n, agreement = rows[0]
        return {"agreement": round(float(agreement), 4), "n": int(n), "judge_version": jv}

    def _compute_cardinality(self) -> List[Dict[str, Any]]:
        """For every session-grain dimension carrying a catalog cardinality
        budget, measure its true distinct count. Fields whose cardinality
        exceeds the budget are marked refuse=True — a breakdown over them must
        be refused, not truncated. Fully catalog-driven; no field is named in
        code."""
        budgets = (self._catalog.get("cardinality_budgets") or {})
        out: List[Dict[str, Any]] = []
        for field_path, budget in budgets.items():
            if field_path.startswith("_") or not isinstance(budget, (int, float)):
                continue
            if not field_path.startswith("session."):
                continue  # session-grain breakdowns only
            expr = field_path[len("session."):]  # e.g. custom_dims.customer_ref / session_id
            try:
                distinct = self._scalar(f"SELECT COUNT(DISTINCT {expr}) FROM sessions")
            except duckdb.Error:
                continue
            out.append({
                "field": field_path,
                "budget": int(budget),
                "distinct": int(distinct),
                "refuse": distinct > budget,
            })
        return out

    # -- helpers -----------------------------------------------------------

    def _scalar(self, sql: str) -> int:
        return int(self._con.execute(sql).fetchone()[0])

    def tool_coverage(self) -> float:
        """Minimum non-legacy session share across tenants — the honest
        denominator for any tool/kb/cost metric. Computed, never assumed."""
        shares = [r["v3_coverage"] for r in self._coverage if r.get("v3_coverage") is not None]
        return round(min(shares), 4) if shares else 1.0

    def coverage_by_tenant(self) -> Dict[str, float]:
        return {r["tenant"]: round(r["v3_coverage"], 4) for r in self._coverage}

    def golden_set(self, limit: int = 20) -> List[str]:
        """Known-good session ids (resolved, non-legacy) for replay's regression
        guard. Deterministic ordering so the yardstick is stable across runs."""
        rows = self._con.execute("""
            SELECT session_id FROM sessions
            WHERE session_end = 'resolved' AND agent_kind = 'v3_agent'
            ORDER BY session_id
            LIMIT ?
        """, [max(0, int(limit))]).fetchall()
        return [r[0] for r in rows]

    # -- accessors ---------------------------------------------------------

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def row_counts(self) -> Dict[str, int]:
        return dict(self._row_counts)

    @property
    def candidates(self) -> List[Dict[str, Any]]:
        return self._candidates

    @property
    def standards(self) -> List[Dict[str, Any]]:
        return self._standards

    @property
    def calibration(self) -> Optional[Dict[str, Any]]:
        return dict(self._calibration) if self._calibration else None

    @property
    def cardinality(self) -> List[Dict[str, Any]]:
        return list(self._cardinality)

    @property
    def catalog(self) -> Dict[str, Any]:
        return self._catalog


# Process-wide singleton.
engine = BackendEngine()
