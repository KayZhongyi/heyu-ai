import json
import time
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings
from app.models import Brand, ContentProject, ContentType, Product

PROMPT_NAME = "agricultural-content-script"
PROMPT_VERSION = "1.2.0"


@dataclass(frozen=True)
class ContextSource:
    id: str
    title: str
    citation_label: str
    content: str
    content_sha256: str


@dataclass
class GenerationResult:
    content: dict
    latency_ms: int


class AIProvider(Protocol):
    name: str
    model: str

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
    ) -> GenerationResult: ...


class DeterministicProvider:
    """Offline provider for tests and zero-cost demos.

    It is deliberately transparent: this provider composes verified facts rather
    than pretending to be a trained model.
    """

    name = "mock"
    model = "deterministic-v1"

    @staticmethod
    def _common_context(
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
    ) -> tuple[str, str, list[dict], list[str]]:
        facts = [source.content.strip() for source in sources if source.content.strip()]
        fact_text = "；".join(facts[:3]) or "请先补充并审核产品资料"
        selling_points = "、".join(product.selling_points) or "真实产地与产品特色"
        citations = [
            {"source_id": source.id, "label": source.citation_label or source.title}
            for source in sources
        ]
        risk_notes = [f"禁止使用：{claim}" for claim in product.prohibited_claims]
        return fact_text, selling_points, citations, risk_notes

    @staticmethod
    def _video_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
    ) -> dict:
        is_sixty_seconds = project.content_type == ContentType.short_video_60s
        end_second = 60 if is_sixty_seconds else 30
        middle_end = 48 if is_sixty_seconds else 20
        hook = f"你知道来自{product.origin or '产地'}的{product.name}有什么特别吗？"
        body = (
            f"这是{brand.name}带来的{product.name}。"
            f"它的主要特点是{selling_points}。"
            f"根据已审核资料：{fact_text}。"
        )
        if project.objective:
            body += f"这条内容希望帮助大家{project.objective}。"
        if product.price_display:
            body += f"当前展示信息为{product.price_display}。"
        cta = "想了解更多真实生产信息，欢迎在评论区留言。"
        return {
            "format": "short_video_script",
            "duration_seconds": end_second,
            "title_options": [
                f"{product.name}真实产地故事",
                f"{end_second}秒认识{product.name}",
                f"{brand.name}今天带你看好农产",
            ],
            "hook": hook,
            "script": f"{hook}{body}{cta}",
            "shots": [
                {"seconds": "0-3", "visual": "产品与产地快速亮相", "voiceover": hook},
                {
                    "seconds": f"3-{middle_end}",
                    "visual": "产品细节和生产场景",
                    "voiceover": body,
                },
                {
                    "seconds": f"{middle_end}-{end_second}",
                    "visual": "品牌与互动提示",
                    "voiceover": cta,
                },
            ],
            "cta": cta,
        }

    @staticmethod
    def _livestream_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
    ) -> dict:
        greeting = f"欢迎来到{brand.name}直播间，今天带大家认识{product.name}。"
        fact_statement = f"根据已审核资料：{fact_text}。"
        if project.content_type == ContentType.livestream_opening:
            segments = [
                {"stage": "欢迎", "script": greeting},
                {
                    "stage": "价值预告",
                    "script": f"接下来会讲清它的产地、特点和怎么选，核心特点是{selling_points}。",
                },
                {
                    "stage": "互动",
                    "script": "新进来的朋友可以在评论区告诉我，你最关心产地还是储存方法？",
                },
            ]
            format_name = "livestream_opening"
        elif project.content_type == ContentType.livestream_interaction:
            segments = [
                {"stage": "产地提问", "script": f"大家猜一猜，{product.name}来自哪里？"},
                {"stage": "选择提问", "script": f"你更想先听{selling_points}中的哪一点？"},
                {"stage": "顾虑收集", "script": "购买农产品时，你最担心品质、储存还是运输？"},
                {"stage": "事实回应", "script": fact_statement},
            ]
            format_name = "livestream_interaction"
        else:
            segments = [
                {"stage": "产品亮相", "script": greeting},
                {"stage": "核心卖点", "script": f"它值得关注的特点是{selling_points}。"},
                {"stage": "事实依据", "script": fact_statement},
                {
                    "stage": "购买提示",
                    "script": f"规格为{product.specification or '以实际商品页为准'}，"
                    f"储存建议是{product.storage_method or '请按商品说明储存'}。",
                },
                {"stage": "互动收口", "script": "还有哪项产品信息想核实？请留言，我们按资料回答。"},
            ]
            format_name = "livestream_product_pitch"
        return {
            "format": format_name,
            "run_of_show": segments,
            "host_notes": [
                "只陈述已审核事实，不临场扩展功效承诺。",
                "价格、库存和物流以直播时实际页面为准。",
            ],
        }

    @staticmethod
    def _text_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
    ) -> dict:
        if project.content_type == ContentType.comment_reply:
            return {
                "format": "comment_reply",
                "reply_options": [
                    f"谢谢关注。{product.name}的主要特点是{selling_points}，相关信息来自已审核产品资料。",
                    f"关于您关心的产品信息，目前可确认的是：{fact_text}。",
                    "如果想了解规格、储存或发货信息，请告诉我们具体问题，我们会按资料核实。",
                ],
            }
        if project.content_type == ContentType.title_and_cover:
            return {
                "format": "title_and_cover",
                "title_options": [
                    f"从产地认识{product.name}",
                    f"{brand.name}为什么选择{product.name}",
                    f"{product.name}选购前先看这份事实卡",
                ],
                "cover_copy_options": [
                    f"真实产地 · {product.name}",
                    "先看事实，再选农产",
                    f"{selling_points}",
                ],
            }
        return {
            "format": "social_post",
            "headline": f"今天认真介绍一份来自{product.origin or '真实产地'}的{product.name}",
            "body": (
                f"{brand.name}希望把产品信息讲清楚：它的主要特点是{selling_points}。"
                f"根据已审核资料，{fact_text}。"
            ),
            "cta": "你还想了解哪项产品信息？欢迎留言，我们会继续补充可核实的答案。",
            "hashtags": [f"#{product.name}", "#农产品", "#产地故事"],
        }

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
    ) -> GenerationResult:
        started = time.perf_counter()
        fact_text, selling_points, citations, risk_notes = self._common_context(
            brand, product, sources
        )
        if project.content_type in {
            ContentType.short_video_30s,
            ContentType.short_video_60s,
        }:
            content = self._video_content(project, brand, product, fact_text, selling_points)
        elif project.content_type in {
            ContentType.livestream_opening,
            ContentType.livestream_product_pitch,
            ContentType.livestream_interaction,
        }:
            content = self._livestream_content(project, brand, product, fact_text, selling_points)
        else:
            content = self._text_content(project, brand, product, fact_text, selling_points)
        content["risk_notes"] = risk_notes
        content["citations"] = citations
        return GenerationResult(
            content=content,
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
        )


