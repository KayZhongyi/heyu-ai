[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root "dist"
}
$workDirectory = Join-Path $root "work\pyinstaller"
$specDirectory = Join-Path $workDirectory "spec"
$portableDirectory = Join-Path $OutputDirectory "heyu-ai-windows-portable"

function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Parent,
        [Parameter(Mandatory = $true)]
        [string]$Child
    )

    $parentPath = [System.IO.Path]::GetFullPath($Parent).TrimEnd(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $childPath = [System.IO.Path]::GetFullPath($Child)
    $prefix = $parentPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $childPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the selected output directory: $childPath"
    }
}

Assert-ChildPath -Parent $OutputDirectory -Child $portableDirectory
New-Item -ItemType Directory -Force -Path $OutputDirectory, $workDirectory, $specDirectory |
    Out-Null

& $Python -c "import app.main, alembic, fastapi, sqlalchemy, uvicorn"
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python environment does not contain the installed Heyu AI application."
}

& $Python -m pip install --disable-pip-version-check "pyinstaller==6.21.0"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to install the Windows packaging tool."
}

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name "HeyuAI" `
    --paths (Join-Path $root "apps\api") `
    --add-data "$root\apps\web;web" `
    --add-data "$root\apps\api\migrations;migrations" `
    --add-data "$root\apps\api\alembic.ini;." `
    --hidden-import "app.main" `
    --collect-submodules "app" `
    --collect-all "pwdlib" `
    --collect-all "argon2" `
    --distpath $OutputDirectory `
    --workpath $workDirectory `
    --specpath $specDirectory `
    (Join-Path $root "apps\api\portable_launcher.py")
if ($LASTEXITCODE -ne 0) {
    throw "Unable to build the Windows portable package."
}

$builtDirectory = Join-Path $OutputDirectory "HeyuAI"
if (-not (Test-Path -LiteralPath $builtDirectory -PathType Container)) {
    throw "PyInstaller did not create the expected application directory."
}

if (Test-Path -LiteralPath $portableDirectory) {
    Remove-Item -LiteralPath $portableDirectory -Recurse -Force
}
Move-Item -LiteralPath $builtDirectory -Destination $portableDirectory
Copy-Item -LiteralPath (Join-Path $root "docs\portable-model-settings.example.env") `
    -Destination (Join-Path $portableDirectory "portable-model-settings.example.env")

@"
Heyu AI Windows Portable

1. Double-click HeyuAI.exe.
2. Wait for the browser to open.
3. Close the launcher window to stop the platform.

Python, Git, Docker, Ollama, and Node.js are not required.
Local data is stored in the data folder beside the executable.

The default generator is free and deterministic. To use an approved external
model, copy portable-model-settings.example.env to .env, enter the provider
settings, and restart HeyuAI. Never share or commit the completed .env file.
"@ | Set-Content -LiteralPath (Join-Path $portableDirectory "README.txt") -Encoding UTF8

$archive = Join-Path $OutputDirectory "heyu-ai-windows-portable.zip"
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
Compress-Archive -Path "$portableDirectory\*" -DestinationPath $archive
Write-Host "Portable package created: $archive"
