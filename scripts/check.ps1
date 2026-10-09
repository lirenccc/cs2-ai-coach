$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

& $Python ".\scripts\validate_scaffold.py"
& $Python -m pytest ".\services\analyzer\tests" -q
pnpm test
pnpm lint

if (Get-Command cargo -ErrorAction SilentlyContinue) {
    cargo test --manifest-path ".\Cargo.toml"
}
else {
    Write-Warning "cargo is not installed; Rust tests skipped."
}
