$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> pnpm test"
pnpm test

Write-Host "==> cargo test"
cargo test

Write-Host "==> pytest (services/analyzer)"
Push-Location "services/analyzer"
python -m pytest
Pop-Location

Write-Host "All bootstrap tests passed."
