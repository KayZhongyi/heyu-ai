import json

import httpx
import pytest

from app.ai import AIProviderError, DeterministicProvider, OpenAICompatibleProvider, get_ai_provider
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
