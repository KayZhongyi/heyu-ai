"""Probe an OpenAI-compatible chat-completions provider contract.

This script is intentionally small and dependency-free so it can run in a local
zero-cost checkout before any real model is configured. It verifies the wire
contract used by 禾语 AI's replaceable model adapter without printing secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_MODEL = "heyu-provider-probe"
DEFAULT_TIMEOUT_SECONDS = 20.0


class ProbeError(RuntimeError):
    """Raised when the provider contract is not satisfied."""


@dataclass(frozen=True)
class ProbeConfig:
    base_url: str
    api_key: str
    model: str = DEFAULT_MODEL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def build_probe_payload(model: str) -> dict[str, Any]:
    """Build the minimal chat-completions request expected by the adapter."""

    return {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a contract probe for an agriculture content-production "
                    "platform. Return only one JSON object."
                ),
            },
            {
                "role": "user",
                "content": (
                    'Return {"ok": true, "provider_contract": '
                    '"openai-compatible", "supports_json_object": true}.'
                ),
            },
        ],
    }


def parse_chat_completion_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract and validate JSON-object content from a chat-completions response."""

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProbeError("response missing choices[0].message.content") from exc
    if not isinstance(content, str):
        raise ProbeError("choices[0].message.content must be a JSON string")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProbeError("choices[0].message.content is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProbeError("choices[0].message.content must decode to a JSON object")
    if parsed.get("ok") is not True:
        raise ProbeError('decoded JSON object must contain "ok": true')
    return parsed


def _request_json(
    endpoint: str,
    payload: dict[str, Any],
    api_key: str,
    timeout_seconds: float,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise ProbeError(f"provider returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason.__class__.__name__
        raise ProbeError(f"provider connection failed: {reason}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError("provider response body is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ProbeError("provider response body must be a JSON object")
    return data


def probe_provider(
    config: ProbeConfig,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    endpoint = config.base_url.rstrip("/") + "/chat/completions"
    payload = build_probe_payload(config.model)
    response = _request_json(
        endpoint,
        payload,
        config.api_key,
        config.timeout_seconds,
        opener=opener,
    )
    return parse_chat_completion_response(response)


def run_mock_probe() -> dict[str, Any]:
    """Run the parser against an in-process fixture; no network or secret needed."""

    fixture = {
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
    return parse_chat_completion_response(fixture)


def _config_from_env(args: argparse.Namespace) -> ProbeConfig:
    base_url = args.base_url or os.getenv("AI_BASE_URL")
    api_key = args.api_key or os.getenv("AI_API_KEY")
    model = args.model or os.getenv("AI_MODEL") or DEFAULT_MODEL
    timeout_seconds = args.timeout or float(os.getenv("AI_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    if not base_url:
        raise ProbeError("AI_BASE_URL is required unless --mock is used")
    if not api_key:
        raise ProbeError("AI_API_KEY is required unless --mock is used")
    return ProbeConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the minimal OpenAI-compatible /chat/completions JSON-object "
            "contract used by Heyu AI."
        )
    )
    parser.add_argument("--mock", action="store_true", help="run an offline parser self-test")
    parser.add_argument("--base-url", help="provider base URL, for example https://host/v1")
    parser.add_argument("--api-key", help="provider API key; prefer AI_API_KEY env var")
    parser.add_argument("--model", help="model name; defaults to AI_MODEL or a probe name")
    parser.add_argument("--timeout", type=float, help="request timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    started = time.perf_counter()
    try:
        if args.mock:
            result = run_mock_probe()
            mode = "mock"
        else:
            result = probe_provider(_config_from_env(args))
            mode = "provider"
    except ProbeError as exc:
        print(f"Probe failed: {exc}", file=sys.stderr)
        return 1
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    safe_result = {
        "mode": mode,
        "ok": True,
        "elapsed_ms": elapsed_ms,
        "provider_contract": result.get("provider_contract"),
        "supports_json_object": result.get("supports_json_object"),
    }
    print(json.dumps(safe_result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
