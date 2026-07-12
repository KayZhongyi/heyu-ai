[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root "apps\api"
$python = Join-Path $root ".venv\Scripts\python.exe"
$data = Join-Path $root "data"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Heyu AI is not installed. Run the setup launcher first."
}

New-Item -ItemType Directory -Force -Path $data | Out-Null
$databasePath = (Join-Path $data "heyu.db").Replace("\", "/")
$env:DATABASE_URL = "sqlite:///$databasePath"
$env:PYTHONUTF8 = "1"

$healthUrl = "http://127.0.0.1:$Port/health"
$docsUrl = "http://127.0.0.1:$Port/docs"
$existing = $null
try {
    $existing = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
} catch {
    # Expected when the service is not already running.
}
if ($existing) {
    Start-Process $docsUrl
    Write-Host "Heyu AI is already running: $docsUrl"
    exit 0
}

Write-Host "Starting Heyu AI: $docsUrl"
$server = Start-Process -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $api -WindowStyle Hidden -PassThru

for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($server.HasExited) {
        throw "Heyu AI exited unexpectedly with code $($server.ExitCode)."
    }
    try {
        Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1 | Out-Null
        Start-Process $docsUrl
        Write-Host "Startup complete. Closing this window will not stop the background service."
        exit 0
    } catch {
        # Continue waiting until the startup deadline.
    }
}

Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
throw "Heyu AI did not become healthy within 30 seconds."
