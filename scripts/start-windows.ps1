[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000,
    [switch]$OpenBrowser = $true
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root "apps\api"
$python = Join-Path $root ".venv\Scripts\python.exe"
$data = Join-Path $root "data"
$pidPath = Join-Path $data "heyu-server.pid"
$secretPath = Join-Path $data "app-secret.txt"

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Heyu AI is not installed. Run the setup launcher first."
}

New-Item -ItemType Directory -Force -Path $data | Out-Null
$databasePath = (Join-Path $data "heyu.db").Replace("\", "/")
$env:DATABASE_URL = "sqlite:///$databasePath"
$env:AUTO_CREATE_SCHEMA = "false"
$env:PYTHONUTF8 = "1"
if (Test-Path -LiteralPath $secretPath -PathType Leaf) {
    $appSecret = (Get-Content -LiteralPath $secretPath -Raw).Trim()
} else {
    $secretBytes = New-Object byte[] 32
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($secretBytes)
    } finally {
        $random.Dispose()
    }
    $appSecret = [Convert]::ToBase64String($secretBytes)
    Set-Content -LiteralPath $secretPath -Value $appSecret -Encoding ASCII -NoNewline
}
if ($appSecret.Length -lt 32) {
    throw "The local APP_SECRET is invalid. Delete $secretPath and start Heyu AI again."
}
$env:APP_SECRET = $appSecret

$healthUrl = "http://127.0.0.1:$Port/health"
$workspaceUrl = "http://127.0.0.1:$Port/"
$existing = $null
try {
    $existing = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
} catch {
    # Expected when the service is not already running.
}
if ($existing) {
    if ($OpenBrowser) {
        Start-Process $workspaceUrl
    }
    Write-Host "Heyu AI is already running: $workspaceUrl"
    exit 0
}

Write-Host "Preparing the local database..."
Push-Location $api
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed. Run the reset demo launcher after preserving any needed local data."
    }
} finally {
    Pop-Location
}

Write-Host "Starting Heyu AI: $workspaceUrl"
$server = Start-Process -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $api -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $pidPath -Value $server.Id -Encoding ASCII -NoNewline

for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($server.HasExited) {
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        throw "Heyu AI exited unexpectedly with code $($server.ExitCode)."
    }
    try {
        Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1 | Out-Null
        if ($OpenBrowser) {
            Start-Process $workspaceUrl
        }
        Write-Host "Startup complete. Closing this window will not stop the background service."
        exit 0
    } catch {
        # Continue waiting until the startup deadline.
    }
}

Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
throw "Heyu AI did not become healthy within 30 seconds."
