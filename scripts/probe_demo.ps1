param(
    [Parameter(Mandatory = $true)]
    [string]$DemoPath,
    [string]$OutputPath = "runtime\probe.json"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}

& $Python ".\scripts\probe_demo.py" $DemoPath --out $OutputPath
Write-Host "Probe written to $OutputPath"
