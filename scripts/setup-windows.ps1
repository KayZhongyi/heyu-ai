[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$api = Join-Path $root "apps\api"
$venv = Join-Path $root ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

function Resolve-HeyuPython {
    if ($env:HEYU_PYTHON) {
        if (-not (Test-Path -LiteralPath $env:HEYU_PYTHON -PathType Leaf)) {
            throw "HEYU_PYTHON points to a missing file: $env:HEYU_PYTHON"
        }
        return $env:HEYU_PYTHON
    }

    $candidates = @(
        @{ Command = "py"; Arguments = @("-3.12") },
        @{ Command = "python"; Arguments = @() },
        @{ Command = "python3"; Arguments = @() }
    )
    foreach ($candidate in $candidates) {
        if (Get-Command $candidate.Command -ErrorAction SilentlyContinue) {
            $version = & $candidate.Command @($candidate.Arguments) -c `
                "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -eq "3.12") {
                return ,@($candidate.Command, $candidate.Arguments)
            }
        }
    }
    throw "Python 3.12 was not found. Install it, or set HEYU_PYTHON to python.exe."
}

Write-Host "Heyu AI: preparing the project-local environment at $venv"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $python = Resolve-HeyuPython
    if ($python -is [string]) {
        & $python -m venv $venv
    } else {
        & $python[0] @($python[1]) -m venv $venv
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the project virtual environment."
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $root "data") | Out-Null
& $venvPython -m pip install --disable-pip-version-check --upgrade pip
& $venvPython -m pip install --disable-pip-version-check $api
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed."
}

Write-Host "Setup complete. Dependencies and application data stay under: $root"
