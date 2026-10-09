$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}

$Port = 8765
$Token = [Convert]::ToHexString(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLowerInvariant()

$env:CS2_COACH_ANALYZER_HOST = "127.0.0.1"
$env:CS2_COACH_ANALYZER_PORT = "$Port"
$env:CS2_COACH_SESSION_TOKEN = $Token
$env:CS2_COACH_DB_PATH = (Join-Path $Root "runtime\app.db")

$AnalyzerArgs = @(
    "-m", "app",
    "--host", "127.0.0.1",
    "--port", "$Port",
    "--token", "$Token",
    "--db-path", $env:CS2_COACH_DB_PATH
)

$Analyzer = Start-Process `
    -FilePath $Python `
    -ArgumentList $AnalyzerArgs `
    -WorkingDirectory (Join-Path $Root "services\analyzer") `
    -PassThru `
    -NoNewWindow

try {
    Start-Sleep -Milliseconds 700
    pnpm tauri dev
}
finally {
    if (-not $Analyzer.HasExited) {
        Stop-Process -Id $Analyzer.Id -Force
    }
}
