"""AI/ML service configuration, environment-overridable with safe defaults."""
from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_NEXUS = os.path.dirname(_HERE)                          # Nexus-Loop/
_ROOT = os.path.dirname(_NEXUS)                          # repo root


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# Replay endpoint the ai/ml layer verifies prescriptions against.
REPLAY_URL = _env("NEXUS_REPLAY_URL", "http://127.0.0.1:8719")

# Catalog used for gap authoring (NOT_MEASURABLE capabilities, required events).
CATALOG_PATH = _env("NEXUS_CATALOG_PATH",
                    os.path.join(_NEXUS, "kit", "catalog.json"))

# Kit dir for the replay golden set (known-good sessions).
KIT_DIR = _env("NEXUS_KIT_DIR", os.path.join(_NEXUS, "kit"))

# Replay is optional: if unreachable, verification degrades gracefully.
REPLAY_ENABLED = _env("NEXUS_REPLAY_ENABLED", "1") not in ("0", "false", "False", "")
REPLAY_TIMEOUT_S = float(_env("NEXUS_REPLAY_TIMEOUT_S", "30"))
GOLDEN_SET_SIZE = int(_env("NEXUS_GOLDEN_SET_SIZE", "20"))
