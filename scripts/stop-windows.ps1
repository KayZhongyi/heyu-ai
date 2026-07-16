[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$dataDirectory = [System.IO.Path]::GetFullPath((Join-Path $root "data"))
$pidPath = [System.IO.Path]::GetFullPath((Join-Path $dataDirectory "heyu-server.pid"))
$expectedPrefix = $dataDirectory.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar

if (-not $pidPath.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use a PID file outside the project data directory: $pidPath"
}

if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
    Write-Host "No Heyu AI process started by this project was found."
    exit 0
}

$rawPid = (Get-Content -LiteralPath $pidPath -Raw -Encoding ASCII).Trim()
$processId = 0
if (-not [int]::TryParse($rawPid, [ref]$processId) -or $processId -le 0) {
    throw "The Heyu AI PID file is invalid. Remove it manually after checking: $pidPath"
}

$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $pidPath -Force
    Write-Host "Heyu AI was already stopped. Removed the stale PID file."
    exit 0
}

$commandLine = $null
try {
    $commandLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $processId").CommandLine
} catch {
    throw "Unable to verify process $processId. Refusing to stop it automatically."
}

if (
    $process.ProcessName -notmatch "^python" -or
    $commandLine -notmatch "uvicorn" -or
    $commandLine -notmatch "app\.main:app"
) {
    throw "PID $processId does not look like the Heyu AI server. Refusing to stop it."
}

Stop-Process -Id $processId
Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue

$healthUrl = "http://127.0.0.1:$Port/health"
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
        Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1 | Out-Null
        Start-Sleep -Milliseconds 250
    } catch {
        Write-Host "Heyu AI has stopped."
        exit 0
    }
}

throw "The recorded process stopped, but port $Port still serves a health endpoint."
