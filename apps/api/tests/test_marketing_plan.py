import json
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import marketing
from app.config import Settings
from app.marketing import (
    DeterministicMarketingProvider,
    MarketingPlanRequest,
    MarketingPlanResponse,
    MarketingProviderError,
    OpenAICompatibleMarketingProvider,
)


def sample_request(**overrides) -> MarketingPlanRequest:
    data = {
        "locale": "zh-CN",
        "persona": "farmer",
        "goals": ["sell", "build-brand"],
        "product_name": "当季番茄",
        "origin": "广东清远",
        "product_description": "自然成熟后采摘，适合家庭鲜食与做菜。",
        "selling_points": ["自然成熟", "清甜多汁", "当天采摘"],
        "platform": "douyin",
        "tone": "plain",
    }
    data.update(overrides)
    return MarketingPlanRequest.model_validate(data)


def assert_no_corrupted_text(result: MarketingPlanResponse) -> None:
    serialized = json.dumps(result.model_dump(), ensure_ascii=False)
    assert "\ufffd" not in serialized
    assert re.search(r"\?{2,}", serialized) is None
    for fragment in ("锟斤拷", "鐨勌", "銆", "鈥", "鏂版", "瑙嗛", "浜у"):
        assert fragment not in serialized


def test_deterministic_plan_is_complete():
    result = DeterministicMarketingProvider().generate(sample_request())

    assert result.provider == "mock"
    assert result.product_profile.core_selling_points == ["自然成熟", "清甜多汁", "当天采摘"]
    assert len(result.videos) == 3
    assert len(result.seven_day_plan) == 7
    assert all(len(video.shots) >= 3 for video in result.videos)
    assert len({video.angle for video in result.videos}) == 3
    assert_no_corrupted_text(result)


@pytest.mark.parametrize(
    ("locale", "product_name", "description", "selling_points", "platform"),
    [
        (
            "zh-CN",
            "当季番茄",
            "自然成熟后采摘，适合家庭鲜食与做菜。",
            ["自然成熟", "清甜多汁", "当天采摘"],
            "douyin",
        ),
        (
            "zh-HK",
            "高山單叢茶",
            "春季採摘並完成傳統工序，香氣清晰，適合日常沖泡。",
            ["春季採摘", "傳統工序", "香氣清晰"],
            "xiaohongshu",
        ),
        (
            "zh-CN",
            "水果礼盒",
            "按成熟度分选后装箱，适合节日探访与家庭分享。",
            ["多种水果搭配", "分级装箱", "适合分享"],
            "wechat-channels",
        ),
    ],
)
def test_marketing_intelligence_covers_required_product_platform_pairs(
    locale,
    product_name,
    description,
    selling_points,
    platform,
):
    result = DeterministicMarketingProvider().generate(
        sample_request(
            locale=locale,
            product_name=product_name,
            product_description=description,
            selling_points=selling_points,
            platform=platform,
        )
    )

    assert [route.route_id for route in result.creative_routes] == [
        "practical-hook",
        "people-story",
        "playful-contrast",
    ]
    assert [video.route_id for video in result.videos] == [
        route.route_id for route in result.creative_routes
    ]
    assert len({route.name for route in result.creative_routes}) == 3
    assert [signal.signal_type for signal in result.topic_signals] == [
        "manual-hotspot",
        "seasonal-farming",
        "evergreen-pain-point",
    ]
    assert {signal.recommendation for signal in result.topic_signals}.issubset(
        {"recommended", "consider", "skip"}
    )
    for signal in result.topic_signals:
        dimension_scores = signal.fit_scores.model_dump()
        assert set(dimension_scores) == {
            "product",
            "audience",
            "platform",
            "timeliness",
            "filmability",
            "source",
        }
        assert signal.total_score == round(
            sum(item["score"] for item in dimension_scores.values()) / 6
        )
        assert signal.source_note
        assert signal.explanation

    for video in result.videos:
        assessment = video.quality_assessment
        assert assessment.total_score == round(sum(assessment.scores.model_dump().values()) / 6)
        assert len(assessment.strengths) >= 2
        assert assessment.improvements

    assert result.next_step.current_stage == "select-route"
    assert [stage.stage for stage in result.next_step.stages] == [
        "select-route",
        "prepare-shoot",
        "record-publication",
    ]
    assert product_name in result.next_step.primary_action
    assert_no_corrupted_text(result)