class AIProviderError(RuntimeError):
    """A safe, credential-free error raised when an external provider fails."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


class _StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citations: list["_Citation"]
    risk_notes: list[str]


class _Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    label: str


class _Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seconds: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    voiceover: str = Field(min_length=1)


class _ShortVideoOutput(_StrictOutput):
    format: Literal["short_video_script"]
    duration_seconds: int
    title_options: list[str] = Field(min_length=1)
    hook: str = Field(min_length=1)
    script: str = Field(min_length=1)
    shots: list[_Shot] = Field(min_length=1)
    cta: str = Field(min_length=1)


class _RunOfShowItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(min_length=1)
    script: str = Field(min_length=1)


class _LivestreamOutput(_StrictOutput):
    format: Literal[
        "livestream_opening",
        "livestream_product_pitch",
        "livestream_interaction",
    ]
    run_of_show: list[_RunOfShowItem] = Field(min_length=1)
    host_notes: list[str] = Field(min_length=1)


class _CommentReplyOutput(_StrictOutput):
    format: Literal["comment_reply"]
    reply_options: list[str] = Field(min_length=1)


class _SocialPostOutput(_StrictOutput):
    format: Literal["social_post"]
    headline: str = Field(min_length=1)
    body: str = Field(min_length=1)
    cta: str = Field(min_length=1)
    hashtags: list[str]


class _TitleAndCoverOutput(_StrictOutput):
    format: Literal["title_and_cover"]
    title_options: list[str] = Field(min_length=1)
    cover_copy_options: list[str] = Field(min_length=1)


_OUTPUT_MODELS: dict[ContentType, type[_StrictOutput]] = {
    ContentType.short_video_30s: _ShortVideoOutput,
    ContentType.short_video_60s: _ShortVideoOutput,
    ContentType.livestream_opening: _LivestreamOutput,
    ContentType.livestream_product_pitch: _LivestreamOutput,
    ContentType.livestream_interaction: _LivestreamOutput,
    ContentType.comment_reply: _CommentReplyOutput,
    ContentType.social_post: _SocialPostOutput,
    ContentType.title_and_cover: _TitleAndCoverOutput,
}

_EXPECTED_FORMATS = {
    ContentType.short_video_30s: "short_video_script",
    ContentType.short_video_60s: "short_video_script",
    ContentType.livestream_opening: "livestream_opening",
    ContentType.livestream_product_pitch: "livestream_product_pitch",
    ContentType.livestream_interaction: "livestream_interaction",
    ContentType.comment_reply: "comment_reply",
    ContentType.social_post: "social_post",
    ContentType.title_and_cover: "title_and_cover",
}


def validate_generation_output(
    content: object,
    content_type: ContentType,
    allowed_source_ids: set[str],
) -> dict:
    """Validate provider output before it can become a durable content version."""

    if not isinstance(content, dict):
        raise AIProviderError(
            "The configured AI provider returned a non-object response",
            code="provider_invalid_output",
        )
    if content.get("format") != _EXPECTED_FORMATS[content_type]:
        raise AIProviderError(
            "The configured AI provider returned the wrong content format",
            code="provider_invalid_output",
        )
    try:
        validated = _OUTPUT_MODELS[content_type].model_validate(content)
    except ValidationError:
        raise AIProviderError(
            "The configured AI provider returned content that failed validation",
            code="provider_invalid_output",
        ) from None

    normalized = validated.model_dump(mode="json")
    if content_type == ContentType.short_video_30s and normalized["duration_seconds"] != 30:
        raise AIProviderError(
            "The configured AI provider returned the wrong video duration",
            code="provider_invalid_output",
        )
    if content_type == ContentType.short_video_60s and normalized["duration_seconds"] != 60:
        raise AIProviderError(
            "The configured AI provider returned the wrong video duration",
            code="provider_invalid_output",
        )

    cited_source_ids = {citation["source_id"] for citation in normalized["citations"]}
    if not cited_source_ids.issubset(allowed_source_ids):
        raise AIProviderError(
            "The configured AI provider cited an unavailable knowledge source",
            code="provider_unknown_citation",
        )
    return normalized


class OpenAICompatibleProvider:
    """Adapter for servers implementing the OpenAI chat-completions contract."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 45,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @staticmethod
    def _payload(
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
    ) -> dict:
        verified_sources = [
            {
                "source_id": source.id,
                "label": source.citation_label or source.title,
                "content": source.content,
            }
            for source in sources
        ]
        task = {
            "content_type": project.content_type.value,
            "platform": project.platform,
            "target_audience": project.target_audience,
            "objective": project.objective,
            "tone": project.tone,
            "extra_requirements": project.extra_requirements,
            "brand": {"name": brand.name, "story": brand.story, "voice": brand.voice},
            "product": {
                "name": product.name,
                "origin": product.origin,
                "specification": product.specification,
                "price_display": product.price_display,
                "storage_method": product.storage_method,
                "selling_points": product.selling_points,
                "prohibited_claims": product.prohibited_claims,
            },
            "verified_sources": verified_sources,
        }
        return {
            "model": "",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You create factual agricultural marketing content. Return one JSON "
                        "object only. Use only verified_sources for factual claims. Never invent "
                        "certifications, efficacy, prices, yields, or customer outcomes. Preserve "
                        "source provenance in a citations array containing source_id and label. "
                        "Include a risk_notes array. Match the requested content_type."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(task, ensure_ascii=False),
                },
            ],
        }

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
    ) -> GenerationResult:
        started = time.perf_counter()
        payload = self._payload(project, brand, product, sources)
        payload["model"] = self.model
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            content = json.loads(raw_content)
        except httpx.TimeoutException:
            raise AIProviderError(
                "The configured AI provider timed out",
                code="provider_timeout",
            ) from None
        except httpx.HTTPStatusError:
            raise AIProviderError(
                "The configured AI provider request failed",
                code="provider_http_error",
            ) from None
        except httpx.HTTPError:
            raise AIProviderError(
                "The configured AI provider could not be reached",
                code="provider_connection_error",
            ) from None
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise AIProviderError(
                "The configured AI provider did not return valid structured content",
                code="provider_invalid_response",
            ) from None
        if not isinstance(content, dict):
            raise AIProviderError(
                "The configured AI provider returned a non-object response",
                code="provider_invalid_response",
            )
        return GenerationResult(
            content=content,
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
        )


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    settings = settings or get_settings()
    if settings.ai_provider.strip().lower() == "openai-compatible":
        return OpenAICompatibleProvider(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    return DeterministicProvider()
