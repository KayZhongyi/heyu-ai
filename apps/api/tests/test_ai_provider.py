import json

import httpx
import pytest

from app.ai import (
    AIProviderError,
    DeterministicProvider,
    OpenAICompatibleProvider,
    get_ai_provider,
    validate_generation_output,
)
from app.config import Settings
from app.models import Brand, ContentProject, ContentType, Product


def entities():
    project = ContentProject(
        content_type=ContentType.short_video_30s,
        platform="抖音",
        target_audience="家庭用户",
        objective="了解产品",
        tone="真诚",
        extra_requirements="不夸大",
    )
    brand = Brand(name="测试品牌", story="真实产地", voice="朴实")
    product = Product(
        name="测试番茄",
        origin="云南",
        specification="500g",
        price_display="",
        storage_method="冷藏",
        selling_points=["自然成熟"],
        prohibited_claims=["治疗疾病"],
    )
    return project, brand, product


def test_provider_factory_keeps_zero_cost_default():
    provider = get_ai_provider(Settings(ai_provider="mock", ai_model="deterministic-v1"))
    assert isinstance(provider, DeterministicProvider)


def test_openai_compatible_provider_sends_structured_grounded_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "format": "short_video_script",
                                    "script": "只使用已审核事实。",
                                    "citations": [],
                                    "risk_notes": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="secret-test-key",
        model="example-model",
        transport=httpx.MockTransport(handler),
    )
    result = provider.generate_script(*entities(), [])

    assert result.content["format"] == "short_video_script"
    assert captured["authorization"] == "Bearer secret-test-key"
    assert captured["payload"]["model"] == "example-model"
    task = json.loads(captured["payload"]["messages"][1]["content"])
    assert task["product"]["prohibited_claims"] == ["治疗疾病"]
    assert task["verified_sources"] == []


def test_openai_compatible_provider_rejects_invalid_response_without_leaking_key():
    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="do-not-leak-this-key",
        model="example-model",
        transport=httpx.MockTransport(lambda request: httpx.Response(500, text="failure")),
    )

    with pytest.raises(AIProviderError) as exc:
        provider.generate_script(*entities(), [])

    assert "do-not-leak-this-key" not in str(exc.value)
    assert exc.value.code == "provider_http_error"


def valid_short_video_output(source_id: str = "source-1") -> dict:
    return {
        "format": "short_video_script",
        "duration_seconds": 30,
        "title_options": ["A factual title"],
        "hook": "A factual opening.",
        "script": "A factual script.",
        "shots": [
            {
                "seconds": "0-30",
                "visual": "Show the product.",
                "voiceover": "Describe the approved fact.",
            }
        ],
        "cta": "Read the verified product details.",
        "citations": [{"source_id": source_id, "label": "Approved fact"}],
        "risk_notes": [],
    }


def test_generation_output_validation_rejects_missing_fields_and_wrong_format():
    missing_script = valid_short_video_output()
    missing_script.pop("script")
    with pytest.raises(AIProviderError) as missing:
        validate_generation_output(
            missing_script,
            ContentType.short_video_30s,
            {"source-1"},
        )
    assert missing.value.code == "provider_invalid_output"

    wrong_format = valid_short_video_output()
    wrong_format["format"] = "social_post"
    with pytest.raises(AIProviderError) as wrong:
        validate_generation_output(
            wrong_format,
            ContentType.short_video_30s,
            {"source-1"},
        )
    assert wrong.value.code == "provider_invalid_output"


def test_generation_output_validation_rejects_unknown_citation_and_wrong_duration():
    with pytest.raises(AIProviderError) as citation:
        validate_generation_output(
            valid_short_video_output("invented-source"),
            ContentType.short_video_30s,
            {"source-1"},
        )
    assert citation.value.code == "provider_unknown_citation"

    wrong_duration = valid_short_video_output()
    wrong_duration["duration_seconds"] = 60
    with pytest.raises(AIProviderError) as duration:
        validate_generation_output(
            wrong_duration,
            ContentType.short_video_30s,
            {"source-1"},
        )
    assert duration.value.code == "provider_invalid_output"


def test_openai_compatible_provider_does_not_fill_missing_provenance_arrays():
    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="test-key",
        model="example-model",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "format": "social_post",
                                        "headline": "Headline",
                                        "body": "Body",
                                        "cta": "CTA",
                                        "hashtags": [],
                                    }
                                )
                            }
                        }
                    ]
                },
            )
        ),
    )

    result = provider.generate_script(*entities(), [])
    assert "citations" not in result.content
    assert "risk_notes" not in result.content


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        (httpx.Response(200, text="not-json"), "provider_invalid_response"),
        (
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(["not", "an", "object"])}}]},
            ),
            "provider_invalid_response",
        ),
    ],
)
def test_openai_compatible_provider_classifies_malformed_responses(response, expected_code):
    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="test-key",
        model="example-model",
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(AIProviderError) as exc:
        provider.generate_script(*entities(), [])

    assert exc.value.code == expected_code


def test_openai_compatible_provider_classifies_timeout():
    def timeout(request):
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OpenAICompatibleProvider(
        base_url="https://model.example/v1",
        api_key="test-key",
        model="example-model",
        transport=httpx.MockTransport(timeout),
    )

    with pytest.raises(AIProviderError) as exc:
        provider.generate_script(*entities(), [])

    assert exc.value.code == "provider_timeout"
