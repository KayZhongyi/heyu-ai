import json

import httpx
import pytest

from app.ai import (
    AIProviderError,
    DeterministicProvider,
    OpenAICompatibleProvider,
    get_ai_provider,
    validate_campaign_brief_output,
    validate_generation_output,
)
from app.config import Settings
from app.models import Brand, CampaignBriefRevision, ContentProject, ContentType, Product


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


def campaign_brief():
    return CampaignBriefRevision(
        id="brief-1",
        revision_number=2,
        platform="douyin",
        target_audience="Young families",
        objective="Qualified product-page visits",
        tone="Warm and specific",
        core_message="Freshness should be explained with current evidence",
        audience_need="Know what is available now and why it is trustworthy",
        desired_action="Open the product page and check today's specification",
        proof_points=["Current supply snapshot", "Approved origin record"],
        claim_evidence=[],
        mandatory_messages=["State today's specification"],
        prohibited_messages=["Never promise medical benefits"],
        channel_constraints={"hook_seconds": 3, "max_duration_seconds": 30},
        locale="zh-CN",
        extra_requirements="Keep every factual statement traceable",
    )


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
    result = provider.generate_script(*entities(), [], brief=campaign_brief())

    assert result.content["format"] == "short_video_script"
    assert captured["authorization"] == "Bearer secret-test-key"
    assert captured["payload"]["model"] == "example-model"
    task = json.loads(captured["payload"]["messages"][1]["content"])
    assert task["product"]["prohibited_claims"] == ["治疗疾病"]
    assert task["verified_sources"] == []
    assert task["campaign_brief"]["brief_revision_id"] == "brief-1"
    assert task["campaign_brief"]["core_message"] == (
        "Freshness should be explained with current evidence"
    )
    assert task["campaign_brief"]["mandatory_messages"] == ["State today's specification"]
    assert task["campaign_brief"]["claim_evidence"] == []


def test_deterministic_provider_uses_campaign_brief_direction():
    result = DeterministicProvider().generate_script(
        *entities(),
        [],
        brief=campaign_brief(),
    )

    assert result.content["hook"] == "Freshness should be explained with current evidence"
    assert result.content["cta"] == ("Open the product page and check today's specification")
    assert any("Never promise medical benefits" in note for note in result.content["risk_notes"])
    validate_campaign_brief_output(result.content, campaign_brief())


def test_campaign_brief_output_validation_blocks_missing_and_prohibited_copy():
    brief = campaign_brief()
    with pytest.raises(AIProviderError) as missing:
        validate_campaign_brief_output(
            {"format": "social_post", "body": "Only a generic product message."},
            brief,
        )
    assert missing.value.code == "campaign_mandatory_message_missing"

    brief.mandatory_messages = []
    with pytest.raises(AIProviderError) as prohibited:
        validate_campaign_brief_output(
            {
                "format": "social_post",
                "body": "Never promise medical benefits",
            },
            brief,
        )
    assert prohibited.value.code == "campaign_prohibited_message_used"


def test_campaign_brief_output_validation_ignores_prohibition_guidance():
    brief = campaign_brief()
    with pytest.raises(AIProviderError) as missing:
        validate_campaign_brief_output(
            {
                "format": "mobile_shooting_checklist",
                "do_not_capture_or_claim": ["Do not State today's specification"],
            },
            brief,
        )
    assert missing.value.code == "campaign_mandatory_message_missing"

    brief.mandatory_messages = []
    validate_campaign_brief_output(
        {
            "format": "mobile_shooting_checklist",
            "do_not_capture_or_claim": ["Never promise medical benefits"],
        },
        brief,
    )


def test_campaign_brief_output_validation_enforces_duration_limit():
    brief = campaign_brief()
    brief.mandatory_messages = []
    brief.prohibited_messages = []
    validate_campaign_brief_output({"duration_seconds": 30}, brief)
    with pytest.raises(AIProviderError) as duration:
        validate_campaign_brief_output({"duration_seconds": 31}, brief)
    assert duration.value.code == "campaign_duration_exceeded"


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


def valid_mobile_shooting_checklist(source_id: str = "source-1") -> dict:
    return {
        "format": "mobile_shooting_checklist",
        "shooting_goal": "Capture a factual vertical product story.",
        "before_shooting": [
            {
                "task": "Clean the lens and verify the approved product.",
                "required": True,
                "reason": "Keep the footage usable and factual.",
            }
        ],
        "shots": [
            {
                "sequence": sequence,
                "duration_seconds": 5,
                "shot_size": "close-up",
                "orientation": "vertical",
                "subject": "Approved product and packaging",
                "action": "Hold the frame steady.",
                "voiceover_or_text": "Show the approved product name.",
                "evidence_required": "Approved product record",
                "capture_notes": "Leave safe space for captions.",
            }
            for sequence in range(1, 6)
        ],
        "continuity_checks": ["Keep product and lighting positions consistent."],
        "do_not_capture_or_claim": ["Do not invent certifications or outcomes."],
        "citations": [{"source_id": source_id, "label": "Approved fact"}],
        "risk_notes": [],
    }


