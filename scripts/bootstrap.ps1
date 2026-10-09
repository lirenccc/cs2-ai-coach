$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

Write-Host "== Node dependencies =="
pnpm install

Write-Host "== Python virtual environment =="
if (-not (Test-Path ".venv")) {
    py -3.12 -m venv .venv
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".\services\analyzer[dev,ai,demo]"

New-Item -ItemType Directory -Force -Path "runtime" | Out-Null
Write-Host "Bootstrap complete. Next: .\scripts\check.ps1"