def test_plan_supports_three_product_categories():
    provider = DeterministicMarketingProvider()
    products = [
        ("当季番茄", "自然成熟后采摘，适合家庭鲜食与做菜。"),
        ("高山单丛茶", "春季采摘并完成传统工序，香气清晰。"),
        ("岭南荔枝", "当季采收，果肉饱满，适合家庭分享。"),
    ]

    for product_name, description in products:
        result = provider.generate(
            sample_request(product_name=product_name, product_description=description)
        )
        assert product_name in result.product_profile.one_line_value
        assert len(result.videos) == 3


def test_plan_supports_three_locales():
    provider = DeterministicMarketingProvider()

    zh_cn = provider.generate(sample_request(locale="zh-CN"))
    zh_hk = provider.generate(sample_request(locale="zh-HK"))
    en = provider.generate(
        sample_request(
            locale="en",
            product_name="Seasonal tomatoes",
            origin="Qingyuan, Guangdong",
            product_description="Picked after natural ripening for everyday family meals.",
            selling_points=["naturally ripened", "juicy", "picked today"],
        )
    )

    assert zh_cn.strategy.platform_name == "抖音"
    assert zh_hk.strategy.platform_name == "抖音"
    assert en.strategy.platform_name == "Douyin"
    assert "來自" in zh_hk.product_profile.one_line_value
    assert zh_hk.product_profile.core_selling_points == [
        "自然成熟",
        "清甜多汁",
        "当天采摘",
    ]
    assert "广东清远" in zh_hk.product_profile.one_line_value
    assert "Seasonal tomatoes" in en.product_profile.one_line_value
    assert [route.name for route in zh_cn.creative_routes] == [
        "实用吸睛",
        "人物故事",
        "轻松反差",
    ]
    assert [route.name for route in zh_hk.creative_routes] == [
        "實用吸睛",
        "人物故事",
        "輕鬆反差",
    ]
    zh_hk_text = json.dumps(zh_hk.model_dump(), ensure_ascii=False)
    assert "不一样" not in zh_hk_text
    assert zh_hk.videos[2].title.endswith("下一鏡不一樣")
    assert [route.name for route in en.creative_routes] == [
        "Practical hook",
        "People story",
        "Playful contrast",
    ]
    for result in (zh_cn, zh_hk, en):
        assert_no_corrupted_text(result)


def test_request_deduplicates_goals_and_rejects_high_risk_claims():
    request = sample_request(goals=["sell", "sell", "build-brand"])
    assert request.goals == ["sell", "build-brand"]

    with pytest.raises(ValidationError, match="high-risk"):
        sample_request(selling_points=["当天采摘", "降血糖"])


def test_response_requires_ordered_days_and_distinct_videos():
    valid = DeterministicMarketingProvider().generate(sample_request()).model_dump()
    valid["seven_day_plan"][1]["day"] = 1
    with pytest.raises(ValidationError, match="ordered days"):
        MarketingPlanResponse.model_validate(valid)

    valid = DeterministicMarketingProvider().generate(sample_request()).model_dump()
    valid["videos"][1]["angle"] = valid["videos"][0]["angle"]
    with pytest.raises(ValidationError, match="distinct"):
        MarketingPlanResponse.model_validate(valid)


def test_public_preview_endpoint_needs_no_account(client: TestClient):
    response = client.post("/v1/marketing/preview", json=sample_request().model_dump())

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert len(body["videos"]) == 3
    assert len(body["seven_day_plan"]) == 7


def test_configured_generation_endpoint_requires_account(client: TestClient):
    response = client.post("/v1/marketing/generate", json=sample_request().model_dump())

    assert response.status_code in {401, 403}


def test_configured_generation_reuses_bounded_cache(monkeypatch):
    class CountingProvider:
        name = "counting-provider"
        model = "counting-model"

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            return DeterministicMarketingProvider().generate(request)

    provider = CountingProvider()
    settings = type(
        "SettingsStub",
        (),
        {
            "marketing_cache_ttl_seconds": 60,
            "marketing_cache_max_entries": 8,
            "marketing_fallback_to_mock": True,
        },
    )()
    marketing._marketing_cache.clear()
    monkeypatch.setattr(marketing, "get_settings", lambda: settings)
    monkeypatch.setattr(marketing, "get_marketing_provider", lambda _: provider)

    first = marketing.generate_marketing_plan(sample_request())
    second = marketing.generate_marketing_plan(sample_request())

    assert provider.calls == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.product_profile == first.product_profile