def test_deterministic_provider_builds_actionable_mobile_shooting_checklist():
    project, brand, product = entities()
    project.content_type = ContentType.mobile_shooting_checklist

    result = DeterministicProvider().generate_script(
        project,
        brand,
        product,
        [],
        brief=campaign_brief(),
    )

    assert result.content["format"] == "mobile_shooting_checklist"
    assert result.content["shots"][0]["orientation"] == "vertical"
    assert [shot["sequence"] for shot in result.content["shots"]] == [1, 2, 3, 4, 5]
    assert "State today's specification" in result.content["shots"][1]["voiceover_or_text"]
    assert (
        result.content["shots"][-1]["voiceover_or_text"]
        == "Open the product page and check today's specification"
    )
    validate_generation_output(
        result.content,
        ContentType.mobile_shooting_checklist,
        {},
    )
    validate_campaign_brief_output(result.content, campaign_brief())


@pytest.mark.parametrize(
    ("locale", "goal_copy", "first_shot_size", "prohibition_copy"),
    [
        ("en", "Film a clear vertical story", "close-up", "Do not use filters"),
        ("zh-HK", "以手機直度拍好", "近鏡", "不得使用濾鏡"),
    ],
)
def test_mobile_shooting_checklist_follows_campaign_locale(
    locale,
    goal_copy,
    first_shot_size,
    prohibition_copy,
):
    project, brand, product = entities()
    project.content_type = ContentType.mobile_shooting_checklist
    brief = campaign_brief()
    brief.locale = locale

    content = (
        DeterministicProvider()
        .generate_script(
            project,
            brand,
            product,
            [],
            brief=brief,
        )
        .content
    )

    assert goal_copy in content["shooting_goal"]
    assert content["shots"][0]["shot_size"] == first_shot_size
    assert content["do_not_capture_or_claim"][0].startswith(prohibition_copy)
    validate_generation_output(content, ContentType.mobile_shooting_checklist, {})
    validate_campaign_brief_output(content, brief)


def test_mobile_shooting_checklist_validation_rejects_non_vertical_or_incomplete_shots():
    non_vertical = valid_mobile_shooting_checklist()
    non_vertical["shots"][0]["orientation"] = "landscape"
    with pytest.raises(AIProviderError) as orientation:
        validate_generation_output(
            non_vertical,
            ContentType.mobile_shooting_checklist,
            {"source-1": "Trusted source"},
        )
    assert orientation.value.code == "provider_invalid_output"

    incomplete = valid_mobile_shooting_checklist()
    incomplete["shots"][0].pop("evidence_required")
    with pytest.raises(AIProviderError) as evidence:
        validate_generation_output(
            incomplete,
            ContentType.mobile_shooting_checklist,
            {"source-1": "Trusted source"},
        )
    assert evidence.value.code == "provider_invalid_output"

    wrong_sequence = valid_mobile_shooting_checklist()
    wrong_sequence["shots"][-1]["sequence"] = 6
    with pytest.raises(AIProviderError) as sequence:
        validate_generation_output(
            wrong_sequence,
            ContentType.mobile_shooting_checklist,
            {"source-1": "Trusted source"},
        )
    assert sequence.value.code == "provider_invalid_output"


def test_generation_output_validation_rejects_missing_fields_and_wrong_format():
    missing_script = valid_short_video_output()
    missing_script.pop("script")
    with pytest.raises(AIProviderError) as missing:
        validate_generation_output(
            missing_script,
            ContentType.short_video_30s,
            {"source-1": "Trusted source"},
        )
    assert missing.value.code == "provider_invalid_output"

    wrong_format = valid_short_video_output()
    wrong_format["format"] = "social_post"
    with pytest.raises(AIProviderError) as wrong:
        validate_generation_output(
            wrong_format,
            ContentType.short_video_30s,
            {"source-1": "Trusted source"},
        )
    assert wrong.value.code == "provider_invalid_output"


def test_generation_output_validation_rejects_unknown_citation_and_wrong_duration():
    with pytest.raises(AIProviderError) as citation:
        validate_generation_output(
            valid_short_video_output("invented-source"),
            ContentType.short_video_30s,
            {"source-1": "Trusted source"},
        )
    assert citation.value.code == "provider_unknown_citation"

    wrong_duration = valid_short_video_output()
    wrong_duration["duration_seconds"] = 60
    with pytest.raises(AIProviderError) as duration:
        validate_generation_output(
            wrong_duration,
            ContentType.short_video_30s,
            {"source-1": "Trusted source"},
        )
    assert duration.value.code == "provider_invalid_output"


def test_generation_output_requires_citation_when_sources_were_selected():
    output = valid_short_video_output()
    output["citations"] = []

    with pytest.raises(AIProviderError) as exc:
        validate_generation_output(
            output,
            ContentType.short_video_30s,
            {"source-1": "Trusted source"},
        )

    assert exc.value.code == "provider_missing_citation"


def test_generation_output_rebuilds_labels_and_deduplicates_citations():
    output = valid_short_video_output()
    output["citations"] = [
        {"source_id": "source-1", "label": "Fabricated label"},
        {"source_id": "source-1", "label": "A second fabricated label"},
    ]

    normalized = validate_generation_output(
        output,
        ContentType.short_video_30s,
        {"source-1": "Server-owned label"},
    )

    assert normalized["citations"] == [{"source_id": "source-1", "label": "Server-owned label"}]


def test_generation_output_allows_empty_citations_when_no_sources_exist():
    output = valid_short_video_output()
    output["citations"] = []

    normalized = validate_generation_output(
        output,
        ContentType.short_video_30s,
        {},
    )

    assert normalized["citations"] == []


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
