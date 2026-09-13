"""Backend configuration, resolved from environment with safe defaults.

Every path is overridable so the same service runs against the practice kit,
the sealed kit, or any future corpus without code changes — the sealed-corpus
requirement is met by pointing these at a different directory, not by editing
literals.
"""
from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_FLAGGING = os.path.dirname(_HERE)                       # flaggingLogic/
_ROOT = os.path.dirname(_FLAGGING)                       # repo root


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# Corpus (the four files the detectors read).
DATA_DIR = _env("NEXUS_DATA_DIR", os.path.join(_FLAGGING, "data"))

# Detector thresholds.
CONFIG_PATH = _env("NEXUS_CONFIG_PATH", os.path.join(_FLAGGING, "pipeline", "config.json"))

# Catalog + labels ship with the kit; used for calibration and coverage basis.
# They are metadata only — never used to compute a metric value.
CATALOG_PATH = _env("NEXUS_CATALOG_PATH",
                    os.path.join(_ROOT, "Nexus-Loop", "kit", "catalog.json"))
LABELS_PATH = _env("NEXUS_LABELS_PATH",
                   os.path.join(_ROOT, "Nexus-Loop", "kit", "labels", "rubric_scores.jsonl"))

# Downstream services the backend calls (frontend -> backend -> ai/ml -> replay).
AIML_URL = _env("NEXUS_AIML_URL", "http://127.0.0.1:8802")
REPLAY_URL = _env("NEXUS_REPLAY_URL", "http://127.0.0.1:8719")

# Corpus identity for the report header; discovered, defaulted to A.
CORPUS_VARIANT = _env("NEXUS_CORPUS_VARIANT", "A")

# Calibration tolerance: model vs human quality agreement on a 1-5 scale.
CALIBRATION_TOLERANCE = float(_env("NEXUS_CALIBRATION_TOLERANCE", "1.0"))

# HTTP timeout (seconds) for the ai/ml call — generous, replay verification runs there.
AIML_TIMEOUT_S = float(_env("NEXUS_AIML_TIMEOUT_S", "120"))

# Golden-set size sent to replay's regression guard.
GOLDEN_SET_SIZE = int(_env("NEXUS_GOLDEN_SET_SIZE", "20"))

# Comma-separated CORS allow-list for the browser frontend; empty => permissive (dev).
CORS_ORIGINS = _env("NEXUS_CORS_ORIGINS", "")
