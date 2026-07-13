"""Focused self-test for the repository audit rules."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name("audit-repository.py")
SPEC = importlib.util.spec_from_file_location("audit_repository", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def expect_finding(path: str, text: str, tmp_path: Path) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    old_root = MODULE.ROOT
    MODULE.ROOT = tmp_path
    try:
        assert MODULE.audit([path])
    finally:
        MODULE.ROOT = old_root


def main() -> None:
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        root = Path(directory)
        expect_finding("private/material.pdf", "not inspected", root)
        expect_finding("config/.env", "SAFE=value", root)
        expect_finding(
            "notes.md",
            "token = " + "ghp_" + "abcdefghijklmnopqrstuvwxyz1234567890",
            root,
        )
        expect_finding(
            "server.pem",
            "-----BEGIN " + "PRIVATE KEY-----\nsecret\n-----END " + "PRIVATE KEY-----",
            root,
        )
        expect_finding(
            "config.yaml",
            "APP_" + "SECRET: genuinely-secret-production-value-123456",
            root,
        )

        safe = root / ".env.example"
        safe.write_text("APP_SECRET=replace-this-in-production\n", encoding="utf-8")
        compose = root / "compose.yaml"
        compose.write_text(
            "APP_SECRET: ${APP_SECRET:-local-development-secret}\n",
            encoding="utf-8",
        )
        old_root = MODULE.ROOT
        MODULE.ROOT = root
        try:
            assert MODULE.audit([".env.example", "compose.yaml"]) == []
        finally:
            MODULE.ROOT = old_root

    print("Repository audit rule self-test passed.")


if __name__ == "__main__":
    main()
