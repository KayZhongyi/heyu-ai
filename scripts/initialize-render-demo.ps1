[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [string]$OutputDirectory = "outputs/render-demo"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-SecretValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvironmentName,

        [Parameter(Mandatory = $true)]
        [string]$Prompt,

        [int]$MinimumLength = 10
    )

    $value = [Environment]::GetEnvironmentVariable($EnvironmentName, "Process")
    if (-not $value) {
        $secureValue = Read-Host $Prompt -AsSecureString
        $value = [System.Net.NetworkCredential]::new("", $secureValue).Password
    }
    if ($value.Length -lt $MinimumLength) {
        throw "$EnvironmentName must contain at least $MinimumLength characters."
    }
    return $value
}

function Invoke-PythonStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Python $($Arguments[0])"
    }
}

$parsedUrl = $null
if (
    -not [Uri]::TryCreate($BaseUrl, [UriKind]::Absolute, [ref]$parsedUrl) -or
    $parsedUrl.Scheme -ne "https"
) {
    throw "BaseUrl must be an absolute HTTPS URL, for example https://heyu-ai-demo.onrender.com."
}
$normalizedBaseUrl = $BaseUrl.TrimEnd("/")

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
}
else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Run scripts/setup-windows.ps1 first."
    }
    $python = $pythonCommand.Source
}

$outputRoot = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
}
else {
    [IO.Path]::GetFullPath((Join-Path $repositoryRoot $OutputDirectory))
}
New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null

$managedVariables = @(
    "HEYU_DEMO_USERNAME",
    "HEYU_DEMO_PASSWORD",
    "HEYU_DEMO_OWNER_PASSWORD",
    "HEYU_DEMO_CREATOR_PASSWORD",
    "HEYU_DEMO_REVIEWER_PASSWORD"
)
$previousValues = @{}
foreach ($name in $managedVariables) {
    $previousValues[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

try {
    $gatePassword = Get-SecretValue `
        -EnvironmentName "HEYU_DEMO_PASSWORD" `
        -Prompt "Render demo access password" `
        -MinimumLength 12
    $ownerPassword = Get-SecretValue `
        -EnvironmentName "HEYU_DEMO_OWNER_PASSWORD" `
        -Prompt "Owner demo account password"
    $creatorPassword = Get-SecretValue `
        -EnvironmentName "HEYU_DEMO_CREATOR_PASSWORD" `
        -Prompt "Creator demo account password"
    $reviewerPassword = Get-SecretValue `
        -EnvironmentName "HEYU_DEMO_REVIEWER_PASSWORD" `
        -Prompt "Reviewer demo account password"

    [Environment]::SetEnvironmentVariable("HEYU_DEMO_USERNAME", "heyu-demo", "Process")
    [Environment]::SetEnvironmentVariable(
        "HEYU_DEMO_PASSWORD",
        $gatePassword,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "HEYU_DEMO_OWNER_PASSWORD",
        $ownerPassword,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "HEYU_DEMO_CREATOR_PASSWORD",
        $creatorPassword,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "HEYU_DEMO_REVIEWER_PASSWORD",
        $reviewerPassword,
        "Process"
    )

    Invoke-PythonStep -Python $python -Arguments @(
        (Join-Path $PSScriptRoot "setup_demo_accounts.py"),
        "--base-url",
        $normalizedBaseUrl,
        "--accounts",
        "3",
        "--output",
        (Join-Path $outputRoot "accounts.json")
    )
    Invoke-PythonStep -Python $python -Arguments @(
        (Join-Path $PSScriptRoot "seed_demo_workspace.py"),
        "--base-url",
        $normalizedBaseUrl,
        "--output",
        (Join-Path $outputRoot "workspace.json")
    )

    Write-Host ""
    Write-Host "Render demo initialization completed." -ForegroundColor Green
    Write-Host "Owner account:    leader@demo.example"
    Write-Host "Creator account:  video@demo.example"
    Write-Host "Reviewer account: review@demo.example"
    Write-Host "Non-secret reports: $outputRoot"
    Write-Host "Passwords were not written to reports. Share them privately."
}
finally {
    foreach ($name in $managedVariables) {
        [Environment]::SetEnvironmentVariable(
            $name,
            $previousValues[$name],
            "Process"
        )
    }
    $gatePassword = $null
    $ownerPassword = $null
    $creatorPassword = $null
    $reviewerPassword = $null
}
