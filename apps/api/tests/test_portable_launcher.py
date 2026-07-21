from pathlib import Path

import pytest

from portable_launcher import load_or_create_app_secret


def test_portable_app_secret_is_strong_and_persistent(tmp_path: Path):
    first = load_or_create_app_secret(tmp_path)
    second = load_or_create_app_secret(tmp_path)

    assert first == second
    assert len(first) >= 32
    assert (tmp_path / "app-secret.txt").read_text(encoding="ascii") == first


def test_portable_app_secret_rejects_an_invalid_persisted_value(tmp_path: Path):
    (tmp_path / "app-secret.txt").write_text("too-short", encoding="ascii")

    with pytest.raises(RuntimeError, match="local APP_SECRET is invalid"):
        load_or_create_app_secret(tmp_path)
