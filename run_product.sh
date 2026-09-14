#!/bin/bash
# Launch the whole product: replay endpoint + ai/ml layer + backend.
# Frontend -> backend (:8801) -> ai/ml (:8802) -> replay (:8719).
#
#   ./run_product.sh            # uses ./.venv and the practice kit
#   NEXUS_KIT=/path/to/kit ./run_product.sh   # point every layer at another corpus
#
# Ctrl-C stops all three.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${NEXUS_PY:-}" ]; then
  PY="$NEXUS_PY"
elif [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/.venv/Scripts/python.exe" ]; then
  PY="$ROOT/.venv/Scripts/python.exe"
elif command -v py >/dev/null 2>&1; then
  PY="py"
else
  PY="python"
fi
KIT="${NEXUS_KIT:-$ROOT/Nexus-Loop/kit}"
DATA="${NEXUS_DATA_DIR:-$ROOT/flaggingLogic/data}"
GT="${NEXUS_GROUND_TRUTH:-$ROOT/flaggingLogic/pipeline/ground_truth.json}"

export NEXUS_DATA_DIR="$DATA"
export NEXUS_CATALOG_PATH="${NEXUS_CATALOG_PATH:-$KIT/catalog.json}"
export NEXUS_LABELS_PATH="${NEXUS_LABELS_PATH:-$KIT/labels/rubric_scores.jsonl}"

pids=()
cleanup() { echo; echo "stopping..."; for p in "${pids[@]}"; do kill "$p" 2>/dev/null; done; }
trap cleanup EXIT INT TERM

echo "replay  -> http://127.0.0.1:8719"
( cd "$ROOT/Nexus-Loop/tools/nexus-loop-kit" && "$PY" replay/serve.py --kit "$KIT" --ground-truth "$GT" --port 8719 ) &
pids+=($!)

echo "ai/ml   -> http://127.0.0.1:8802"
( cd "$ROOT/Nexus-Loop" && "$PY" run_aiml.py ) &
pids+=($!)

echo "backend -> http://127.0.0.1:8801   (GET /report, /metrics, /findings, /coverage)"
( cd "$ROOT/flaggingLogic" && "$PY" run_backend.py ) &
pids+=($!)

echo "warming backend (first request rescans the corpus once)..."
for i in $(seq 1 60); do
  if "$PY" -c "import httpx,sys;sys.exit(0 if httpx.get('http://127.0.0.1:8801/health',timeout=2).json().get('ready') else 1)" 2>/dev/null; then
    echo "ready. try:  curl http://127.0.0.1:8801/report"; break
  fi
  sleep 1
done
wait
