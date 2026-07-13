"""Fail when tracked repository files contain private artifacts or obvious secrets."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_SUFFIXES = {
    ".db",
    ".doc",
    ".docx",
    ".key",
    ".p12",
    ".pdf",
    ".pem",
    ".ppt",
    ".pptx",
    ".sqlite",
    ".sqlite3",
}
FORBIDDEN_NAMES = {
    ".env",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
ALLOWED_PATHS = {
    ".env.example",
}
TEXT_SUFFIXES = {
    "",
    ".bat",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

SECRET_PATTERNS = [
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "generic assigned secret",
        re.compile(
            r"""(?ix)
            \b(?:api[_-]?key|access[_-]?token|client[_-]?secret|app[_-]?secret)
            \s*[:=]\s*
            ["']?(?P<value>[^\s"'#]{24,})
            """
        ),
    ),
]

GENERIC_SECRET_PLACEHOLDERS = {
    "a-unique-production-secret",
    "dummy",
    "example",
    "local-development-secret",
    "replace",
    "test",
}


def is_placeholder_secret(value: str) -> bool:
    normalized = value.lower()
    return "${" in value or any(
        placeholder in normalized for placeholder in GENERIC_SECRET_PLACEHOLDERS
    )


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def audit(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for relative in paths:
        normalized = relative.replace("\\", "/")
        path = PurePosixPath(normalized)
        if normalized in ALLOWED_PATHS:
            continue
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"forbidden tracked artifact: {normalized}")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue

        absolute = ROOT / Path(*path.parts)
        try:
            text = absolute.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            if label == "generic assigned secret" and is_placeholder_secret(
                match.group("value")
            ):
                continue
            findings.append(f"possible {label}: {normalized}")
    return findings


def main() -> int:
    findings = audit(tracked_paths())
    if findings:
        print("Repository audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Repository audit passed: no forbidden tracked artifacts or obvious secrets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
