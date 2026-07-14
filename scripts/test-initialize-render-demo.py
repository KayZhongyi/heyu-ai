#!/usr/bin/env python3
"""Static safety checks for the interactive Render demo initializer."""

from pathlib import Path

script = (Path(__file__).resolve().parent / "initialize-render-demo.ps1").read_text(
    encoding="utf-8"
)

required_fragments = (
    "Read-Host $Prompt -AsSecureString",
    '[Environment]::GetEnvironmentVariable($EnvironmentName, "Process")',
    '"HEYU_DEMO_PASSWORD",\n        $gatePassword,\n        "Process"',
    "setup_demo_accounts.py",
    "seed_demo_workspace.py",
    "finally {",
    "$previousValues[$name]",
    '$parsedUrl.Scheme -ne "https"',
)
for fragment in required_fragments:
    assert fragment in script, f"Missing safety behavior: {fragment}"

for forbidden in (
    "[string]$Password",
    "[string]$OwnerPassword",
    "[string]$CreatorPassword",
    "[string]$ReviewerPassword",
    "--password",
):
    assert forbidden not in script, (
        f"Secret must not be accepted on the command line: {forbidden}"
    )

assert script.index("setup_demo_accounts.py") < script.index("seed_demo_workspace.py")
assert script.count("HEYU_DEMO_PASSWORD") >= 3

print("Interactive Render demo initializer safety checks passed.")
