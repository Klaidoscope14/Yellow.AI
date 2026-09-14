# Launch the whole product in PowerShell: replay endpoint + ai/ml layer + backend.
# Frontend -> backend (:8801) -> ai/ml (:8802) -> replay (:8719).

$ErrorActionPreference = "Stop"
$ROOT = $PSScriptRoot

# Determine Python executable (avoid WindowsApps dummy aliases)
$PY = "python"
if ($env:NEXUS_PY) {
    $PY = $env:NEXUS_PY
} elseif (Test-Path "$ROOT\.venv\Scripts\python.exe") {
    $PY = "$ROOT\.venv\Scripts\python.exe"
} else {
    $realPy = Get-Command python.exe, py.exe -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notmatch "WindowsApps" } | Select-Object -First 1
    if ($realPy) {
        $PY = $realPy.Source
    }
}

$KIT = if ($env:NEXUS_KIT) { $env:NEXUS_KIT } else { "$ROOT\Nexus-Loop\kit" }
$DATA = if ($env:NEXUS_DATA_DIR) { $env:NEXUS_DATA_DIR } else { "$ROOT\flaggingLogic\data" }
$GT = if ($env:NEXUS_GROUND_TRUTH) { $env:NEXUS_GROUND_TRUTH } else { "$ROOT\flaggingLogic\pipeline\ground_truth.json" }

$env:NEXUS_DATA_DIR = $DATA
$env:NEXUS_CATALOG_PATH = if ($env:NEXUS_CATALOG_PATH) { $env:NEXUS_CATALOG_PATH } else { "$KIT\catalog.json" }
$env:NEXUS_LABELS_PATH = if ($env:NEXUS_LABELS_PATH) { $env:NEXUS_LABELS_PATH } else { "$KIT\labels\rubric_scores.jsonl" }

Write-Host "Replay  -> http://127.0.0.1:8719" -ForegroundColor Cyan
$p1 = Start-Process -FilePath $PY -ArgumentList "replay/serve.py --kit `"$KIT`" --ground-truth `"$GT`" --port 8719" -WorkingDirectory "$ROOT\Nexus-Loop\tools\nexus-loop-kit" -PassThru

Write-Host "AI/ML   -> http://127.0.0.1:8802" -ForegroundColor Cyan
$p2 = Start-Process -FilePath $PY -ArgumentList "run_aiml.py" -WorkingDirectory "$ROOT\Nexus-Loop" -PassThru

Write-Host "Backend -> http://127.0.0.1:8801" -ForegroundColor Cyan
$p3 = Start-Process -FilePath $PY -ArgumentList "run_backend.py" -WorkingDirectory "$ROOT\flaggingLogic" -PassThru

Write-Host ""
Write-Host "Services started! Press Ctrl+C in this terminal to stop all services." -ForegroundColor Green
Write-Host "Backend:  http://127.0.0.1:8801" -ForegroundColor Yellow
Write-Host "Frontend: http://localhost:5173/app/ (start separately with 'cd frontend; npm run dev')" -ForegroundColor Yellow
Write-Host ""

try {
    # Keep script alive until user stops it
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`nStopping all background processes..." -ForegroundColor Red
    if ($p1 -and !$p1.HasExited) { Stop-Process -Id $p1.Id -Force -ErrorAction SilentlyContinue }
    if ($p2 -and !$p2.HasExited) { Stop-Process -Id $p2.Id -Force -ErrorAction SilentlyContinue }
    if ($p3 -and !$p3.HasExited) { Stop-Process -Id $p3.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped." -ForegroundColor Gray
}
