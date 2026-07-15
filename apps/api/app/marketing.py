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


class Shot(StrictModel):
    seconds: str
    visual: str
    voiceover: str
    filming_tip: str


class VideoScript(StrictModel):
    angle: str
    title: str
    cover_text: str
    hook: str
    script: str
    background_music: str
    shots: list[Shot] = Field(min_length=3, max_length=6)
    call_to_action: str


class LivestreamSection(StrictModel):
    section: str
    talking_points: list[str]


class DailyPlan(StrictModel):
    day: int = Field(ge=1, le=7)
    objective: str
    content: str
    action: str


class MarketingPlanResponse(StrictModel):
    product_profile: ProductProfile
    strategy: PlatformStrategy
    trend: TrendBrief
    videos: list[VideoScript] = Field(min_length=3, max_length=3)
    livestream: list[LivestreamSection] = Field(min_length=4, max_length=8)
    seven_day_plan: list[DailyPlan] = Field(min_length=7, max_length=7)
    next_actions: list[str] = Field(min_length=3, max_length=6)
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
        angles = [
            (
                "产地现场",
                f"{product}不是从货架开始的",
                f"今天带你到{origin}，看看{product}从哪里来。",
                "自然纪录感的轻快木吉他",
            ),
            (
                "产品差异",
                f"挑{product}，先看这三个地方",
                f"别急着看价格，先用十秒看懂{product}值不值得买。",
                "节奏清晰、鼓点轻盈的知识类配乐",
            ),
            (
                "农户人物",
                "种了这么多年，我最想说的不是辛苦",
                f"我是{origin}的种植户，这批{product}，我想亲自讲给你听。",
                "温暖克制的钢琴与环境声",
            ),
        ]
        videos: list[VideoScript] = []
        for index, (angle, title, hook, music) in enumerate(angles):
            point = points[index % len(points)]
            script = (
                f"{hook} 这一季我们最在意的是{point}。"
                f"{request.product_description.strip()} "
                f"镜头里不需要复杂表演，把采摘、切开或装箱的真实过程拍清楚，"
                f"让大家先看见产品，再听见种植者的话。{cta}。"
            )
            videos.append(
                VideoScript(
                    angle=angle,
                    title=title,
                    cover_text=f"{product}｜{point}",
                    hook=hook,
                    script=script,
                    background_music=music,
                    shots=[
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
                            visual="切开、称重或细节对比",
                            voiceover=request.product_description.strip()[:120],
                            filming_tip="用自然光，避免滤镜改变产品真实颜色",
                        ),
                        Shot(
                            seconds="24–30秒",
                            visual="农户出镜或产品整齐装箱",
                            voiceover=cta,
                            filming_tip="结尾只保留一个行动指令",
                        ),
                    ],
                    call_to_action=cta,
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
                    content=f"发布“{angles[0][1]}”产地视频",
                    action="记录完播率与高频评论",
                ),
                DailyPlan(
                    day=2,
                    objective="解释产品差异",
                    content=f"发布“{angles[1][1]}”知识视频",
                    action="把评论问题加入直播问答",
                ),
                DailyPlan(
                    day=3,
                    objective="建立人物信任",
                    content=f"发布“{angles[2][1]}”农户故事",
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
        }
        for source, target in replacements.items():
            raw = raw.replace(source, target)
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
        angles = [
            (
                "Origin",
                f"{product} does not begin on a shelf",
                f"Come to {origin} and see where {product} begins.",
            ),
            (
                "Difference",
                f"Three things to notice when choosing {product}",
                f"Before comparing prices, take ten seconds to see what makes {product} different.",
            ),
            (
                "Farmer story",
                "What I most want people to know after years of growing",
                f"I grow {product} in {origin}, and I want to tell this story myself.",
            ),
        ]
        videos = []
        for index, (angle, title, hook) in enumerate(angles):
            point = points[index % len(points)]
            videos.append(
                VideoScript(
                    angle=angle,
                    title=title,
                    cover_text=f"{product} · {point}",
                    hook=hook,
                    script=f"{hook} This season, our focus is {point}. {request.product_description.strip()} Show the real harvest, preparation or packing process instead of overproducing the scene. {cta}.",
                    background_music=[
                        "light acoustic documentary",
                        "clean rhythmic explainer",
                        "warm piano with natural ambience",
                    ][index],
                    shots=[
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
                            visual="Cut-open, weighing or detail comparison",
                            voiceover=request.product_description.strip()[:120],
                            filming_tip="Use daylight and preserve the product's real color",
                        ),
                        Shot(
                            seconds="24–30s",
                            visual="Farmer on camera or packed product",
                            voiceover=cta,
                            filming_tip="End with one clear action",
                        ),
                    ],
                    call_to_action=cta,
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
                    content=f"Publish “{angles[0][1]}”",
                    action="Record completion rate and recurring comments",
                ),
                DailyPlan(
                    day=2,
                    objective="Explain the difference",
                    content=f"Publish “{angles[1][1]}”",
                    action="Add comment questions to the live Q&A",
                ),
                DailyPlan(
                    day=3,
                    objective="Build personal trust",
                    content=f"Publish “{angles[2][1]}”",
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
            provider="",
            model="",
            latency_ms=0,
        )


SYSTEM_PROMPT = """You are Heyu AI, a farmer-first agricultural marketing strategist.
Create a practical plan that a farmer can film with a phone. Never invent product
facts, certifications, prices, medical effects, stock or trend data. Return one
JSON object that strictly matches the supplied schema. Produce exactly three
different videos and seven daily actions. Keep the requested locale natural and
adapt the content to the selected Chinese social platform."""


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
