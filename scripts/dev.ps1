$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

# Tauri owns sidecar lifecycle (random loopback port + per-session token).
# Pass only paths / interpreter hints — never a token for the renderer.
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $Python) {
    $env:CS2_COACH_ANALYZER_PYTHON = $Python
}
else {
    Write-Warning "Missing .venv; Tauri will fall back to system Python 3.12+."
}
$env:CS2_COACH_DB_PATH = (Join-Path $Root "runtime\app.db")

pnpm tauri dev