def test_configured_generation_degrades_to_mock(monkeypatch):
    class FailingProvider:
        name = "unavailable-provider"
        model = "unavailable-model"

        def generate(self, request):
            raise MarketingProviderError("provider unavailable")

    settings = type(
        "SettingsStub",
        (),
        {
            "marketing_cache_ttl_seconds": 60,
            "marketing_cache_max_entries": 8,
            "marketing_fallback_to_mock": True,
        },
    )()
    marketing._marketing_cache.clear()
    monkeypatch.setattr(marketing, "get_settings", lambda: settings)
    monkeypatch.setattr(marketing, "get_marketing_provider", lambda _: FailingProvider())

    result = marketing.generate_marketing_plan(sample_request())

    assert result.provider == "mock-fallback"
    assert result.degraded is True
    assert result.notice
    assert len(result.videos) == 3


def _openai_settings(**overrides) -> Settings:
    values: dict[str, Any] = {
        "ai_provider": "openai-compatible",
        "ai_base_url": "https://model.example/v1",
        "ai_model": "domestic-model",
        "ai_api_key": "test-only-key",
    }
    values.update(overrides)
    return Settings(**values)


class _FakeResponse:
    def __init__(self, body, *, status_code=200):
        self.body = body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise marketing.httpx.HTTPStatusError(
                "provider failed",
                request=marketing.httpx.Request("POST", "https://model.example"),
                response=marketing.httpx.Response(self.status_code),
            )

    def json(self):
        return self.body


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "[]"}}]},
        {"choices": [{"message": {"content": "not-json"}}]},
    ],
)
def test_openai_compatible_provider_normalizes_invalid_contracts(monkeypatch, body):
    monkeypatch.setattr(
        marketing.httpx,
        "post",
        lambda *args, **kwargs: _FakeResponse(body),
    )
    provider = OpenAICompatibleMarketingProvider(_openai_settings())

    with pytest.raises(MarketingProviderError):
        provider.generate(sample_request())


def test_openai_compatible_provider_accepts_fenced_json(monkeypatch):
    source = DeterministicMarketingProvider().generate(sample_request()).model_dump()
    body = {
        "choices": [
            {"message": {"content": "```json\n" + json.dumps(source, ensure_ascii=False) + "\n```"}}
        ]
    }
    monkeypatch.setattr(
        marketing.httpx,
        "post",
        lambda *args, **kwargs: _FakeResponse(body),
    )
    result = OpenAICompatibleMarketingProvider(_openai_settings()).generate(sample_request())

    assert result.provider == "openai-compatible"
    assert result.model == "domestic-model"
    assert len(result.videos) == 3
    assert len(result.creative_routes) == 3
    assert len(result.topic_signals) == 3


def test_openai_compatible_provider_rejects_legacy_response_without_intelligence(monkeypatch):
    source = DeterministicMarketingProvider().generate(sample_request()).model_dump()
    source.pop("creative_routes")
    body = {"choices": [{"message": {"content": json.dumps(source, ensure_ascii=False)}}]}
    monkeypatch.setattr(
        marketing.httpx,
        "post",
        lambda *args, **kwargs: _FakeResponse(body),
    )

    with pytest.raises(MarketingProviderError):
        OpenAICompatibleMarketingProvider(_openai_settings()).generate(sample_request())


def test_degraded_result_is_not_cached_after_provider_recovers(monkeypatch):
    class RecoveringProvider:
        name = "recovering-provider"
        model = "recovering-model"

        def __init__(self):
            self.calls = 0

        def generate(self, request):
            self.calls += 1
            if self.calls == 1:
                raise MarketingProviderError("temporary outage")
            result = DeterministicMarketingProvider().generate(request)
            result.provider = self.name
            result.model = self.model
            return result

    provider = RecoveringProvider()
    settings = type(
        "SettingsStub",
        (),
        {
            "marketing_cache_ttl_seconds": 60,
            "marketing_cache_max_entries": 8,
            "marketing_fallback_to_mock": True,
        },
    )()
    marketing._marketing_cache.clear()
    monkeypatch.setattr(marketing, "get_settings", lambda: settings)
    monkeypatch.setattr(marketing, "get_marketing_provider", lambda _: provider)

    first = marketing.generate_marketing_plan(sample_request())
    second = marketing.generate_marketing_plan(sample_request())

    assert first.degraded is True
    assert second.degraded is False
    assert second.provider == "recovering-provider"
    assert provider.calls == 2
