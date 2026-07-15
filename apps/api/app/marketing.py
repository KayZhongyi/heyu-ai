# ruff: noqa: E501
"""Farmer-first marketing plan generation.

This module is intentionally independent from the governance-heavy content
workflow in ``ai.py``.  It powers the simple creation experience while keeping
the existing workspace available for teams that need review, versioning and
publishing controls.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import Settings, get_settings

Locale = Literal["zh-CN", "zh-HK", "en"]
Platform = Literal["douyin", "xiaohongshu", "wechat-channels", "kuaishou"]
CreativeRouteId = Literal["practical-hook", "people-story", "playful-contrast"]
TopicSignalType = Literal["manual-hotspot", "seasonal-farming", "evergreen-pain-point"]
Recommendation = Literal["recommended", "consider", "skip"]
Goal = Literal[
    "sell",
    "build-brand",
    "gain-followers",
    "promote-tourism",
    "recruit-agents",
]


def _default_goals() -> list[Goal]:
    return ["sell"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


SellingPoint = Annotated[str, Field(min_length=1, max_length=80)]

HIGH_RISK_CLAIM_PATTERNS = (
    re.compile(
        r"(降血糖|降血压|治疗|治愈|防癌|抗癌|包治|国家(?:级)?认证|销量第一|全网第一|"
        r"百分之百有效|100\s*%\s*有效)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(cure[sd]?|treats?|anti-cancer|prevents? cancer|lowers? blood sugar|"
        r"nationally certified|best[- ]selling|number one|100\s*%\s*effective)\b",
        re.IGNORECASE,
    ),
)


class MarketingPlanRequest(StrictModel):
    locale: Locale = "zh-CN"
    persona: Literal["farmer", "cooperative", "rural-operator"] = "farmer"
    goals: list[Goal] = Field(default_factory=_default_goals, min_length=1, max_length=3)
    product_name: str = Field(min_length=1, max_length=80)
    origin: str = Field(default="", max_length=120)
    product_description: str = Field(min_length=4, max_length=1200)
    selling_points: list[SellingPoint] = Field(default_factory=list, max_length=8)
    audience: str = Field(default="", max_length=160)
    platform: Platform = "douyin"
    tone: Literal["plain", "warm", "lively", "premium"] = "plain"
    trend: str = Field(default="", max_length=240)

    @model_validator(mode="after")
    def normalize_and_reject_high_risk_claims(self) -> MarketingPlanRequest:
        self.goals = list(dict.fromkeys(self.goals))
        self.selling_points = [point.strip() for point in self.selling_points if point.strip()]
        source_text = "\n".join((self.product_description, *self.selling_points))
        if any(pattern.search(source_text) for pattern in HIGH_RISK_CLAIM_PATTERNS):
            raise ValueError(
                "Product claims include a high-risk medical, certification, or absolute "
                "marketing statement. Remove it or verify it in the professional workspace."
            )
        return self


class ProductProfile(StrictModel):
    one_line_value: str
    core_audience: str
    core_selling_points: list[str] = Field(min_length=3, max_length=5)
    story_angle: str


class PlatformStrategy(StrictModel):
    platform: Platform
    platform_name: str
    content_focus: str
    recommended_duration: str
    conversion_action: str


class TrendBrief(StrictModel):
    trend_used: str
    integration_method: str
    caution: str


class CreativeRoute(StrictModel):
    route_id: CreativeRouteId
    name: str
    positioning: str
    best_for: str
    signature_hook: str
    selection_reason: str


class TopicFitDimension(StrictModel):
    score: int = Field(ge=0, le=100)
    rationale: str


class TopicFitScores(StrictModel):
    product: TopicFitDimension
    audience: TopicFitDimension
    platform: TopicFitDimension
    timeliness: TopicFitDimension
    filmability: TopicFitDimension
    source: TopicFitDimension

    def average(self) -> int:
        values = (
            self.product.score,
            self.audience.score,
            self.platform.score,
            self.timeliness.score,
            self.filmability.score,
            self.source.score,
        )
        return round(sum(values) / len(values))


class TopicSignal(StrictModel):
    signal_type: TopicSignalType
    title: str
    content_angle: str
    source_label: str
    source_note: str
    fit_scores: TopicFitScores
    total_score: int = Field(ge=0, le=100)
    recommendation: Recommendation
    explanation: str
    usage_caution: str

    @model_validator(mode="after")
    def validate_score_and_recommendation(self) -> TopicSignal:
        expected_score = self.fit_scores.average()
        if self.total_score != expected_score:
            raise ValueError("topic signal total_score must equal the rounded dimension average")
        expected_recommendation: Recommendation
        if expected_score >= 75:
            expected_recommendation = "recommended"
        elif expected_score >= 55:
            expected_recommendation = "consider"
        else:
            expected_recommendation = "skip"
        if self.recommendation != expected_recommendation:
            raise ValueError("topic signal recommendation does not match total_score")
        return self


class Shot(StrictModel):
    seconds: str
    visual: str
    voiceover: str
    filming_tip: str


class VideoQualityScores(StrictModel):
    hook: int = Field(ge=0, le=100)
    factual_grounding: int = Field(ge=0, le=100)
    platform_fit: int = Field(ge=0, le=100)
    filmability: int = Field(ge=0, le=100)
    interaction: int = Field(ge=0, le=100)
    compliance: int = Field(ge=0, le=100)

    def average(self) -> int:
        values = (
            self.hook,
            self.factual_grounding,
            self.platform_fit,
            self.filmability,
            self.interaction,
            self.compliance,
        )
        return round(sum(values) / len(values))


class VideoQualityAssessment(StrictModel):
    scores: VideoQualityScores
    total_score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(min_length=2, max_length=4)
    improvements: list[str] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_total_score(self) -> VideoQualityAssessment:
        if self.total_score != self.scores.average():
            raise ValueError("video quality total_score must equal the rounded dimension average")
        return self


class VideoScript(StrictModel):
    route_id: CreativeRouteId
    angle: str
    title: str
    cover_text: str
    hook: str
    script: str
    background_music: str
    shots: list[Shot] = Field(min_length=3, max_length=6)
    call_to_action: str
    quality_assessment: VideoQualityAssessment


class LivestreamSection(StrictModel):
    section: str
    talking_points: list[str]


class DailyPlan(StrictModel):
    day: int = Field(ge=1, le=7)
    objective: str
    content: str
    action: str


class NextStepStage(StrictModel):
    stage: Literal["select-route", "prepare-shoot", "record-publication"]
    status: Literal["current", "upcoming"]
    instruction: str
    completion_signal: str


class NextStep(StrictModel):
    current_stage: Literal["select-route"]
    title: str
    primary_action: str
    route_ids: list[CreativeRouteId] = Field(min_length=3, max_length=3)
    checklist: list[str] = Field(min_length=2, max_length=5)
    stages: list[NextStepStage] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_workflow(self) -> NextStep:
        if self.route_ids != ["practical-hook", "people-story", "playful-contrast"]:
            raise ValueError("next_step route_ids must list all creative routes in order")
        if [item.stage for item in self.stages] != [
            "select-route",
            "prepare-shoot",
            "record-publication",
        ]:
            raise ValueError("next_step stages must follow select, prepare, record order")
        if [item.status for item in self.stages] != ["current", "upcoming", "upcoming"]:
            raise ValueError("next_step must mark route selection as the current stage")
        return self


class MarketingPlanResponse(StrictModel):
    product_profile: ProductProfile
    strategy: PlatformStrategy
    trend: TrendBrief
    creative_routes: list[CreativeRoute] = Field(min_length=3, max_length=3)
    topic_signals: list[TopicSignal] = Field(min_length=3, max_length=3)
    videos: list[VideoScript] = Field(min_length=3, max_length=3)
    livestream: list[LivestreamSection] = Field(min_length=4, max_length=8)
    seven_day_plan: list[DailyPlan] = Field(min_length=7, max_length=7)
    next_actions: list[str] = Field(min_length=3, max_length=6)
    next_step: NextStep
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
    cache_hit: bool = False
    degraded: bool = False
    notice: str = ""

    @model_validator(mode="after")
    def validate_complete_distinct_plan(self) -> MarketingPlanResponse:
        if [item.day for item in self.seven_day_plan] != list(range(1, 8)):
            raise ValueError("seven_day_plan must contain ordered days 1 through 7")
        normalized_angles = {item.angle.strip().casefold() for item in self.videos}
        normalized_titles = {item.title.strip().casefold() for item in self.videos}
        if len(normalized_angles) != 3 or len(normalized_titles) != 3:
            raise ValueError("videos must contain three distinct angles and titles")
        route_ids = [item.route_id for item in self.creative_routes]
        video_route_ids = [item.route_id for item in self.videos]
        if route_ids != ["practical-hook", "people-story", "playful-contrast"]:
            raise ValueError("creative_routes must contain the three supported routes in order")
        if video_route_ids != route_ids:
            raise ValueError("videos must map one-to-one to creative_routes")
        if [item.signal_type for item in self.topic_signals] != [
            "manual-hotspot",
            "seasonal-farming",
            "evergreen-pain-point",
        ]:
            raise ValueError("topic_signals must contain manual, seasonal and evergreen signals")
        return self


class MarketingProviderError(RuntimeError):
    pass


class MarketingPlanProvider(Protocol):
    name: str
    model: str

    def generate(self, request: MarketingPlanRequest) -> MarketingPlanResponse: ...


@dataclass
class _CacheEntry:
    expires_at: float
    value: MarketingPlanResponse


class MarketingPlanCache:
    """Small bounded in-process cache for repeated demo and generation requests."""

    def __init__(self) -> None:
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> MarketingPlanResponse | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            result = entry.value.model_copy(deep=True)
        result.cache_hit = True
        return result

    def put(
        self,
        key: str,
        value: MarketingPlanResponse,
        *,
        ttl_seconds: int,
        max_entries: int,
    ) -> None:
        entry = _CacheEntry(
            expires_at=time.monotonic() + ttl_seconds,
            value=value.model_copy(deep=True),
        )
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_marketing_cache = MarketingPlanCache()


PLATFORM_NAMES = {
    "zh-CN": {
        "douyin": "抖音",
        "xiaohongshu": "小红书",
        "wechat-channels": "视频号",
        "kuaishou": "快手",
    },
    "zh-HK": {
        "douyin": "抖音",
        "xiaohongshu": "小紅書",
        "wechat-channels": "視頻號",
        "kuaishou": "快手",
    },
    "en": {
        "douyin": "Douyin",
        "xiaohongshu": "Xiaohongshu",
        "wechat-channels": "WeChat Channels",
        "kuaishou": "Kuaishou",
    },
}


def _clean_points(request: MarketingPlanRequest) -> list[str]:
    points = [item.strip() for item in request.selling_points if item.strip()]
    fallbacks = {
        "zh-CN": ["当季新鲜", "产地直供", "真实农家风味"],
        "zh-HK": ["當季新鮮", "產地直供", "真實農家風味"],
        "en": ["seasonal freshness", "direct from the growing region", "an authentic farm story"],
    }
    for fallback in fallbacks[request.locale]:
        if len(points) >= 3:
            break
        if fallback not in points:
            points.append(fallback)
    return points[:5]


def _text(locale: Locale, simplified: str, traditional: str, english: str) -> str:
    if locale == "en":
        return english
    if locale == "zh-HK":
        return traditional
    return simplified


def _creative_routes(request: MarketingPlanRequest) -> list[CreativeRoute]:
    product = request.product_name
    platform = PLATFORM_NAMES[request.locale][request.platform]
    audience = request.audience or _text(
        request.locale,
        "关注真实产地、品质细节和家庭消费场景的人",
        "關注真實產地、品質細節和家庭消費場景的人",
        "people who value real origin, product detail and everyday use",
    )
    return [
        CreativeRoute(
            route_id="practical-hook",
            name=_text(request.locale, "实用吸睛", "實用吸睛", "Practical hook"),
            positioning=_text(
                request.locale,
                f"用一个马上能用的挑选、保存或食用判断，让{product}在前三秒提供价值。",
                f"用一個馬上能用的挑選、保存或食用判斷，讓{product}在前三秒提供價值。",
                f"Give viewers one immediately useful way to choose, store or use {product}.",
            ),
            best_for=_text(
                request.locale,
                "需要快速建立停留和收藏价值的首发内容",
                "需要快速建立停留和收藏價值的首發內容",
                "A first post that needs quick retention and save value",
            ),
            signature_hook=_text(
                request.locale,
                f"挑{product}别只看价格，先看这个细节。",
                f"挑{product}別只看價格，先看這個細節。",
                f"Do not choose {product} on price alone; check this detail first.",
            ),
            selection_reason=_text(
                request.locale,
                f"{platform}适合用明确问题承接{audience}的实际需求。",
                f"{platform}適合用明確問題承接{audience}的實際需要。",
                f"{platform} can turn a clear question into practical value for {audience}.",
            ),
        ),
        CreativeRoute(
            route_id="people-story",
            name=_text(request.locale, "人物故事", "人物故事", "People story"),
            positioning=_text(
                request.locale,
                f"由种植者讲一个与{product}有关的真实决定，用人物建立信任。",
                f"由種植者講一個與{product}有關的真實決定，用人物建立信任。",
                f"Let the grower explain one real decision behind {product} to build trust.",
            ),
            best_for=_text(
                request.locale,
                "品牌建立、产地信任和视频号式熟人传播",
                "品牌建立、產地信任和視頻號式熟人傳播",
                "Brand building, origin trust and relationship-led sharing",
            ),
            signature_hook=_text(
                request.locale,
                f"种了这么多年{product}，我最不愿省掉的是这一步。",
                f"種了這麼多年{product}，我最不願省掉的是這一步。",
                f"After years of growing {product}, this is the step I will not skip.",
            ),
            selection_reason=_text(
                request.locale,
                f"{audience}不仅需要卖点，也需要知道是谁在为这些细节负责。",
                f"{audience}不只需要賣點，也需要知道是誰在為這些細節負責。",
                f"{audience} need to see not only the selling point, but who stands behind it.",
            ),
        ),
        CreativeRoute(
            route_id="playful-contrast",
            name=_text(request.locale, "轻松反差", "輕鬆反差", "Playful contrast"),
            positioning=_text(
                request.locale,
                f"先展示对{product}的常见误判，再用切开、冲泡或装箱画面轻松翻转。",
                f"先展示對{product}的常見誤判，再用切開、沖泡或裝箱畫面輕鬆翻轉。",
                f"Start with a common mistaken impression of {product}, then reverse it visually.",
            ),
            best_for=_text(
                request.locale,
                "需要提升评论意愿、分享感和记忆点的内容",
                "需要提升留言意願、分享感和記憶點的內容",
                "Content that needs more comments, shares and memorability",
            ),
            signature_hook=_text(
                request.locale,
                f"看着普通的{product}，下一镜可能和你想的不一样。",
                f"看起來普通的{product}，下一鏡可能和你想的不一樣。",
                f"This ordinary-looking {product} may change your mind in the next shot.",
            ),
            selection_reason=_text(
                request.locale,
                f"用真实可拍的前后对比制造反差，不靠夸张承诺也能适配{platform}。",
                f"用真實可拍的前後對比製造反差，不靠誇張承諾也能適配{platform}。",
                f"A filmable before-and-after contrast fits {platform} without exaggerated claims.",
            ),
        ),
    ]


def _fit_dimension(score: int, rationale: str) -> TopicFitDimension:
    return TopicFitDimension(score=score, rationale=rationale)


def _topic_signal(
    *,
    signal_type: TopicSignalType,
    title: str,
    content_angle: str,
    source_label: str,
    source_note: str,
    scores: TopicFitScores,
    explanation: str,
    usage_caution: str,
) -> TopicSignal:
    total_score = scores.average()
    recommendation: Recommendation
    if total_score >= 75:
        recommendation = "recommended"
    elif total_score >= 55:
        recommendation = "consider"
    else:
        recommendation = "skip"
    return TopicSignal(
        signal_type=signal_type,
        title=title,
        content_angle=content_angle,
        source_label=source_label,
        source_note=source_note,
        fit_scores=scores,
        total_score=total_score,
        recommendation=recommendation,
        explanation=explanation,
        usage_caution=usage_caution,
    )


def _topic_signals(request: MarketingPlanRequest) -> list[TopicSignal]:
    locale = request.locale
    product = request.product_name
    audience_supplied = bool(request.audience.strip())
    trend = request.trend.strip()
    context = " ".join(
        (request.product_name, request.product_description, request.trend, *request.selling_points)
    ).casefold()
    seasonal_terms = (
        "当季",
        "春",
        "夏",
        "秋",
        "冬",
        "采摘",
        "採摘",
        "收获",
        "收穫",
        "节气",
        "節氣",
        "season",
        "harvest",
        "picked",
    )
    has_season_context = any(term.casefold() in context for term in seasonal_terms)
    platform_name = PLATFORM_NAMES[locale][request.platform]

    if trend:
        manual_scores = TopicFitScores(
            product=_fit_dimension(
                72 if product.casefold() in trend.casefold() else 58,
                _text(
                    locale,
                    "热点由用户手工提供；与产品直接同词时匹配更强。",
                    "熱點由用戶手工提供；與產品直接同詞時匹配更強。",
                    "The topic was supplied manually; an explicit product mention improves fit.",
                ),
            ),
            audience=_fit_dimension(
                68 if audience_supplied else 60,
                _text(
                    locale,
                    "可借热点提问，但仍需用目标受众的真实问题承接。",
                    "可借熱點提問，但仍需用目標受眾的真實問題承接。",
                    "The topic can open a question, but it still needs a real audience need.",
                ),
            ),
            platform=_fit_dimension(
                76,
                _text(
                    locale,
                    f"{platform_name}可使用热点叙事结构，但不等于平台正在推荐该话题。",
                    f"{platform_name}可使用熱點敘事結構，但不代表平台正在推薦該話題。",
                    f"{platform_name} can use the topic structure, but this does not prove promotion.",
                ),
            ),
            timeliness=_fit_dimension(
                55,
                _text(
                    locale,
                    "未连接实时数据，发布当天必须重新核对语境和时效。",
                    "未連接實時數據，發佈當天必須重新核對語境和時效。",
                    "No live data is connected; verify context and timing on publishing day.",
                ),
            ),
            filmability=_fit_dimension(
                72,
                _text(
                    locale,
                    "只借开头结构，主体仍可用现有产品和产地素材完成。",
                    "只借開頭結構，主體仍可用現有產品和產地素材完成。",
                    "Borrow only the opening structure; existing product footage can carry the body.",
                ),
            ),
            source=_fit_dimension(
                50,
                _text(
                    locale,
                    "来源是用户输入，未经过热度、出处或事实核验。",
                    "來源是用戶輸入，未經熱度、出處或事實核驗。",
                    "The source is user input and has not been verified for popularity or provenance.",
                ),
            ),
        )
        manual_title = trend
        manual_angle = _text(
            locale,
            f"用“{trend}”的提问方式开场，三秒内回到{product}的真实细节。",
            f"用「{trend}」的提問方式開場，三秒內回到{product}的真實細節。",
            f"Use the question structure of “{trend}”, then return to real {product} detail.",
        )
    else:
        manual_scores = TopicFitScores(
            product=_fit_dimension(
                25,
                _text(
                    locale,
                    "没有输入具体热点，无法判断产品相关性。",
                    "沒有輸入具體熱點，無法判斷產品相關性。",
                    "No specific topic was supplied.",
                ),
            ),
            audience=_fit_dimension(
                30,
                _text(
                    locale,
                    "没有热点内容可与受众需求比对。",
                    "沒有熱點內容可與受眾需要比對。",
                    "There is no topic to compare with audience needs.",
                ),
            ),
            platform=_fit_dimension(
                35,
                _text(
                    locale,
                    "不能据此声称平台正在流行某话题。",
                    "不能據此聲稱平台正在流行某話題。",
                    "No platform trend can be claimed from missing input.",
                ),
            ),
            timeliness=_fit_dimension(
                20,
                _text(
                    locale,
                    "没有时间戳或实时热度来源。",
                    "沒有時間戳或實時熱度來源。",
                    "There is no timestamp or live popularity source.",
                ),
            ),
            filmability=_fit_dimension(
                45,
                _text(
                    locale,
                    "可先保留热点插槽，但不应围绕未知话题拍摄。",
                    "可先保留熱點插槽，但不應圍繞未知話題拍攝。",
                    "Keep a topic slot, but do not film around an unknown trend.",
                ),
            ),
            source=_fit_dimension(
                15,
                _text(
                    locale,
                    "本次请求没有提供手工热点来源。",
                    "本次請求沒有提供手工熱點來源。",
                    "No manual topic source was provided.",
                ),
            ),
        )
        manual_title = _text(locale, "未提供手工热点", "未提供手工熱點", "No manual topic supplied")
        manual_angle = _text(
            locale,
            "跳过热点绑定，先完成稳定的产品内容。",
            "跳過熱點綁定，先完成穩定的產品內容。",
            "Skip trend binding and make a stable product-led post first.",
        )

    seasonal_scores = TopicFitScores(
        product=_fit_dimension(
            88 if has_season_context else 68,
            _text(
                locale,
                "输入中已有采摘、当季或农时线索。"
                if has_season_context
                else "产品可讲农时，但输入未给出明确季节事实。",
                "輸入中已有採摘、當季或農時線索。"
                if has_season_context
                else "產品可講農時，但輸入未提供明確季節事實。",
                "The input includes harvest or seasonal context."
                if has_season_context
                else "The product can support a farming-time angle, but no season was stated.",
            ),
        ),
        audience=_fit_dimension(
            78,
            _text(
                locale,
                "农时能解释新鲜度和生产过程，容易转化为购买判断。",
                "農時能解釋新鮮度和生產過程，容易轉化為購買判斷。",
                "Farming time can explain freshness and production choices.",
            ),
        ),
        platform=_fit_dimension(
            74,
            _text(
                locale,
                f"{platform_name}适合用短镜头展示采摘或制作节点。",
                f"{platform_name}適合用短鏡頭展示採摘或製作節點。",
                f"{platform_name} supports short visual demonstrations of harvest or making.",
            ),
        ),
        timeliness=_fit_dimension(
            76 if has_season_context else 58,
            _text(
                locale,
                "时效来自用户提供的产品描述，不是外部日历推断。",
                "時效來自用戶提供的產品描述，不是外部日曆推斷。",
                "Timing comes from the supplied description, not an external calendar assumption.",
            ),
        ),
        filmability=_fit_dimension(
            86,
            _text(
                locale,
                "可拍采摘、冲泡、切开、分级或装箱等连续动作。",
                "可拍採摘、沖泡、切開、分級或裝箱等連續動作。",
                "Harvesting, brewing, cutting, grading or packing are filmable actions.",
            ),
        ),
        source=_fit_dimension(
            82 if has_season_context else 62,
            _text(
                locale,
                "仅使用请求中的产品事实；未补造具体节气和日期。",
                "只使用請求中的產品事實；未虛構具體節氣和日期。",
                "Only supplied product facts are used; no date or solar term is invented.",
            ),
        ),
    )
    evergreen_scores = TopicFitScores(
        product=_fit_dimension(
            88,
            _text(
                locale,
                f"围绕如何挑选、使用和保存{product}，与产品直接相关。",
                f"圍繞如何挑選、使用和保存{product}，與產品直接相關。",
                f"Choosing, using and storing {product} is directly relevant.",
            ),
        ),
        audience=_fit_dimension(
            86,
            _text(
                locale,
                "解决购买前后反复出现的问题，受众价值明确。",
                "解決購買前後反覆出現的問題，受眾價值明確。",
                "It solves recurring questions before and after purchase.",
            ),
        ),
        platform=_fit_dimension(
            84,
            _text(
                locale,
                f"适合{platform_name}的清单、对比和问答结构。",
                f"適合{platform_name}的清單、對比和問答結構。",
                f"It fits list, comparison and Q&A formats on {platform_name}.",
            ),
        ),
        timeliness=_fit_dimension(
            92,
            _text(
                locale,
                "常青痛点不依赖短期热度，可反复更新。",
                "常青痛點不依賴短期熱度，可重複更新。",
                "An evergreen pain point does not depend on short-lived popularity.",
            ),
        ),
        filmability=_fit_dimension(
            90,
            _text(
                locale,
                "一部手机即可拍摄细节对比和操作演示。",
                "一部手機即可拍攝細節對比和操作示範。",
                "A phone is enough for detail comparisons and demonstrations.",
            ),
        ),
        source=_fit_dimension(
            76,
            _text(
                locale,
                "来源是产品信息与通用消费决策场景，不声称来自实时榜单。",
                "來源是產品資料與通用消費決策場景，不聲稱來自實時榜單。",
                "The source is product context and a common buying scenario, not a live chart.",
            ),
        ),
    )
    return [
        _topic_signal(
            signal_type="manual-hotspot",
            title=manual_title,
            content_angle=manual_angle,
            source_label=_text(locale, "用户手工输入", "用戶手工輸入", "Manual user input"),
            source_note=_text(
                locale,
                "这是策划输入，不代表实时热度、平台推荐或事实背书。",
                "這是策劃輸入，不代表實時熱度、平台推薦或事實背書。",
                "This is planning input, not evidence of live popularity or platform promotion.",
            ),
            scores=manual_scores,
            explanation=_text(
                locale,
                "是否采用由六项适配分决定；低分时直接跳过，不强行蹭热点。",
                "是否採用由六項適配分決定；低分時直接跳過，不勉強追熱點。",
                "Use depends on six fit dimensions; skip it rather than force a weak trend.",
            ),
            usage_caution=_text(
                locale,
                "发布前人工核对来源、语境和时效。",
                "發佈前人工核對來源、語境和時效。",
                "Check source, context and timing manually before publishing.",
            ),
        ),
        _topic_signal(
            signal_type="seasonal-farming",
            title=_text(
                locale,
                f"{product}的节气与农时节点",
                f"{product}的節氣與農時節點",
                f"Seasonal and farming-time cues for {product}",
            ),
            content_angle=_text(
                locale,
                "只讲输入中能够证明的采摘、制作或供应节点。",
                "只講輸入中能夠證明的採摘、製作或供應節點。",
                "Explain only harvest, making or supply timing supported by the input.",
            ),
            source_label=_text(
                locale, "产品描述与卖点", "產品描述與賣點", "Product description and selling points"
            ),
            source_note=_text(
                locale,
                "未接入节气日历或产区数据库，不自动断言当前正值某个农时。",
                "未接入節氣日曆或產區資料庫，不自動斷言目前正值某個農時。",
                "No calendar or regional database is connected, so current farming time is not asserted.",
            ),
            scores=seasonal_scores,
            explanation=_text(
                locale,
                "有明确季节线索时优先采用；线索不足时先向农户核实。",
                "有明確季節線索時優先採用；線索不足時先向農戶核實。",
                "Prioritize when seasonal evidence is explicit; otherwise confirm it with the grower.",
            ),
            usage_caution=_text(
                locale,
                "不要补写请求中没有的节气、采摘日期或产量。",
                "不要補寫請求中沒有的節氣、採摘日期或產量。",
                "Do not add a solar term, harvest date or yield that was not supplied.",
            ),
        ),
        _topic_signal(
            signal_type="evergreen-pain-point",
            title=_text(
                locale,
                f"{product}怎么挑、怎么用、怎么保存",
                f"{product}怎樣挑、怎樣用、怎樣保存",
                f"How to choose, use and store {product}",
            ),
            content_angle=_text(
                locale,
                "用一个可见细节回答高频购买问题，再邀请观众补充自己的判断。",
                "用一個可見細節回答高頻購買問題，再邀請觀眾補充自己的判斷。",
                "Answer a recurring buying question with visible detail, then invite responses.",
            ),
            source_label=_text(
                locale, "常青消费痛点", "常青消費痛點", "Evergreen consumer pain point"
            ),
            source_note=_text(
                locale,
                "这是稳定选题框架，不代表任何实时搜索量或热度排名。",
                "這是穩定選題框架，不代表任何實時搜尋量或熱度排名。",
                "This is a stable topic frame, not a claim about live search volume or ranking.",
            ),
            scores=evergreen_scores,
            explanation=_text(
                locale,
                "与产品、受众和拍摄条件都直接相关，适合作为首选稳定选题。",
                "與產品、受眾和拍攝條件都直接相關，適合作為首選穩定選題。",
                "It directly fits the product, audience and filming constraints, making it a stable first choice.",
            ),
            usage_caution=_text(
                locale,
                "操作建议必须与真实产品一致，不把个人经验包装成统一标准。",
                "操作建議必須與真實產品一致，不把個人經驗包裝成統一標準。",
                "Keep advice true to the product and do not present personal practice as a universal rule.",
            ),
        ),
    ]


def _video_quality_assessment(
    request: MarketingPlanRequest,
    route_id: CreativeRouteId,
    *,
    hook: str,
    script: str,
    shots: list[Shot],
    call_to_action: str,
) -> VideoQualityAssessment:
    hook_score = {
        "practical-hook": 92,
        "people-story": 86,
        "playful-contrast": 90,
    }[route_id]
    if request.product_name.casefold() not in hook.casefold():
        hook_score -= 4
    factual_score = 92 if request.product_description.strip() in script else 82
    platform_score = {
        "douyin": 90,
        "xiaohongshu": 88 if route_id == "practical-hook" else 86,
        "wechat-channels": 90 if route_id == "people-story" else 84,
        "kuaishou": 88,
    }[request.platform]
    filmability_score = min(
        96,
        70 + len(shots) * 4 + (6 if all(shot.filming_tip.strip() for shot in shots) else 0),
    )
    interaction_tokens = ("评论", "留言", "comment", "details", "想尝", "想試")
    interaction_score = (
        90
        if any(token.casefold() in call_to_action.casefold() for token in interaction_tokens)
        else 72
    )
    compliance_score = (
        45 if any(pattern.search(script) for pattern in HIGH_RISK_CLAIM_PATTERNS) else 96
    )
    scores = VideoQualityScores(
        hook=hook_score,
        factual_grounding=factual_score,
        platform_fit=platform_score,
        filmability=filmability_score,
        interaction=interaction_score,
        compliance=compliance_score,
    )
    route_strength = {
        "practical-hook": _text(
            request.locale,
            "开头给出明确判断题，收藏价值强。",
            "開頭給出明確判斷題，收藏價值強。",
            "The opening gives a clear decision and strong save value.",
        ),
        "people-story": _text(
            request.locale,
            "人物动机清楚，适合建立产地信任。",
            "人物動機清楚，適合建立產地信任。",
            "The human motivation is clear and supports origin trust.",
        ),
        "playful-contrast": _text(
            request.locale,
            "反差由真实画面完成，记忆点明确。",
            "反差由真實畫面完成，記憶點明確。",
            "The contrast is visual and memorable without relying on hype.",
        ),
    }[route_id]
    return VideoQualityAssessment(
        scores=scores,
        total_score=scores.average(),
        strengths=[
            route_strength,
            _text(
                request.locale,
                "事实来自请求中的产品描述和卖点，没有补造实时热度。",
                "事實來自請求中的產品描述和賣點，沒有虛構實時熱度。",
                "Facts come from the supplied description and selling points, with no invented trend data.",
            ),
        ],
        improvements=[
            _text(
                request.locale,
                f"拍摄前补充一个可核实的{request.product_name}细节，并用近景证明。",
                f"拍攝前補充一個可核實的{request.product_name}細節，並用近鏡證明。",
                f"Before filming, add one verifiable {request.product_name} detail and prove it in close-up.",
            ),
            _text(
                request.locale,
                "发布后记录三秒留存、完播和有效评论，下一轮再调整钩子。",
                "發佈後記錄三秒留存、完播和有效留言，下一輪再調整開場。",
                "After publishing, record three-second retention, completion and useful comments.",
            ),
        ],
    )


def _next_step(request: MarketingPlanRequest) -> NextStep:
    product = request.product_name
    platform = PLATFORM_NAMES[request.locale][request.platform]
    return NextStep(
        current_stage="select-route",
        title=_text(
            request.locale,
            "先选择一条创意路线",
            "先選擇一條創意路線",
            "Choose one creative route first",
        ),
        primary_action=_text(
            request.locale,
            f"为{product}在{platform}的首条内容选择实用吸睛、人物故事或轻松反差之一。",
            f"為{product}在{platform}的首條內容選擇實用吸睛、人物故事或輕鬆反差其中一條。",
            f"Choose Practical hook, People story or Playful contrast for the first {product} post on {platform}.",
        ),
        route_ids=["practical-hook", "people-story", "playful-contrast"],
        checklist=[
            _text(
                request.locale,
                "优先查看推荐选题及各路线质量分。",
                "優先查看推薦選題及各路線質量分。",
                "Review recommended topics and each route quality score.",
            ),
            _text(
                request.locale,
                "确认路线中的事实都能由产品或现场画面证明。",
                "確認路線中的事實都能由產品或現場畫面證明。",
                "Confirm every route claim can be proved by the product or location.",
            ),
            _text(
                request.locale,
                "一次只选一条路线进入拍摄，避免信息过多。",
                "一次只選一條路線進入拍攝，避免資訊過多。",
                "Move only one route into filming to avoid an overloaded post.",
            ),
        ],
        stages=[
            NextStepStage(
                stage="select-route",
                status="current",
                instruction=_text(
                    request.locale,
                    "比较三条路线，锁定一条主路线。",
                    "比較三條路線，鎖定一條主路線。",
                    "Compare the three routes and lock one primary route.",
                ),
                completion_signal=_text(
                    request.locale,
                    "已选定 route_id，并确认对应视频脚本。",
                    "已選定 route_id，並確認對應影片腳本。",
                    "A route_id and its video script are selected.",
                ),
            ),
            NextStepStage(
                stage="prepare-shoot",
                status="upcoming",
                instruction=_text(
                    request.locale,
                    "按镜头清单准备产品、人物、场地和可核实事实。",
                    "按鏡頭清單準備產品、人物、場地和可核實事實。",
                    "Prepare product, person, location and verifiable facts from the shot list.",
                ),
                completion_signal=_text(
                    request.locale,
                    "素材与拍摄责任人齐备，可以开拍。",
                    "素材與拍攝負責人齊備，可以開拍。",
                    "Materials and filming owner are ready.",
                ),
            ),
            NextStepStage(
                stage="record-publication",
                status="upcoming",
                instruction=_text(
                    request.locale,
                    "发布后记录时间、链接、路线和核心表现数据。",
                    "發佈後記錄時間、連結、路線和核心表現數據。",
                    "After publishing, record time, link, route and core performance data.",
                ),
                completion_signal=_text(
                    request.locale,
                    "已形成可用于下一轮优化的发布记录。",
                    "已形成可用於下一輪優化的發佈記錄。",
                    "A publication record is ready for the next iteration.",
                ),
            ),
        ],
    )


class DeterministicMarketingProvider:
    """Stable, zero-cost provider for demos, tests and offline use."""

    name = "mock"
    model = "farmer-marketing-v1"

    def generate(self, request: MarketingPlanRequest) -> MarketingPlanResponse:
        started = time.perf_counter()
        if request.locale == "en":
            result = self._english(request)
        elif request.locale == "zh-HK":
            result = self._traditional(request)
        else:
            result = self._simplified(request)
        result.provider = self.name
        result.model = self.model
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return result

    @staticmethod
    def _simplified(request: MarketingPlanRequest) -> MarketingPlanResponse:
        product = request.product_name
        origin = request.origin or "本地农场"
        points = _clean_points(request)
        platform_name = PLATFORM_NAMES["zh-CN"][request.platform]
        audience = request.audience or "关注新鲜食材、家庭餐桌与产地故事的消费者"
        trend = request.trend.strip()
        cta = "评论区留言“想尝”，获取规格、价格和发货信息"
        creative_routes = _creative_routes(request)
        angles: list[tuple[CreativeRouteId, str, str, str, str]] = [
            (
                "practical-hook",
                "实用吸睛",
                f"挑{product}，先看这个真实细节",
                f"挑{product}别只看价格，先看这个细节。",
                "节奏清晰、鼓点轻盈的知识类配乐",
            ),
            (
                "people-story",
                "人物故事",
                f"种了这么多年{product}，这一步我不愿省",
                f"我是{origin}的种植者，做{product}时最不愿省掉的是这一步。",
                "温暖克制的钢琴与环境声",
            ),
            (
                "playful-contrast",
                "轻松反差",
                f"看着普通的{product}，下一镜不一样",
                f"看着普通的{product}，切开、冲泡或装箱后可能和你想的不一样。",
                "轻松俏皮、不过度夸张的节奏配乐",
            ),
        ]
        videos: list[VideoScript] = []
        for index, (route_id, angle, title, hook, music) in enumerate(angles):
            point = points[index % len(points)]
            script = (
                f"{hook} 这一季我们最在意的是{point}。"
                f"{request.product_description.strip()} "
                f"镜头里不需要复杂表演，把采摘、切开或装箱的真实过程拍清楚，"
                f"让大家先看见产品，再听见种植者的话。{cta}。"
            )
            shots = [
                Shot(
                    seconds="0–3秒",
                    visual="产品特写快速入镜，保留自然环境声",
                    voiceover=hook,
                    filming_tip="手机竖拍，靠近主体，第一镜不要超过3秒",
                ),
                Shot(
                    seconds="3–12秒",
                    visual="展示产地、采摘或处理过程",
                    voiceover=f"这一季我们最在意的是{point}。",
                    filming_tip="用连续动作代替站着讲，画面更有信息量",
                ),
                Shot(
                    seconds="12–24秒",
                    visual="切开、称重、冲泡或细节对比",
                    voiceover=request.product_description.strip()[:120],
                    filming_tip="用自然光，避免滤镜改变产品真实颜色",
                ),
                Shot(
                    seconds="24–30秒",
                    visual="农户出镜或产品整齐装箱",
                    voiceover=cta,
                    filming_tip="结尾只保留一个行动指令",
                ),
            ]
            videos.append(
                VideoScript(
                    route_id=route_id,
                    angle=angle,
                    title=title,
                    cover_text=f"{product}｜{point}",
                    hook=hook,
                    script=script,
                    background_music=music,
                    shots=shots,
                    call_to_action=cta,
                    quality_assessment=_video_quality_assessment(
                        request,
                        route_id,
                        hook=hook,
                        script=script,
                        shots=shots,
                        call_to_action=cta,
                    ),
                )
            )
        trend_brief = (
            TrendBrief(
                trend_used=trend,
                integration_method="只借用热点的叙事结构或讨论角度，在开头建立关联，再迅速回到产品和产地。",
                caution="不照搬争议话题，不虚构参与热点的事实，也不让热点盖过产品。",
            )
            if trend
            else TrendBrief(
                trend_used="本次未指定实时热点",
                integration_method="先用稳定的产地、产品差异和人物故事完成可复用内容；后续可在发布前补充热点。",
                caution="热点有效期短，应在发布当天复核热度与语境。",
            )
        )
        return MarketingPlanResponse(
            product_profile=ProductProfile(
                one_line_value=f"来自{origin}的{product}，用真实产地过程讲清{points[0]}。",
                core_audience=audience,
                core_selling_points=points[:3],
                story_angle=f"不把{product}拍成广告道具，而是让种植过程、产品细节和农户本人共同作证。",
            ),
            strategy=PlatformStrategy(
                platform=request.platform,
                platform_name=platform_name,
                content_focus="前三秒给出明确看点，中段用现场细节建立兴趣，结尾只设置一个转化动作。",
                recommended_duration="25–40秒；人物故事可延长至60秒",
                conversion_action=cta,
            ),
            trend=trend_brief,
            creative_routes=creative_routes,
            topic_signals=_topic_signals(request),
            videos=videos,
            livestream=[
                LivestreamSection(
                    section="开场留人",
                    talking_points=[f"先展示今天的{product}", "说清产地和本场直播能获得什么"],
                ),
                LivestreamSection(
                    section="产品讲解",
                    talking_points=[
                        f"围绕{points[0]}、{points[1]}、{points[2]}逐一展示",
                        "每个卖点都配一个可见的动作或细节",
                    ],
                ),
                LivestreamSection(
                    section="信任建立",
                    talking_points=[
                        "讲一个真实种植决定",
                        "展示采摘、规格或装箱过程",
                        "不确定的信息现场不承诺",
                    ],
                ),
                LivestreamSection(
                    section="成交引导",
                    talking_points=[
                        "明确规格、价格、发货和售后",
                        "用一个口令承接评论或私信",
                        "重复核心适用人群",
                    ],
                ),
                LivestreamSection(
                    section="常见问答",
                    talking_points=["口感和食用方式", "保存方式与建议时长", "发货范围与到货处理"],
                ),
            ],
            seven_day_plan=[
                DailyPlan(
                    day=1,
                    objective="让用户认识产品",
                    content=f"发布“{angles[0][2]}”实用视频",
                    action="记录完播率与高频评论",
                ),
                DailyPlan(
                    day=2,
                    objective="解释产品差异",
                    content=f"发布“{angles[1][2]}”人物视频",
                    action="把评论问题加入直播问答",
                ),
                DailyPlan(
                    day=3,
                    objective="建立人物信任",
                    content=f"发布“{angles[2][2]}”反差视频",
                    action="置顶一个真实种植细节",
                ),
                DailyPlan(
                    day=4,
                    objective="促进互动",
                    content=f"发起{product}吃法或挑选方式征集",
                    action="回复至少10条有效评论",
                ),
                DailyPlan(
                    day=5,
                    objective="直播预热",
                    content="发布装箱、备货或直播预告",
                    action="明确直播时间和主推规格",
                ),
                DailyPlan(
                    day=6,
                    objective="集中转化",
                    content=f"围绕{product}完成一场30–60分钟直播",
                    action="记录高频问题、停留峰值和成交节点",
                ),
                DailyPlan(
                    day=7,
                    objective="复盘并再利用",
                    content="剪辑直播中的高价值问答",
                    action="保留有效开头，改写表现较弱的脚本",
                ),
            ],
            next_actions=[
                "确认产品价格、规格和库存",
                "拍摄产地与产品细节素材",
                "选择第一条脚本并按镜头清单拍摄",
                "发布后记录数据用于下一轮优化",
            ],
            next_step=_next_step(request),
            provider="",
            model="",
            latency_ms=0,
        )

    @staticmethod
    def _traditional(request: MarketingPlanRequest) -> MarketingPlanResponse:
        simplified = DeterministicMarketingProvider._simplified(
            request.model_copy(update={"locale": "zh-CN"})
        )
        protected_values = tuple(
            dict.fromkeys(
                value
                for value in (
                    request.product_name,
                    request.origin,
                    request.product_description,
                    request.audience,
                    request.trend,
                    *request.selling_points,
                )
                if value
            )
        )
        raw = simplified.model_dump_json()
        placeholders: dict[str, str] = {}
        for index, value in enumerate(protected_values):
            placeholder = f"__HEYU_USER_INPUT_{index}__"
            raw = raw.replace(value, placeholder)
            placeholders[placeholder] = value
        replacements = {
            "小红书": "小紅書",
            "视频号": "視頻號",
            "数据库": "資料庫",
            "操作演示": "操作示範",
            "钩子": "開場",
            "来自": "來自",
            "这里": "這裡",
            "哪里": "哪裡",
            "这个": "這個",
            "这些": "這些",
            "这批": "這批",
            "这一": "這一",
            "这季": "這季",
            "我们": "我們",
            "大家": "大家",
            "告诉": "告訴",
            "带你": "帶你",
            "看见": "看見",
            "听见": "聽見",
            "开始": "開始",
            "选择": "選擇",
            "继续": "繼續",
            "已经": "已經",
            "适合": "適合",
            "关注": "關注",
            "家庭": "家庭",
            "食材": "食材",
            "消费者": "消費者",
            "产品": "產品",
            "农户": "農戶",
            "农场": "農場",
            "产地": "產地",
            "真实": "真實",
            "视频": "影片",
            "直播": "直播",
            "发布": "發佈",
            "评论": "留言",
            "发货": "出貨",
            "用户": "用戶",
            "记录": "記錄",
            "问题": "問題",
            "当季": "當季",
            "新鲜": "新鮮",
            "种植": "種植",
            "内容": "內容",
            "计划": "計劃",
            "规格": "規格",
            "价格": "價格",
            "转化": "轉化",
            "动作": "行動",
            "过程": "過程",
            "资料": "資料",
            "开场": "開場",
            "讲解": "講解",
            "建议": "建議",
            "镜头": "鏡頭",
            "标题": "標題",
            "话术": "話術",
            "拍摄": "拍攝",
            "采摘": "採摘",
            "冲泡": "沖泡",
            "装箱": "裝箱",
            "处理": "處理",
            "展示": "展示",
            "细节": "細節",
            "发起": "發起",
            "预热": "預熱",
            "集中": "集中",
            "复盘": "覆盤",
            "改写": "改寫",
            "时长": "時長",
            "确认": "確認",
            "库存": "庫存",
            "发布后": "發佈後",
            "实用": "實用",
            "轻松": "輕鬆",
            "质量": "質量",
            "推荐": "推薦",
            "信息": "資訊",
        }
        for source, target in replacements.items():
            raw = raw.replace(source, target)
        character_replacements: dict[str, str | int | None] = {
            "来": "來",
            "这": "這",
            "里": "裡",
            "个": "個",
            "们": "們",
            "带": "帶",
            "见": "見",
            "听": "聽",
            "开": "開",
            "选": "選",
            "继": "繼",
            "经": "經",
            "适": "適",
            "关": "關",
            "鲜": "鮮",
            "费": "費",
            "产": "產",
            "农": "農",
            "场": "場",
            "实": "實",
            "视": "視",
            "评": "評",
            "发": "發",
            "货": "貨",
            "户": "戶",
            "录": "錄",
            "问": "問",
            "当": "當",
            "种": "種",
            "内": "內",
            "计": "計",
            "划": "劃",
            "规": "規",
            "价": "價",
            "转": "轉",
            "动": "動",
            "过": "過",
            "资": "資",
            "议": "議",
            "镜": "鏡",
            "标": "標",
            "话": "話",
            "摄": "攝",
            "采": "採",
            "装": "裝",
            "处": "處",
            "细": "細",
            "预": "預",
            "复": "複",
            "写": "寫",
            "时": "時",
            "长": "長",
            "确": "確",
            "库": "庫",
            "后": "後",
            "讲": "講",
            "与": "與",
            "证": "證",
            "让": "讓",
            "给": "給",
            "点": "點",
            "现": "現",
            "兴": "興",
            "结": "結",
            "设": "設",
            "稳": "穩",
            "异": "異",
            "补": "補",
            "应": "應",
            "热": "熱",
            "语": "語",
            "区": "區",
            "尝": "嘗",
            "获": "獲",
            "节": "節",
            "类": "類",
            "乐": "樂",
            "别": "別",
            "冲": "沖",
            "轻": "輕",
            "识": "識",
            "杂": "雜",
            "说": "說",
            "么": "麼",
            "质": "質",
            "值": "值",
            "决": "決",
            "卖": "賣",
            "谁": "誰",
            "为": "為",
            "负": "負",
            "责": "責",
            "对": "對",
            "误": "誤",
            "画": "畫",
            "愿": "願",
            "记": "記",
            "输": "輸",
            "无": "無",
            "断": "斷",
            "声": "聲",
            "称": "稱",
            "间": "間",
            "源": "源",
            "请": "請",
            "项": "項",
            "强": "強",
            "历": "曆",
            "据": "據",
            "自": "自",
            "供": "供",
            "买": "買",
            "仅": "僅",
            "体": "體",
            "围": "圍",
            "频": "頻",
            "观": "觀",
            "众": "眾",
            "搜": "搜",
            "单": "單",
            "机": "機",
            "统": "統",
            "准": "準",
            "级": "級",
            "续": "續",
            "着": "著",
            "滤": "濾",
            "变": "變",
            "颜": "顏",
            "齐": "齊",
            "钢": "鋼",
            "张": "張",
            "样": "樣",
            "顶": "頂",
            "进": "進",
            "争": "爭",
            "条": "條",
            "备": "備",
            "钟": "鐘",
            "辑": "輯",
            "较": "較",
            "数": "數",
            "优": "優",
            "创": "創",
            "线": "線",
            "锁": "鎖",
            "链": "鏈",
            "表": "表",
        }
        raw = raw.translate(str.maketrans(character_replacements))
        for placeholder, value in placeholders.items():
            raw = raw.replace(placeholder, value)
        result = MarketingPlanResponse.model_validate_json(raw)
        result.strategy.platform_name = PLATFORM_NAMES["zh-HK"][request.platform]
        return result

    @staticmethod
    def _english(request: MarketingPlanRequest) -> MarketingPlanResponse:
        product = request.product_name
        origin = request.origin or "the local farm"
        points = _clean_points(request)
        platform_name = PLATFORM_NAMES["en"][request.platform]
        audience = request.audience or "people who care about seasonal food and farm stories"
        cta = "Comment “details” for specifications, price and delivery information"
        creative_routes = _creative_routes(request)
        angles: list[tuple[CreativeRouteId, str, str, str]] = [
            (
                "practical-hook",
                "Practical hook",
                f"Check this detail before choosing {product}",
                f"Do not choose {product} on price alone; check this detail first.",
            ),
            (
                "people-story",
                "People story",
                f"The step I will not skip when growing {product}",
                f"I grow {product} in {origin}, and this is the step I will not skip.",
            ),
            (
                "playful-contrast",
                "Playful contrast",
                f"This ordinary-looking {product} changes in the next shot",
                f"This ordinary-looking {product} may change your mind after cutting, brewing or packing.",
            ),
        ]
        videos: list[VideoScript] = []
        for index, (route_id, angle, title, hook) in enumerate(angles):
            point = points[index % len(points)]
            script = f"{hook} This season, our focus is {point}. {request.product_description.strip()} Show the real harvest, preparation or packing process instead of overproducing the scene. {cta}."
            shots = [
                Shot(
                    seconds="0–3s",
                    visual="Immediate close-up of the product",
                    voiceover=hook,
                    filming_tip="Shoot vertically and keep the first shot under three seconds",
                ),
                Shot(
                    seconds="3–12s",
                    visual="Origin, harvest or handling process",
                    voiceover=f"Our focus this season is {point}.",
                    filming_tip="Film an action rather than a static explanation",
                ),
                Shot(
                    seconds="12–24s",
                    visual="Cut-open, brewing, weighing or detail comparison",
                    voiceover=request.product_description.strip()[:120],
                    filming_tip="Use daylight and preserve the product's real color",
                ),
                Shot(
                    seconds="24–30s",
                    visual="Farmer on camera or packed product",
                    voiceover=cta,
                    filming_tip="End with one clear action",
                ),
            ]
            videos.append(
                VideoScript(
                    route_id=route_id,
                    angle=angle,
                    title=title,
                    cover_text=f"{product} · {point}",
                    hook=hook,
                    script=script,
                    background_music=[
                        "clean rhythmic explainer",
                        "warm piano with natural ambience",
                        "light playful rhythm with natural ambience",
                    ][index],
                    shots=shots,
                    call_to_action=cta,
                    quality_assessment=_video_quality_assessment(
                        request,
                        route_id,
                        hook=hook,
                        script=script,
                        shots=shots,
                        call_to_action=cta,
                    ),
                )
            )
        trend = (
            TrendBrief(
                trend_used=request.trend,
                integration_method="Borrow the trend's narrative structure for the opening, then return quickly to the product and farm.",
                caution="Do not copy controversy, invent participation or let the trend overpower the product.",
            )
            if request.trend
            else TrendBrief(
                trend_used="No live trend selected",
                integration_method="Start with reusable origin, product-difference and farmer-story formats; add a trend shortly before publishing.",
                caution="Trend relevance expires quickly and should be checked on the publishing day.",
            )
        )
        return MarketingPlanResponse(
            product_profile=ProductProfile(
                one_line_value=f"{product} from {origin}, explained through the real growing process and {points[0]}.",
                core_audience=audience,
                core_selling_points=points[:3],
                story_angle="Let the growing process, product detail and farmer voice carry the story instead of treating the product as an advertising prop.",
            ),
            strategy=PlatformStrategy(
                platform=request.platform,
                platform_name=platform_name,
                content_focus="Make the first three seconds specific, prove the point with visible detail, and end with one conversion action.",
                recommended_duration="25–40 seconds; up to 60 seconds for a farmer story",
                conversion_action=cta,
            ),
            trend=trend,
            creative_routes=creative_routes,
            topic_signals=_topic_signals(request),
            videos=videos,
            livestream=[
                LivestreamSection(
                    section="Opening",
                    talking_points=[
                        f"Show today's {product} immediately",
                        "State the origin and what viewers will learn",
                    ],
                ),
                LivestreamSection(
                    section="Product demonstration",
                    talking_points=[
                        f"Demonstrate {points[0]}, {points[1]} and {points[2]}",
                        "Pair each claim with a visible detail",
                    ],
                ),
                LivestreamSection(
                    section="Trust",
                    talking_points=[
                        "Explain one real growing decision",
                        "Show harvest, grading or packing",
                        "Do not promise information that is not confirmed",
                    ],
                ),
                LivestreamSection(
                    section="Conversion",
                    talking_points=[
                        "Clarify specifications, price, dispatch and service",
                        "Use one comment or message keyword",
                        "Repeat who the product is best for",
                    ],
                ),
                LivestreamSection(
                    section="Questions",
                    talking_points=[
                        "Taste and serving ideas",
                        "Storage guidance",
                        "Delivery and arrival handling",
                    ],
                ),
            ],
            seven_day_plan=[
                DailyPlan(
                    day=1,
                    objective="Introduce the product",
                    content=f"Publish “{angles[0][2]}”",
                    action="Record completion rate and recurring comments",
                ),
                DailyPlan(
                    day=2,
                    objective="Explain the difference",
                    content=f"Publish “{angles[1][2]}”",
                    action="Add comment questions to the live Q&A",
                ),
                DailyPlan(
                    day=3,
                    objective="Build personal trust",
                    content=f"Publish “{angles[2][2]}”",
                    action="Pin one concrete growing detail",
                ),
                DailyPlan(
                    day=4,
                    objective="Invite interaction",
                    content=f"Ask how people choose or use {product}",
                    action="Reply to at least ten useful comments",
                ),
                DailyPlan(
                    day=5,
                    objective="Prepare the live session",
                    content="Show packing, stock preparation or a live preview",
                    action="State the live time and featured specification",
                ),
                DailyPlan(
                    day=6,
                    objective="Convert demand",
                    content=f"Run a 30–60 minute {product} live session",
                    action="Record common questions and conversion moments",
                ),
                DailyPlan(
                    day=7,
                    objective="Review and reuse",
                    content="Cut the strongest Q&A moments from the live session",
                    action="Keep strong openings and rewrite weaker scripts",
                ),
            ],
            next_actions=[
                "Confirm price, specifications and stock",
                "Film origin and product details",
                "Choose one script and follow its shot list",
                "Record publishing data for the next iteration",
            ],
            next_step=_next_step(request),
            provider="",
            model="",
            latency_ms=0,
        )


SYSTEM_PROMPT = """You are Heyu AI, a farmer-first agricultural marketing strategist.
Create a practical plan that a farmer can film with a phone. Never invent product
facts, certifications, prices, medical effects, stock or trend data. Return one
JSON object that strictly matches the supplied schema. Produce exactly three
selectable creative routes (practical hook, people story and playful contrast),
one video and a structured quality assessment for each route, three explainable
topic signals (manual input, seasonal farming and evergreen pain point), and seven
daily actions. Topic signals are planning aids, never claims of real-time popularity.
End with a contextual route-selection, shoot-preparation and publication-record
workflow. Keep the requested locale natural and adapt the content to the selected
Chinese social platform."""


class OpenAICompatibleMarketingProvider:
    name = "openai-compatible"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.ai_model
        prompt_hash = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16]
        self.cache_namespace = (
            f"marketing-v2:{self.name}:{self.model}:"
            f"{settings.ai_base_url.rstrip('/')}:{prompt_hash}"
        )

    def generate(self, request: MarketingPlanRequest) -> MarketingPlanResponse:
        started = time.perf_counter()
        endpoint = self.settings.ai_base_url.rstrip("/") + "/chat/completions"
        schema = MarketingPlanResponse.model_json_schema()
        payload = {
            "model": self.model,
            "temperature": 0.55,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "request": request.model_dump(),
                            "required_response_schema": schema,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.settings.ai_api_key}"},
                json=payload,
                timeout=self.settings.ai_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Model response body must be an object")
            choices = body.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError("Model response did not include choices")
            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                raise ValueError("Model choice must be an object")
            message = first_choice.get("message")
            if not isinstance(message, dict):
                raise ValueError("Model choice did not include a message")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Model message content must be non-empty text")
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
                content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("Model content must decode to a JSON object")
            parsed.update(
                {
                    "provider": self.name,
                    "model": self.model,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                }
            )
            return MarketingPlanResponse.model_validate(parsed)
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            AttributeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise MarketingProviderError("Marketing model returned an invalid response") from exc


def get_marketing_provider(settings: Settings | None = None) -> MarketingPlanProvider:
    settings = settings or get_settings()
    if settings.ai_provider.strip().lower() == "openai-compatible":
        return OpenAICompatibleMarketingProvider(settings)
    return DeterministicMarketingProvider()


def _cache_key(provider: MarketingPlanProvider, request: MarketingPlanRequest) -> str:
    payload = request.model_dump_json(exclude_none=True)
    namespace = getattr(provider, "cache_namespace", f"{provider.name}:{provider.model}")
    raw = f"{namespace}\n{payload}".encode()
    return hashlib.sha256(raw).hexdigest()


def _fallback_notice(locale: Locale) -> str:
    return {
        "zh-CN": "模型服务暂时不可用，本次已自动切换为零成本稳定方案；请在正式发布前复核表达。",
        "zh-HK": "模型服務暫時不可用，本次已自動切換為零成本穩定方案；請在正式發佈前覆核表達。",
        "en": (
            "The configured model is temporarily unavailable. Heyu switched to the "
            "stable zero-cost plan; review the wording before publishing."
        ),
    }[locale]


def generate_marketing_preview(request: MarketingPlanRequest) -> MarketingPlanResponse:
    """Always-free preview used by the public/local demo."""
    return DeterministicMarketingProvider().generate(request)


def generate_marketing_plan(request: MarketingPlanRequest) -> MarketingPlanResponse:
    """Generate with cache reuse and an explicit deterministic degradation path."""
    settings = get_settings()
    provider = get_marketing_provider(settings)
    key = _cache_key(provider, request)
    cached = _marketing_cache.get(key)
    if cached is not None:
        return cached

    try:
        result = provider.generate(request)
    except MarketingProviderError:
        if not settings.marketing_fallback_to_mock:
            raise
        result = DeterministicMarketingProvider().generate(request)
        result.provider = "mock-fallback"
        result.degraded = True
        result.notice = _fallback_notice(request.locale)

    if not result.degraded:
        _marketing_cache.put(
            key,
            result,
            ttl_seconds=settings.marketing_cache_ttl_seconds,
            max_entries=settings.marketing_cache_max_entries,
        )
    return result.model_copy(deep=True)
