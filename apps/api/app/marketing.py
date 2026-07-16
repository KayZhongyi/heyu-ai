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
from datetime import datetime
from typing import Annotated, Literal, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import Settings, get_settings
from app.script_quality import evaluate_script_quality

Locale = Literal["zh-CN", "zh-HK", "en"]
Platform = Literal["douyin", "xiaohongshu", "wechat-channels", "kuaishou"]
CreativeRouteId = Literal["practical-hook", "people-story", "playful-contrast"]
TopicSignalType = Literal["manual-hotspot", "seasonal-farming", "evergreen-pain-point"]
Recommendation = Literal["recommended", "consider", "skip"]
MarketingContentModule = Literal["videos", "livestream", "calendar"]
Goal = Literal[
    "sell",
    "build-brand",
    "gain-followers",
    "promote-tourism",
    "recruit-agents",
]


def _default_goals() -> list[Goal]:
    return ["sell"]


def _default_content_modules() -> list[MarketingContentModule]:
    return ["videos", "livestream", "calendar"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


SellingPoint = Annotated[str, Field(min_length=1, max_length=80)]
TrendSourceType = Literal[
    "manual",
    "rss",
    "atom",
    "douyin-open-platform",
    "seasonal",
    "evergreen",
]

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


class TrendSnapshot(StrictModel):
    """The exact discovery result selected for this plan."""

    title: str = Field(min_length=1, max_length=240)
    source_url: str | None = Field(default=None, max_length=2048)
    source_label: str = Field(min_length=1, max_length=120)
    source_type: TrendSourceType
    published_at: datetime | None = None
    captured_at: datetime
    fit_score: int = Field(ge=0, le=100)
    recommendation: Recommendation
    recommendation_reason: str = Field(min_length=1, max_length=1000)


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
    trend_snapshot: TrendSnapshot | None = None
    content_modules: list[MarketingContentModule] = Field(
        default_factory=_default_content_modules,
        min_length=1,
        max_length=3,
    )

    @model_validator(mode="after")
    def normalize_and_reject_high_risk_claims(self) -> MarketingPlanRequest:
        self.goals = list(dict.fromkeys(self.goals))
        self.content_modules = list(dict.fromkeys(self.content_modules))
        self.selling_points = [point.strip() for point in self.selling_points if point.strip()]
        if self.trend_snapshot is not None:
            if self.trend and self.trend != self.trend_snapshot.title:
                raise ValueError("trend must match trend_snapshot.title")
            self.trend = self.trend_snapshot.title
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
    videos: list[VideoScript] = Field(default_factory=list, max_length=3)
    livestream: list[LivestreamSection] = Field(default_factory=list, max_length=8)
    seven_day_plan: list[DailyPlan] = Field(default_factory=list, max_length=7)
    included_modules: list[MarketingContentModule] = Field(
        default_factory=_default_content_modules,
        min_length=1,
        max_length=3,
    )
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
        self.included_modules = list(dict.fromkeys(self.included_modules))
        expected_presence = {
            "videos": bool(self.videos),
            "livestream": bool(self.livestream),
            "calendar": bool(self.seven_day_plan),
        }
        for module, present in expected_presence.items():
            if (module in self.included_modules) != present:
                raise ValueError(f"{module} presence must match included_modules")
        if self.seven_day_plan and [item.day for item in self.seven_day_plan] != list(range(1, 8)):
            raise ValueError("seven_day_plan must contain ordered days 1 through 7")
        route_ids = [item.route_id for item in self.creative_routes]
        video_route_ids = [item.route_id for item in self.videos]
        if route_ids != ["practical-hook", "people-story", "playful-contrast"]:
            raise ValueError("creative_routes must contain the three supported routes in order")
        if self.videos:
            normalized_angles = {item.angle.strip().casefold() for item in self.videos}
            normalized_titles = {item.title.strip().casefold() for item in self.videos}
            if len(normalized_angles) != 3 or len(normalized_titles) != 3:
                raise ValueError("videos must contain three distinct angles and titles")
            if video_route_ids != route_ids:
                raise ValueError("videos must map one-to-one to creative_routes")
        if [item.signal_type for item in self.topic_signals] != [
            "manual-hotspot",
            "seasonal-farming",
            "evergreen-pain-point",
        ]:
            raise ValueError("topic_signals must contain manual, seasonal and evergreen signals")
        return self


MarketingRegenerationTarget = Literal["video", "livestream", "calendar"]


class MarketingModuleRegenerationRequest(StrictModel):
    request: MarketingPlanRequest
    current_plan: MarketingPlanResponse
    target: MarketingRegenerationTarget
    route_id: CreativeRouteId | None = None
    instruction: str = Field(default="", max_length=400)
    variation_index: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def validate_target_is_available(self) -> MarketingModuleRegenerationRequest:
        expected_modules = list(self.current_plan.included_modules)
        if self.request.content_modules != expected_modules:
            raise ValueError("request content_modules must match current_plan included_modules")
        if self.target == "video":
            if "videos" not in expected_modules:
                raise ValueError("videos must be included before regenerating a video")
            if self.route_id is None:
                raise ValueError("route_id is required when target is video")
            if self.route_id not in {item.route_id for item in self.current_plan.videos}:
                raise ValueError("route_id is not present in current_plan videos")
        else:
            if self.route_id is not None:
                raise ValueError("route_id is only supported when target is video")
            required_module: MarketingContentModule = (
                "livestream" if self.target == "livestream" else "calendar"
            )
            if required_module not in expected_modules:
                raise ValueError(f"{required_module} must be included before regeneration")
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


def _short_product_fact(description: str, *, limit: int = 72) -> str:
    """Keep one supplied fact short enough for a single 8–20 second voiceover."""
    normalized = " ".join(description.split())
    first_sentence = re.split(r"(?<=[。！？.!?])\s*", normalized, maxsplit=1)[0]
    if len(first_sentence) <= limit:
        return first_sentence
    return first_sentence[: limit - 1].rstrip("，,；;。.!！?？ ") + "。"


@dataclass(frozen=True)
class ProductFilmContext:
    """Concrete visual actions that can be filmed with one phone."""

    decision_detail: str
    practical_hook: str
    evidence_sentence: str
    proof_action: str
    process_action: str
    story_hook: str
    story_opening: str
    story_steps: str
    contrast_action: str
    use_scene: str


def _product_film_language(request: MarketingPlanRequest) -> ProductFilmContext:
    """Infer product-specific, phone-filmable actions from all supplied facts."""
    product_name = request.product_name
    normalized = " ".join(
        (
            product_name,
            request.product_description,
            *request.selling_points,
        )
    ).casefold()
    if any(token in normalized for token in ("百香果", "熱情果", "热情果", "passion fruit")):
        return ProductFilmContext(
            decision_detail="果皮颜色、切面和果肉汁水",
            practical_hook="这两颗{product}，哪一颗更适合现在吃？先别猜，切开看果肉和汁水。",
            evidence_sentence="把不同成熟度的果实放在一起，先看果皮颜色，再切开、挖出果肉，观察香气和汁水状态。",
            proof_action="同框拍两颗不同成熟度的百香果，依次切开、挖出果肉，再倒入冰水或气泡水",
            process_action="跟拍果园采摘、轻放入筐、分级和装箱，最后切开一颗展示果肉",
            story_hook="这颗{product}颜色已经很好看了，我们为什么还要等到今天才摘？",
            story_opening="果园里的果实占满画面，农户摘下一颗、切开，并同步说出第一句话",
            story_steps="果园采摘、成熟度判断还是百香果气泡饮",
            contrast_action="左边放刚转色的果实，右边放自然成熟的果实；先让观众选择，再切开对比果肉和汁水",
            use_scene="直接挖着吃、加入冰水或气泡水的夏日场景",
        )
    if any(token in normalized for token in ("番茄", "西红柿", "tomato")):
        return ProductFilmContext(
            decision_detail="果蒂、果肩和成熟度",
            practical_hook="这两颗{product}，你会先拿哪一颗？别只看红不红，先看果蒂和果肩。",
            evidence_sentence="把两颗成熟度不同的番茄放在一起，看果蒂、果肩，再切开看果肉和汁水。",
            proof_action="把两颗成熟度不同的番茄并排，从果蒂扫到果肩，再切开拍果肉和汁水",
            process_action="用近景跟拍采摘、轻放入筐和分选动作，让种植者边做边讲",
            story_hook="别人摘下来就直接装筐，我们为什么还要把这一筐{product}重新挑一遍？",
            story_opening="一筐番茄占满画面，种植者拿起其中一颗重新分选，并同步说出第一句话",
            story_steps="采摘、分选还是装筐",
            contrast_action="同框放一颗外形规整和一颗外形普通的番茄，先让观众选，再切开对比",
            use_scene="鲜食、做菜或家庭餐桌",
        )
    if any(token in normalized for token in ("茶", "tea", "oolong")):
        return ProductFilmContext(
            decision_detail="干茶、第一遍出汤和叶底",
            practical_hook="同样是这批{product}，为什么第一遍出汤差这么多？先看干茶和叶底。",
            evidence_sentence="不急着听香气描述，先看干茶、第一遍出汤和泡开后的叶底。",
            proof_action="固定机位拍投茶、注水、第一遍出汤，再给叶底一个近景",
            process_action="用近景跟拍采青、摊晾或冲泡中的一个连续动作，让制茶人边做边讲一个真实工序",
            story_hook="这批{product}已经能继续做了，我们为什么还要多等这一段摊晾？",
            story_opening="摊晾中的茶叶铺满画面，制茶人翻动茶叶并同步说出第一句话",
            story_steps="采青、摊晾还是冲泡",
            contrast_action="先拍不起眼的干茶，再用同一机位切到舒展后的叶底和茶汤",
            use_scene="日常冲泡、办公室或朋友分享",
        )
    if any(
        token in normalized
        for token in (
            "水果",
            "果园",
            "果肉",
            "荔枝",
            "柑",
            "橙",
            "桃",
            "梨",
            "莓",
            "芒果",
            "菠萝",
            "凤梨",
            "fruit",
            "lychee",
            "mango",
        )
    ):
        return ProductFilmContext(
            decision_detail="成熟度、果面和装箱分层",
            practical_hook="这两份{product}看起来都漂亮，哪一份更适合今天吃？先看成熟度和装箱分层。",
            evidence_sentence="先看同一批果实的成熟度和完整度，再看分级、搭配和装箱是否对应食用时间。",
            proof_action="从果面近景拍到称重、切开和装箱，尤其展示最底下一层",
            process_action="用近景跟拍采收、分级、搭配和装箱，让农户边做边讲为什么这样分",
            story_hook="明明这颗{product}更漂亮，装箱时我们为什么把它放到另一组？",
            story_opening="农户从两组水果中拿起一颗重新分级，并同步说出第一句话",
            story_steps="采收、分级、搭配还是装箱",
            contrast_action="把外形更漂亮和更适合现在吃的两份放在一起，请观众先选再揭晓判断方法",
            use_scene="家庭分享、送礼或当季鲜食",
        )
    if any(
        token in normalized
        for token in ("大米", "稻米", "小米", "杂粮", "豆", "菌", "菇", "rice", "grain")
    ):
        return ProductFilmContext(
            decision_detail="颗粒、淘洗水和煮熟后的状态",
            practical_hook="同样一把{product}，下锅前先看哪一点？摊开、淘洗，再看颗粒状态。",
            evidence_sentence="先把产品摊开放大拍颗粒和纹理，再淘洗、浸泡或煮制，展示前后变化。",
            proof_action="抓取一把产品摊在深色盘中，近拍颗粒，再拍淘洗和煮熟后的状态",
            process_action="跟拍晾晒、筛选、称重和装袋中的一个连续动作，让农户边做边讲",
            story_hook="这批{product}已经筛过一遍了，我们为什么装袋前还要再看一次？",
            story_opening="农户把一把产品摊开在掌心，随后倒入筛盘并同步说出第一句话",
            story_steps="晾晒、筛选还是煮制效果",
            contrast_action="把两份颗粒并排，先让观众选，再通过淘洗或煮制后的状态揭晓差别",
            use_scene="家庭主食、煲粥或日常备餐",
        )
    return ProductFilmContext(
        decision_detail="一个能在镜头里看见的产品细节",
        practical_hook=f"这两份{product_name}，你会先选哪一份？别只看第一眼，先看一个能拍出来的细节。",
        evidence_sentence="先把卖点换成一个能拍到的细节，再用同一件产品的动作或前后状态证明。",
        proof_action="把卖点对应的实物、动作或前后状态放在同一画面里",
        process_action="用近景跟拍采收、处理或装箱，让农户边做边讲一个真实决定",
        story_hook=f"同样是{product_name}，我们为什么还要多做这一步？",
        story_opening=f"{product_name}占满画面，农户拿起产品开始处理，并同步说出第一句话",
        story_steps="采收、处理还是装箱",
        contrast_action="把两种常见选择并排，请观众先选，再用现场细节解释差别",
        use_scene="家庭消费和日常使用",
    )


def _short_trend_angle(trend: str, *, limit: int = 28) -> str:
    """Keep a trend phrase natural enough to say in the opening seconds."""
    normalized = " ".join(trend.split()).strip("“”\"' ")
    candidates = [
        item.strip(" ：:，,、｜|—-")
        for item in re.split(r"[：:｜|；;。!?！？\n]", normalized)
        if item.strip(" ：:，,、｜|—-")
    ]
    useful = next((item for item in candidates if 4 <= len(item) <= limit), "")
    selected = useful or normalized
    if len(selected) > limit:
        selected = selected[:limit].rstrip("，,、；;：: ")
    return selected or trend


def _simplified_bgm_directions(platform: Platform) -> dict[str, str]:
    platform_search = {
        "douyin": "轻快乡村、无歌词、强节拍",
        "xiaohongshu": "清新生活、无歌词、轻木吉他",
        "wechat-channels": "温暖纪实、无歌词、自然感",
        "kuaishou": "轻快生活、无歌词、真实感",
    }[platform]
    return {
        "practical-hook": (
            f"剪映搜索“{platform_search}”；开场0–3秒保留现场声，第4秒进入92–104 BPM；"
            "音乐音量约25%，口播时压低到8%，结尾问题前留半拍"
        ),
        "people-story": (
            f"剪映搜索“{platform_search}”；开场先收种植或制作现场声，人物第一句话后进入68–82 BPM；"
            "音乐音量约18%，口播时压低到6%，人物停顿处不要补满"
        ),
        "playful-contrast": (
            f"剪映搜索“{platform_search}”；开场0–2秒用两个清楚节拍，揭晓时短暂停顿后进入100–112 BPM；"
            "音乐音量约28%，口播时压低到8%，答案揭晓后再恢复"
        ),
    }


def _simplified_video_blueprints(
    request: MarketingPlanRequest,
    points: list[str],
) -> list[dict[str, str]]:
    """Build three genuinely different story engines instead of three rewrites."""
    product = request.product_name
    origin = request.origin or "本地农场"
    film = _product_film_language(request)
    music = _simplified_bgm_directions(request.platform)
    practical_cta = f"你挑{product}最先看哪一点？把你的判断留在评论区。"
    story_cta = f"你更想看{film.story_steps}？留言选一个，下一条带你看。"
    contrast_cta = "你刚才选对了吗？把你选这一边的理由留在评论区。"
    blueprints = [
        {
            "route_id": "practical-hook",
            "angle": "实用吸睛",
            "title": f"{product}怎么挑？先看{film.decision_detail}",
            "cover_text": f"挑{product}先看这里",
            "hook": film.practical_hook.format(product=product),
            "opening_visual": f"{product}清楚入镜；用极近景拍{film.decision_detail}，手指直接指出要看的位置",
            "bridge": film.evidence_sentence,
            "proof_visual": film.proof_action,
            "proof_voice": (
                f"先看{film.decision_detail}，再看镜头里的变化；"
                f"我们这批{product}最想讲清的是{points[0]}。"
            ),
            "context_visual": f"把{product}放进{film.use_scene}的真实使用场景",
            "context_voice": request.product_description.strip(),
            "music": music["practical-hook"],
            "cta": practical_cta,
        },
        {
            "route_id": "people-story",
            "angle": "人物故事",
            "title": f"做{product}，我们为什么一直保留这一步",
            "cover_text": f"{product}背后的一个决定",
            "hook": film.story_hook.format(product=product),
            "opening_visual": f"{product}清楚入镜；{film.story_opening}",
            "bridge": f"在{origin}，“{points[1]}”不是一句卖点，它就在每天的操作里。",
            "proof_visual": film.process_action,
            "proof_voice": (
                f"现在做的每一步都能在现场看见；我们保留它，是因为它直接关系到{points[1]}。"
            ),
            "context_visual": "手部动作、人物表情和产地环境交替出现，最后回到产品近景",
            "context_voice": request.product_description.strip(),
            "music": music["people-story"],
            "cta": story_cta,
        },
        {
            "route_id": "playful-contrast",
            "angle": "轻松反差",
            "title": f"只看外表挑{product}，你可能会选错",
            "cover_text": "你会选左边还是右边？",
            "hook": f"先别告诉我答案：左边和右边这两份{product}，你会选哪一份？",
            "opening_visual": f"左右两份{product}同时入镜，画面中央出现两秒倒计时",
            "bridge": f"先选，不急着听答案；真正要看的，是和“{points[2]}”有关的现场细节。",
            "proof_visual": film.contrast_action,
            "proof_voice": (f"别只看第一眼，刚才容易忽略的细节，正好能说明{points[2]}。"),
            "context_visual": "用手指向左右两组产品，揭晓后快速回放刚才容易忽略的细节",
            "context_voice": request.product_description.strip(),
            "music": music["playful-contrast"],
            "cta": contrast_cta,
        },
    ]
    trend = request.trend.strip()
    if trend:
        trend_angle = trend
        for prefix in (f"{product}：", f"{product}:", f"{product}｜", f"{product}|"):
            if trend_angle.startswith(prefix):
                trend_angle = trend_angle[len(prefix) :].strip()
                break
        for suffix in ("怎么拍", "怎麼拍", "如何拍"):
            if trend_angle.endswith(suffix):
                trend_angle = trend_angle[: -len(suffix)].strip()
                break
        trend_angle = _short_trend_angle(trend_angle or trend)
        blueprints[0]["bridge"] = (
            f"借“{trend_angle}”这个切口，先把{product}放在镜头前做一个具体选择："
            f"{film.evidence_sentence}"
        )
        blueprints[1]["bridge"] = (
            f"趁大家在关注“{trend_angle}”，把镜头拉回{origin}："
            f"“{points[1]}”就藏在眼前这一步真实操作里。"
        )
        blueprints[2]["bridge"] = (
            f"围绕“{trend_angle}”先做一个更实在的选择题：这两份{product}你会选哪份？"
            f"答案藏在和“{points[2]}”有关的现场细节里。"
        )
    return blueprints


def _english_video_blueprints(
    request: MarketingPlanRequest,
    points: list[str],
) -> list[dict[str, str]]:
    product = request.product_name
    origin = request.origin or "the local farm"
    trend = request.trend.strip()
    blueprints = [
        {
            "route_id": "practical-hook",
            "angle": "Practical hook",
            "title": f"How to choose {product}: one detail to check first",
            "cover_text": f"Check this before buying {product}",
            "hook": f"Before choosing {product}, can you spot which visible detail proves the difference?",
            "opening_visual": f"Extreme close-up of two {product} samples; point to one visible difference",
            "bridge": f"Use one simple side-by-side check to test whether “{points[0]}” is visible.",
            "proof_visual": f"Place two {product} samples side by side, then cut, weigh or turn them to reveal the relevant detail",
            "proof_voice": f"Start with what viewers can see, then connect that evidence to {points[0]}.",
            "context_visual": f"Show {product} in a real family-use scene rather than on an empty display table",
            "music": "Keep natural sound for the first 3 seconds; bring in a clean 92–104 BPM beat at second 4 and lower it under the explanation",
            "cta": f"What do you check first when choosing {product}? Comment your answer; use “details” for size and delivery information.",
        },
        {
            "route_id": "people-story",
            "angle": "People story",
            "title": f"The decision behind this batch of {product}",
            "cover_text": "One decision behind the product",
            "hook": f"The hardest part of explaining {product} is not saying it is good—it is showing why we keep this step.",
            "opening_visual": "The grower's hands perform the key task while the first sentence is spoken",
            "bridge": f"Follow the grower at {origin} through one real action connected to {points[1]}.",
            "proof_visual": "Track harvesting, sorting or packing in one continuous action, keeping the grower in frame",
            "proof_voice": f"Name the action on screen and explain how it connects to {points[1]}, without switching to advertising slogans.",
            "context_visual": "Alternate hands, facial expression and the growing environment, then return to a product close-up",
            "music": "Open on farm ambience; add warm acoustic guitar or piano at 68–82 BPM after the first sentence, always below the voice",
            "cta": "Which should we film next—harvesting, sorting or packing? Choose one in the comments.",
        },
        {
            "route_id": "playful-contrast",
            "angle": "Playful contrast",
            "title": f"The appearance test most {product} shoppers get wrong",
            "cover_text": "Left or right?",
            "hook": f"Do not answer yet: which of these two {product} would you choose, left or right?",
            "opening_visual": f"Bring two {product} options into frame together and show a two-second choice countdown",
            "bridge": f"The reveal uses a visible detail connected to {points[2]}, not an exaggerated twist.",
            "proof_visual": "Hold both options side by side, pause for the choice, then cut, turn or unpack them to reveal the evidence",
            "proof_voice": f"Let viewers choose first, then point out the visible detail connected to {points[2]}.",
            "context_visual": "Point to the left and right options, reveal the answer, then replay the detail viewers may have missed",
            "music": "Use two clear beats for the opening choice; pause at the reveal, then enter a light 100–112 BPM rhythm",
            "cta": "Left or right—which did you choose? Comment before the reveal, then compare your reason with ours.",
        },
    ]
    if trend:
        blueprints[2]["bridge"] = (
            f"Use the choice-and-reveal structure of “{trend}”, but return to {product} "
            f"within three seconds and explain the answer through {points[2]}."
        )
    return blueprints


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
    background_music: str,
) -> VideoQualityAssessment:
    evaluation = evaluate_script_quality(
        product_name=request.product_name,
        trend=request.trend,
        hook=hook,
        script=script,
        shots=shots,
        cta=call_to_action,
        bgm=background_music,
    )
    detailed_scores = evaluation["scores"]
    hook_score = round(
        (
            detailed_scores["hook_product"]
            + detailed_scores["hook_structure"]
            + detailed_scores["opening_0_3"]
        )
        / 3
    )
    factual_score = round(
        (
            detailed_scores["visual_proof_3_8"]
            + detailed_scores["voice_visual_alignment"]
            + detailed_scores["specificity"]
        )
        / 3
    )
    platform_baseline = {
        "douyin": 90,
        "xiaohongshu": 88 if route_id == "practical-hook" else 86,
        "wechat-channels": 90 if route_id == "people-story" else 84,
        "kuaishou": 88,
    }[request.platform]
    platform_score = round(
        (
            platform_baseline
            + detailed_scores["bgm_direction"]
            + detailed_scores["trend_integration"]
        )
        / 3
    )
    filmability_score = detailed_scores["filmability"]
    interaction_score = detailed_scores["cta_interaction"]
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
    issue_messages = {
        "hook_missing_product": _text(
            request.locale,
            f"开头直接说出{request.product_name}，不要让观众猜正在讲什么。",
            f"開頭直接說出{request.product_name}，不要讓觀眾猜正在講甚麼。",
            f"Name {request.product_name} in the opening so viewers know the subject immediately.",
        ),
        "hook_weak_question": _text(
            request.locale,
            "把开头改成一个具体选择、反差或结果，不只提出宽泛问题。",
            "把開頭改成一個具體選擇、反差或結果，不只提出寬泛問題。",
            "Turn the opening into a concrete choice, contrast or result instead of a broad question.",
        ),
        "hook_no_tension": _text(
            request.locale,
            "前三秒加入明确问题、选择、反差或结果，让观众有继续看的理由。",
            "首三秒加入明確問題、選擇、反差或結果，讓觀眾有繼續看的理由。",
            "Add a clear problem, choice, contrast or result in the first three seconds.",
        ),
        "opening_product_not_visible": _text(
            request.locale,
            f"0—3秒让{request.product_name}直接入镜，并与第一句话同步出现。",
            f"0—3秒讓{request.product_name}直接入鏡，並與第一句話同步出現。",
            f"Show {request.product_name} on screen in 0–3 seconds as the first line begins.",
        ),
        "opening_no_action": _text(
            request.locale,
            "开场加入手指指出、切开、对比或拿起等一个可见动作。",
            "開場加入手指指出、切開、對比或拿起等一個可見動作。",
            "Add one visible opening action such as pointing, cutting, comparing or picking up.",
        ),
        "proof_shot_missing": _text(
            request.locale,
            "补充3—8秒证据镜头，用近景或对比证明开场提出的问题。",
            "補充3—8秒證據鏡頭，用近鏡或對比證明開場提出的問題。",
            "Add a 3–8 second proof shot using a close-up or comparison.",
        ),
        "proof_not_visual": _text(
            request.locale,
            "3—8秒不要只讲结论，要拍到近景、对比、测量或真实操作。",
            "3—8秒不要只講結論，要拍到近鏡、對比、量度或真實操作。",
            "Use a close-up, comparison, measurement or real action in the 3–8 second proof.",
        ),
        "voice_visual_mismatch": _text(
            request.locale,
            "逐镜检查口播与画面：说到哪个细节，镜头就展示哪个细节。",
            "逐鏡檢查口播與畫面：說到哪個細節，鏡頭就展示哪個細節。",
            "Align every spoken detail with the same visible detail in that shot.",
        ),
        "cta_not_interactive": _text(
            request.locale,
            "结尾只保留一个具体互动动作，例如评论选择、回答问题或收藏。",
            "結尾只保留一個具體互動行動，例如留言選擇、回答問題或收藏。",
            "End with one specific action such as choosing in comments, answering or saving.",
        ),
        "bgm_incomplete_direction": _text(
            request.locale,
            "补充可搜索的音乐类型、进入时机，以及口播时降低音量的位置。",
            "補充可搜尋的音樂類型、進入時機，以及口播時降低音量的位置。",
            "Specify a searchable music style, entry point and where to lower it under speech.",
        ),
        "trend_not_integrated": _text(
            request.locale,
            "不要只贴热点名称；用热点建立选择或讨论，并在三秒内回到产品。",
            "不要只貼熱點名稱；用熱點建立選擇或討論，並在三秒內回到產品。",
            "Use the trend to frame a choice or discussion, then return to the product within three seconds.",
        ),
        "generic_ad_copy": _text(
            request.locale,
            "把空泛形容词换成观众能在镜头里看到的事实或动作。",
            "把空泛形容詞換成觀眾能在鏡頭裡看到的事實或動作。",
            "Replace generic promotion with a fact or action viewers can see.",
        ),
        "high_resource_shoot": _text(
            request.locale,
            "把高门槛拍摄改成手机、现有场地和一人可完成的镜头。",
            "把高門檻拍攝改成手機、現有場地和一人可完成的鏡頭。",
            "Replace high-threshold production with shots one person can film by phone on site.",
        ),
        "too_many_shots": _text(
            request.locale,
            "把镜头收敛到3—6个，优先保留开场、证据、解释和互动。",
            "把鏡頭收斂到3—6個，優先保留開場、證據、解釋和互動。",
            "Reduce the plan to 3–6 shots covering opening, proof, explanation and interaction.",
        ),
    }
    improvements = [
        issue_messages[issue["code"]]
        for issue in evaluation["issues"]
        if issue["code"] in issue_messages
    ]
    improvements = list(dict.fromkeys(improvements))[:3]
    if not improvements:
        improvements = [
            _text(
                request.locale,
                "发布后记录三秒留存、完播和有效评论，用真实反馈调整下一条开场。",
                "發佈後記錄三秒留存、完播和有效留言，用真實回饋調整下一條開場。",
                "After publishing, use three-second retention, completion and useful comments to refine the next opening.",
            )
        ]
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
        improvements=improvements,
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
    model = "farmer-marketing-v2"

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
        creative_routes = _creative_routes(request)
        blueprints = _simplified_video_blueprints(request, points)
        videos: list[VideoScript] = []
        for blueprint in blueprints:
            route_id = blueprint["route_id"]
            if route_id not in ("practical-hook", "people-story", "playful-contrast"):
                raise ValueError("unsupported deterministic creative route")
            typed_route_id = cast(CreativeRouteId, route_id)
            hook = blueprint["hook"]
            cta = blueprint["cta"]
            proof_voice = " ".join(
                part
                for part in (
                    blueprint["proof_voice"],
                    _short_product_fact(request.product_description),
                )
                if part
            )
            shots = [
                Shot(
                    seconds="0–3秒",
                    visual=blueprint["opening_visual"],
                    voiceover=hook,
                    filming_tip="手机竖拍；第一句话和第一动作同时发生，3秒内必须出现产品",
                ),
                Shot(
                    seconds="3–8秒",
                    visual=blueprint["proof_visual"],
                    voiceover=blueprint["bridge"],
                    filming_tip="只拍一个连续动作，用近景证明刚才提出的问题",
                ),
                Shot(
                    seconds="8–20秒",
                    visual=blueprint["context_visual"],
                    voiceover=proof_voice,
                    filming_tip="口播说到哪个细节，画面就切到哪个细节；不要用无关空镜",
                ),
                Shot(
                    seconds="20–30秒",
                    visual=f"回到{product}近景；屏幕只保留一个问题和一个行动词",
                    voiceover=cta,
                    filming_tip="说完问题后停一秒，让观众有时间选择或评论",
                ),
            ]
            script = " ".join(shot.voiceover.strip() for shot in shots if shot.voiceover.strip())
            videos.append(
                VideoScript(
                    route_id=typed_route_id,
                    angle=blueprint["angle"],
                    title=blueprint["title"],
                    cover_text=blueprint["cover_text"],
                    hook=hook,
                    script=script,
                    background_music=blueprint["music"],
                    shots=shots,
                    call_to_action=cta,
                    quality_assessment=_video_quality_assessment(
                        request,
                        typed_route_id,
                        hook=hook,
                        script=script,
                        shots=shots,
                        call_to_action=cta,
                        background_music=blueprint["music"],
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
                content_focus="前三秒提出具体问题或选择，中段立刻给视觉证据，结尾用一个评论动作承接互动。",
                recommended_duration="25–40秒；人物故事可延长至60秒",
                conversion_action="先用评论问题承接互动，再按所选路线引导规格咨询、下一条内容或直播。",
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
                    content=f"发布“{blueprints[0]['title']}”实用视频",
                    action="记录完播率与高频评论",
                ),
                DailyPlan(
                    day=2,
                    objective="解释产品差异",
                    content=f"发布“{blueprints[1]['title']}”人物视频",
                    action="把评论问题加入直播问答",
                ),
                DailyPlan(
                    day=3,
                    objective="建立人物信任",
                    content=f"发布“{blueprints[2]['title']}”反差视频",
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
            "会": "會",
            "错": "錯",
            "边": "邊",
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
            "形容词": "形容詞",
            "分层": "分層",
            "解释": "解釋",
            "必须": "必須",
            "还是": "還是",
            "刚才": "剛才",
            "揭晓": "揭曉",
            "停顿": "停頓",
            "制造": "製造",
            "环境": "環境",
            "关系": "關係",
            "结论": "結論",
            "检查": "檢查",
            "开头": "開頭",
            "宽泛": "寬泛",
            "脚本": "腳本",
            "没有": "沒有",
            "实时": "實時",
            "搜索": "搜尋",
            "温暖": "溫暖",
            "歌词": "歌詞",
            "压低": "壓低",
            "恢复": "恢復",
            "记忆": "記憶",
            "测量": "測量",
            "讨论": "討論",
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
            "两": "兩",
            "层": "層",
            "释": "釋",
            "须": "須",
            "还": "還",
            "刚": "剛",
            "晓": "曉",
            "顿": "頓",
            "环": "環",
            "系": "係",
            "论": "論",
            "检": "檢",
            "题": "題",
            "宽": "寬",
            "并": "並",
            "没": "沒",
            "词": "詞",
            "约": "約",
            "压": "壓",
            "满": "滿",
            "连": "連",
            "从": "從",
            "组": "組",
            "颗": "顆",
            "竖": "豎",
            "吗": "嗎",
            "忆": "憶",
            "测": "測",
            "讨": "討",
            "贴": "貼",
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
        creative_routes = _creative_routes(request)
        blueprints = _english_video_blueprints(request, points)
        videos: list[VideoScript] = []
        for blueprint in blueprints:
            route_id = cast(CreativeRouteId, blueprint["route_id"])
            hook = blueprint["hook"]
            cta = blueprint["cta"]
            proof_voice = " ".join(
                part
                for part in (
                    blueprint["proof_voice"],
                    _short_product_fact(request.product_description, limit=110),
                )
                if part
            )
            shots = [
                Shot(
                    seconds="0–3s",
                    visual=blueprint["opening_visual"],
                    voiceover=hook,
                    filming_tip="Shoot vertically; begin the first action and first sentence together",
                ),
                Shot(
                    seconds="3–8s",
                    visual=blueprint["proof_visual"],
                    voiceover=blueprint["bridge"],
                    filming_tip="Use one continuous close-up action to answer the opening question",
                ),
                Shot(
                    seconds="8–20s",
                    visual=blueprint["context_visual"],
                    voiceover=proof_voice,
                    filming_tip="Match every spoken detail with the exact action or product detail on screen",
                ),
                Shot(
                    seconds="20–30s",
                    visual=f"Return to a close-up of {product}; show only one question and one action word on screen",
                    voiceover=cta,
                    filming_tip="Pause for one second after the question so viewers have time to choose",
                ),
            ]
            script = " ".join(shot.voiceover.strip() for shot in shots if shot.voiceover.strip())
            videos.append(
                VideoScript(
                    route_id=route_id,
                    angle=blueprint["angle"],
                    title=blueprint["title"],
                    cover_text=blueprint["cover_text"],
                    hook=hook,
                    script=script,
                    background_music=blueprint["music"],
                    shots=shots,
                    call_to_action=cta,
                    quality_assessment=_video_quality_assessment(
                        request,
                        route_id,
                        hook=hook,
                        script=script,
                        shots=shots,
                        call_to_action=cta,
                        background_music=blueprint["music"],
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
                content_focus="Open with a specific question or choice, provide visual evidence immediately, and finish with one interaction action.",
                recommended_duration="25–40 seconds; up to 60 seconds for a farmer story",
                conversion_action="Use a route-specific comment question first, then guide viewers to details, the next episode or a live session.",
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
                    content=f"Publish “{blueprints[0]['title']}”",
                    action="Record completion rate and recurring comments",
                ),
                DailyPlan(
                    day=2,
                    objective="Explain the difference",
                    content=f"Publish “{blueprints[1]['title']}”",
                    action="Add comment questions to the live Q&A",
                ),
                DailyPlan(
                    day=3,
                    objective="Build personal trust",
                    content=f"Publish “{blueprints[2]['title']}”",
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


SYSTEM_PROMPT = """You are Heyu AI, a farmer-first short-video growth producer.
Your primary job is to turn a farm product brief and a selected topic signal into
content that is specific, watchable and easy to film with one phone.

Return one JSON object that strictly matches the supplied schema. Produce exactly
three genuinely different creative routes:
1. Practical hook: solve one concrete buying, choosing, storing or using problem.
2. People story: follow one real action and explain the grower's decision behind it.
3. Playful contrast: let viewers choose, compare or guess before a visual reveal.

For every route:
- Put the product and a concrete question, contrast or consequence in the first
  three seconds. Never use vague hooks such as "check this detail" without naming
  the object viewers should inspect.
- Use a 0–3s hook, 3–8s visual proof, 8–20s explanation or contrast, and one clear
  interaction action at the end.
- Match every spoken claim with a filmable close-up, action or side-by-side proof.
- Give route-specific BGM direction including mood, tempo and where music enters,
  pauses or lowers under speech.
- Make the three titles, hooks, narrative subjects, shot logic and CTAs different.
- Use the selected trend as a narrative structure or discussion entry, then return
  to the product within three seconds. Do not paste an unrelated trend into copy.
- Avoid generic advertising phrases such as high quality, great taste, worth
  buying, must-buy or best choice.

Also provide three explainable topic signals and seven daily actions, then end with
route selection, shoot preparation and publication follow-up. Keep the requested
locale natural and adapt pacing and interaction to the selected Chinese platform.
Use only supplied product facts. Do not invent certifications, prices, medical
effects, stock, popularity metrics, views, sales or trend rankings."""


def _refresh_plan_quality(
    request: MarketingPlanRequest,
    plan: MarketingPlanResponse,
) -> MarketingPlanResponse:
    """Replace model self-scoring with the shared deterministic evaluator."""

    for video in plan.videos:
        video.quality_assessment = _video_quality_assessment(
            request,
            video.route_id,
            hook=video.hook,
            script=video.script,
            shots=video.shots,
            call_to_action=video.call_to_action,
            background_music=video.background_music,
        )
    return plan


def _plan_revision_issues(
    request: MarketingPlanRequest,
    plan: MarketingPlanResponse,
) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for video in plan.videos:
        evaluation = evaluate_script_quality(
            product_name=request.product_name,
            trend=request.trend,
            hook=video.hook,
            script=video.script,
            shots=video.shots,
            cta=video.call_to_action,
            bgm=video.background_music,
        )
        important = [issue for issue in evaluation["issues"] if issue["severity"] == "high"]
        if evaluation["total_score"] < 78 or important:
            issues.append(
                {
                    "route_id": video.route_id,
                    "total_score": evaluation["total_score"],
                    "issues": important or evaluation["issues"][:3],
                }
            )
    return issues


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
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": request.model_dump(mode="json"),
                        "required_response_schema": schema,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        payload = {
            "model": self.model,
            "temperature": 0.55,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        try:
            candidates: list[MarketingPlanResponse] = []
            for attempt in range(2):
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
                raw_content = message.get("content")
                if not isinstance(raw_content, str) or not raw_content.strip():
                    raise ValueError("Model message content must be non-empty text")
                content = raw_content.strip()
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
                candidate = _refresh_plan_quality(
                    request,
                    MarketingPlanResponse.model_validate(parsed),
                )
                candidates.append(candidate)
                revision_issues = _plan_revision_issues(request, candidate)
                if not revision_issues or attempt == 1:
                    break
                messages.extend(
                    [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "task": (
                                        "Revise the complete JSON once. Fix the listed script "
                                        "quality problems without changing supplied product facts, "
                                        "then return only the full response object."
                                    ),
                                    "quality_issues": revision_issues,
                                    "required_response_schema": schema,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ]
                )
            if not candidates:
                raise ValueError("Model did not produce a valid marketing plan")
            return max(
                candidates,
                key=lambda item: min(video.quality_assessment.total_score for video in item.videos),
            )
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


def select_marketing_modules(
    result: MarketingPlanResponse,
    modules: list[MarketingContentModule],
) -> MarketingPlanResponse:
    """Return only the deliverables selected by the user.

    Providers may still produce the full structured plan so existing compatible
    model prompts remain valid. The API response, saved version and exports only
    contain the modules explicitly requested by the user.
    """

    selected = list(dict.fromkeys(modules))
    update: dict[str, object] = {"included_modules": selected}
    if "videos" not in selected:
        update["videos"] = []
    if "livestream" not in selected:
        update["livestream"] = []
    if "calendar" not in selected:
        update["seven_day_plan"] = []
    return MarketingPlanResponse.model_validate(
        result.model_copy(update=update).model_dump(mode="python")
    )


def _regenerated_video(
    request: MarketingPlanRequest,
    video: VideoScript,
    variation_index: int,
) -> VideoScript:
    variant = (variation_index - 1) % 3
    copy = {
        "zh-CN": (
            ("先看结果，再说原因：", "现场验证版", "你更想看哪一个细节？把答案留在评论区。"),
            ("给我三秒，只看这个细节：", "三秒开场版", "先收藏，拍摄时照着这条顺序完成。"),
            ("先做一个选择，再揭晓答案：", "互动选择版", "在评论区选一边，再看下一条现场验证。"),
        ),
        "zh-HK": (
            ("先看結果，再說原因：", "現場驗證版", "你更想看哪一個細節？把答案留在留言區。"),
            ("給我三秒，只看這個細節：", "三秒開場版", "先收藏，拍攝時照着這個次序完成。"),
            ("先做一個選擇，再揭曉答案：", "互動選擇版", "在留言區選一邊，再看下一條現場驗證。"),
        ),
        "en": (
            (
                "See the result first, then the reason: ",
                "Proof-first cut",
                "Which detail should we show next? Leave your choice in the comments.",
            ),
            (
                "Give this detail three seconds: ",
                "Three-second opening",
                "Save this version and follow the same shot order when filming.",
            ),
            (
                "Make your choice before the answer: ",
                "Interactive choice cut",
                "Pick a side in the comments, then watch the next field test.",
            ),
        ),
    }[request.locale][variant]
    prefix, title_suffix, call_to_action = copy
    separator = " | " if request.locale == "en" else "｜"
    hook = f"{prefix}{video.hook}"
    script = video.script.replace(video.hook, hook, 1)
    if script == video.script:
        script = f"{hook}\n{video.script}"
    shots = [item.model_copy(deep=True) for item in video.shots]
    if shots:
        shots[0] = shots[0].model_copy(update={"voiceover": hook})
    quality = _video_quality_assessment(
        request,
        video.route_id,
        hook=hook,
        script=script,
        shots=shots,
        call_to_action=call_to_action,
        background_music=video.background_music,
    )
    return video.model_copy(
        update={
            "title": f"{video.title}{separator}{title_suffix}",
            "hook": hook,
            "script": script,
            "shots": shots,
            "call_to_action": call_to_action,
            "quality_assessment": quality,
        },
        deep=True,
    )


def _regenerated_livestream(
    locale: Locale,
    sections: list[LivestreamSection],
    variation_index: int,
) -> list[LivestreamSection]:
    regenerated = [item.model_copy(deep=True) for item in sections]
    if not regenerated:
        return regenerated
    variants = {
        "zh-CN": (
            ("先问后讲", "先请观众选择最关心的产品细节，再进入展示。"),
            ("现场验证", "先展示一个可见细节，再解释它与产品卖点的关系。"),
            ("评论互动", "先收集评论区问题，再按出现频率逐一回应。"),
        ),
        "zh-HK": (
            ("先問後講", "先請觀眾選擇最關心的產品細節，再進入展示。"),
            ("現場驗證", "先展示一個可見細節，再解釋它與產品賣點的關係。"),
            ("留言互動", "先收集留言區問題，再按出現頻率逐一回應。"),
        ),
        "en": (
            (
                "Ask before telling",
                "Let viewers choose the product detail they care about before the demonstration.",
            ),
            ("Live proof", "Show one visible detail first, then connect it to the product value."),
            (
                "Comment-led flow",
                "Collect viewer questions first, then answer them in order of frequency.",
            ),
        ),
    }[locale]
    title, talking_point = variants[(variation_index - 1) % len(variants)]
    first = regenerated[0]
    regenerated[0] = first.model_copy(
        update={
            "section": f"{title} · {first.section}",
            "talking_points": [talking_point, *first.talking_points],
        }
    )
    return regenerated


def _regenerated_calendar(
    locale: Locale,
    days: list[DailyPlan],
    variation_index: int,
) -> list[DailyPlan]:
    regenerated = [item.model_copy(deep=True) for item in days]
    if not regenerated:
        return regenerated
    variants = {
        "zh-CN": (
            ("先测互动", "先发布互动型内容，用评论选择下一条拍摄方向。"),
            ("先建信任", "先发布现场与人物内容，让观众认识产品从哪里来。"),
            ("先给方法", "先发布可收藏的挑选或使用方法，再承接产品介绍。"),
        ),
        "zh-HK": (
            ("先測互動", "先發佈互動型內容，用留言選擇下一條拍攝方向。"),
            ("先建信任", "先發佈現場與人物內容，讓觀眾認識產品從哪裏來。"),
            ("先給方法", "先發佈可收藏的挑選或使用方法，再承接產品介紹。"),
        ),
        "en": (
            (
                "Test interaction first",
                "Publish an interactive post and let comments choose the next filming direction.",
            ),
            (
                "Build trust first",
                "Start with field and people content so viewers understand where the product comes from.",
            ),
            (
                "Lead with utility",
                "Publish a saveable choosing or usage tip before the product introduction.",
            ),
        ),
    }[locale]
    objective, action = variants[(variation_index - 1) % len(variants)]
    regenerated[0] = regenerated[0].model_copy(update={"objective": objective, "action": action})
    return regenerated


def merge_regenerated_marketing_module(
    payload: MarketingModuleRegenerationRequest,
    candidate: MarketingPlanResponse,
) -> MarketingPlanResponse:
    """Replace only the requested deliverable and preserve the rest of the plan."""

    current = payload.current_plan.model_copy(deep=True)
    update: dict[str, object] = {
        "provider": candidate.provider,
        "model": candidate.model,
        "latency_ms": candidate.latency_ms,
        "cache_hit": candidate.cache_hit,
        "degraded": candidate.degraded,
        "notice": candidate.notice,
    }
    if payload.target == "video":
        assert payload.route_id is not None
        candidate_by_route = {item.route_id: item for item in candidate.videos}
        replacement = candidate_by_route[payload.route_id]
        replacement = _regenerated_video(
            payload.request,
            replacement,
            payload.variation_index,
        )
        update["videos"] = [
            replacement if item.route_id == payload.route_id else item for item in current.videos
        ]
    elif payload.target == "livestream":
        update["livestream"] = _regenerated_livestream(
            payload.request.locale,
            candidate.livestream,
            payload.variation_index,
        )
    else:
        update["seven_day_plan"] = _regenerated_calendar(
            payload.request.locale,
            candidate.seven_day_plan,
            payload.variation_index,
        )
    return MarketingPlanResponse.model_validate(
        current.model_copy(update=update).model_dump(mode="python")
    )


def generate_marketing_preview(request: MarketingPlanRequest) -> MarketingPlanResponse:
    """Always-free preview used by the public/local demo."""
    provider_request = request.model_copy(update={"content_modules": _default_content_modules()})
    result = DeterministicMarketingProvider().generate(provider_request)
    return select_marketing_modules(result, request.content_modules)


def generate_marketing_plan(request: MarketingPlanRequest) -> MarketingPlanResponse:
    """Generate with cache reuse and an explicit deterministic degradation path."""
    settings = get_settings()
    provider = get_marketing_provider(settings)
    key = _cache_key(provider, request)
    cached = _marketing_cache.get(key)
    if cached is not None:
        return select_marketing_modules(cached, request.content_modules)

    provider_request = request.model_copy(update={"content_modules": _default_content_modules()})
    try:
        result = provider.generate(provider_request)
    except MarketingProviderError:
        if not settings.marketing_fallback_to_mock:
            raise
        result = DeterministicMarketingProvider().generate(provider_request)
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
    return select_marketing_modules(result.model_copy(deep=True), request.content_modules)


def regenerate_marketing_preview(
    payload: MarketingModuleRegenerationRequest,
) -> MarketingPlanResponse:
    provider_request = payload.request.model_copy(
        update={"content_modules": _default_content_modules()}
    )
    candidate = DeterministicMarketingProvider().generate(provider_request)
    return merge_regenerated_marketing_module(payload, candidate)


def regenerate_marketing_plan(
    payload: MarketingModuleRegenerationRequest,
) -> MarketingPlanResponse:
    provider_request = payload.request.model_copy(
        update={"content_modules": _default_content_modules()}
    )
    candidate = generate_marketing_plan(provider_request)
    return merge_regenerated_marketing_module(payload, candidate)
