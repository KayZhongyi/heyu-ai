[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$SkipBackup,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$dataDirectory = [System.IO.Path]::GetFullPath((Join-Path $root "data"))
$databasePath = [System.IO.Path]::GetFullPath((Join-Path $dataDirectory "heyu.db"))
$expectedPrefix = $dataDirectory.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar
$stopScript = Join-Path $PSScriptRoot "stop-windows.ps1"

if (-not $databasePath.StartsWith($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to reset a database outside the project data directory: $databasePath"
}

if (Test-Path -LiteralPath $stopScript -PathType Leaf) {
    & $stopScript
}

if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
    Write-Host "No local demo database exists. The next start will create a clean workspace."
    exit 0
}

if (-not $Force) {
    $answer = Read-Host "Reset local demo data at '$databasePath'? Type RESET to continue"
    if ($answer -cne "RESET") {
        Write-Host "Reset cancelled."
        exit 0
    }
}

if (-not $SkipBackup) {
    $backupDirectory = [System.IO.Path]::GetFullPath((Join-Path $dataDirectory "backups"))
    if (-not $backupDirectory.StartsWith(
        $expectedPrefix,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to write a backup outside the project data directory."
    }
    New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupPath = Join-Path $backupDirectory "heyu-before-reset-$timestamp.db"
    Copy-Item -LiteralPath $databasePath -Destination $backupPath
    Write-Host "Backup created: $backupPath"
}

if ($PSCmdlet.ShouldProcess($databasePath, "Remove local Heyu AI demo database")) {
    try {
        Remove-Item -LiteralPath $databasePath -Force
    } catch {
        throw "Unable to reset the database. Close any running Heyu AI server and try again."
    }
}

Write-Host "Local demo data has been reset. Start Heyu AI to create a clean workspace."
