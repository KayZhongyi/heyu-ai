from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probe-openai-compatible-provider.py"


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("probe_openai_compatible_provider", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mock_probe_cli_is_offline_and_returns_safe_summary():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--mock"],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["mode"] == "mock"
    assert payload["ok"] is True
    assert payload["provider_contract"] == "openai-compatible"
    assert "api" not in completed.stdout.lower()
    assert completed.stderr == ""


def test_probe_provider_posts_expected_openai_compatible_contract():
    module = _load_probe_module()
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "ok": True,
                                        "provider_contract": "openai-compatible",
                                        "supports_json_object": True,
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode()

    def fake_opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    result = module.probe_provider(
        module.ProbeConfig(
            base_url="https://provider.example/v1/",
            api_key="secret-test-key",
            model="farm-model",
            timeout_seconds=3.5,
        ),
        opener=fake_opener,
    )

    assert result["ok"] is True
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["timeout"] == 3.5
    assert captured["headers"]["Authorization"] == "Bearer secret-test-key"
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["body"]["model"] == "farm-model"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][1]["role"] == "user"


@pytest.mark.parametrize(
    "response,error",
    [
        ({}, "response missing choices"),
        ({"choices": [{"message": {"content": "not-json"}}]}, "not valid JSON"),
        ({"choices": [{"message": {"content": "[]"}}]}, "must decode to a JSON object"),
        ({"choices": [{"message": {"content": '{"ok": false}'}}]}, '"ok": true'),
    ],
)
def test_parse_chat_completion_response_fails_closed(response, error):
    module = _load_probe_module()

    with pytest.raises(module.ProbeError, match=error):
        module.parse_chat_completion_response(response)


def test_missing_real_provider_env_does_not_leak_cli_secret():
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--api-key",
            "super-secret-key",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "super-secret-key" not in completed.stdout
    assert "super-secret-key" not in completed.stderr
