"""Trend discovery and farmer-first product-fit ranking.

The module deliberately separates two questions:

1. What signals were actually observed, and where did they come from?
2. Is a signal useful for this product, audience, platform, and filming context?

RSS/Atom and an optional Douyin Open Platform adapter can supply observed
signals.  When those sources are unavailable, the service returns clearly
labelled seasonal and evergreen ideas rather than inventing real-time heat,
view counts, engagement, or sales predictions.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal, Protocol
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

Platform = Literal["douyin", "xiaohongshu", "wechat-channels", "kuaishou", "other"]
SourceType = Literal["manual", "rss", "atom", "douyin-open-platform", "seasonal", "evergreen"]
Recommendation = Literal["recommended", "consider", "skip"]

MAX_DISCOVERY_ITEMS = 20
MAX_FEED_ITEMS = 30
DEFAULT_TIMEOUT_SECONDS = 5.0


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrendCandidate(StrictModel):
    """A traceable signal; it intentionally contains no popularity metric."""

    title: str = Field(min_length=1, max_length=240)
    source_url: str | None = Field(default=None, max_length=2048)
    source_label: str = Field(min_length=1, max_length=120)
    captured_at: datetime
    published_at: datetime | None = None
    source_type: SourceType
    summary: str = Field(default="", max_length=1200)

    @field_validator("captured_at", "published_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("trend timestamps must include a timezone")
        return value


class ManualTrend(StrictModel):
    title: str = Field(min_length=1, max_length=240)
    source_url: str | None = Field(default=None, max_length=2048)
    source_label: str = Field(default="用户提供", min_length=1, max_length=120)
    published_at: datetime | None = None
    summary: str = Field(default="", max_length=1200)


class FeedSource(StrictModel):
    url: str = Field(min_length=1, max_length=2048)
    label: str = Field(min_length=1, max_length=120)


class DouyinOpenPlatformSource(StrictModel):
    """Configurable placeholder for an authorized official endpoint.

    No endpoint is guessed and no request is made unless both ``endpoint`` and
    ``access_token`` are supplied by the deployer.
    """

    endpoint: str | None = Field(default=None, max_length=2048)
    access_token: str | None = Field(default=None, min_length=1, max_length=4096)
    source_label: str = Field(default="抖音开放平台热点榜", min_length=1, max_length=120)

    @property
    def connected(self) -> bool:
        return bool(self.endpoint and self.access_token)


class TrendDiscoveryRequest(StrictModel):
    product_name: str = Field(min_length=1, max_length=80)
    selling_points: list[str] = Field(default_factory=list, max_length=8)
    audience: str = Field(default="", max_length=160)
    platform: Platform = "douyin"
    manual_trends: list[ManualTrend] = Field(default_factory=list, max_length=20)
    feed_sources: list[FeedSource] = Field(default_factory=list, max_length=12)
    douyin: DouyinOpenPlatformSource | None = None
    limit: int = Field(default=8, ge=1, le=MAX_DISCOVERY_ITEMS)


class FitDimension(StrictModel):
    score: int = Field(ge=0, le=100)
    explanation: str


class TrendFit(StrictModel):
    product: FitDimension
    selling_points: FitDimension
    audience: FitDimension
    platform: FitDimension
    timeliness: FitDimension
    filmability: FitDimension


class RankedTrend(StrictModel):
    candidate: TrendCandidate
    fit: TrendFit
    fit_score: int = Field(ge=0, le=100)
    recommendation: Recommendation
    recommendation_reason: str


class TrendDiscoveryResult(StrictModel):
    items: list[RankedTrend]
    warnings: list[str]
    used_fallback: bool
    metric_note: str = (
        "fit_score 只表示该选题与当前产品及拍摄条件的适配度；"
        "它不是实时热度、播放量、互动量或销量预测。"
    )


class TrendSourceAdapter(Protocol):
    def fetch(self, *, captured_at: datetime, limit: int) -> list[TrendCandidate]: ...


class TrendSourceError(RuntimeError):
    """A recoverable source error that should trigger an explicit fallback."""


class RssAtomAdapter:
    def __init__(
        self,
        source: FeedSource,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.source = source
        self.client = client
        self.timeout_seconds = max(0.1, min(timeout_seconds, 15.0))

    def fetch(self, *, captured_at: datetime, limit: int) -> list[TrendCandidate]:
        try:
            if self.client is None:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = client.get(self.source.url)
            else:
                response = self.client.get(
                    self.source.url,
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                )
            response.raise_for_status()
            return _parse_feed(
                response.content,
                source=self.source,
                captured_at=captured_at,
                limit=min(limit, MAX_FEED_ITEMS),
            )
        except (httpx.HTTPError, ET.ParseError, UnicodeError, ValueError) as exc:
            raise TrendSourceError(f"{self.source.label} 暂时不可用：{type(exc).__name__}") from exc


class DouyinOpenPlatformAdapter:
    """Adapter shell for a configured, authorized Douyin Open Platform endpoint."""

    def __init__(
        self,
        source: DouyinOpenPlatformSource,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.source = source
        self.client = client
        self.timeout_seconds = max(0.1, min(timeout_seconds, 15.0))

    def fetch(self, *, captured_at: datetime, limit: int) -> list[TrendCandidate]:
        if not self.source.connected:
            return []
        assert self.source.endpoint is not None
        assert self.source.access_token is not None
        headers = {"Authorization": f"Bearer {self.source.access_token}"}
        params = {"count": min(limit, MAX_FEED_ITEMS)}
        try:
            if self.client is None:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = client.get(self.source.endpoint, headers=headers, params=params)
            else:
                response = self.client.get(
                    self.source.endpoint,
                    headers=headers,
                    params=params,
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TrendSourceError("抖音开放平台热点源暂时不可用") from exc
        return _parse_douyin_payload(
            payload,
            source=self.source,
            captured_at=captured_at,
            limit=min(limit, MAX_FEED_ITEMS),
        )


class TrendDiscoveryService:
    def __init__(
        self,
        *,
        feed_client: httpx.Client | None = None,
        douyin_client: httpx.Client | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.feed_client = feed_client
        self.douyin_client = douyin_client
        self.timeout_seconds = timeout_seconds

    def discover(
        self,
        request: TrendDiscoveryRequest,
        *,
        now: datetime | None = None,
    ) -> TrendDiscoveryResult:
        captured_at = now or datetime.now(UTC)
        if captured_at.tzinfo is None:
            raise ValueError("now must include a timezone")

        candidates = [
            TrendCandidate(
                title=item.title.strip(),
                source_url=item.source_url,
                source_label=item.source_label,
                captured_at=captured_at,
                published_at=item.published_at,
                source_type="manual",
                summary=item.summary.strip(),
            )
            for item in request.manual_trends
        ]
        warnings: list[str] = []
        observed_count = 0
        configured_external_source = bool(request.feed_sources)

        for feed_source in request.feed_sources:
            feed_adapter = RssAtomAdapter(
                feed_source,
                client=self.feed_client,
                timeout_seconds=self.timeout_seconds,
            )
            try:
                fetched = feed_adapter.fetch(captured_at=captured_at, limit=request.limit)
            except TrendSourceError as exc:
                warnings.append(str(exc))
                continue
            candidates.extend(fetched)
            observed_count += len(fetched)

        if request.douyin is not None:
            if request.douyin.connected:
                configured_external_source = True
                douyin_adapter = DouyinOpenPlatformAdapter(
                    request.douyin,
                    client=self.douyin_client,
                    timeout_seconds=self.timeout_seconds,
                )
                try:
                    fetched = douyin_adapter.fetch(captured_at=captured_at, limit=request.limit)
                except TrendSourceError as exc:
                    warnings.append(str(exc))
                else:
                    candidates.extend(fetched)
                    observed_count += len(fetched)
            else:
                warnings.append("抖音开放平台热点榜未连接，未请求或伪造平台热点。")

        used_fallback = observed_count == 0
        if used_fallback:
            candidates.extend(
                _fallback_candidates(
                    request.product_name,
                    captured_at=captured_at,
                )
            )
            if configured_external_source:
                warnings.append("实时来源当前没有可用结果，已改用季节性与常青选题信号。")
            else:
                warnings.append("未配置可用的实时来源，当前使用季节性与常青选题信号。")

        unique_candidates = _deduplicate(candidates)
        ranked = [
            rank_candidate(candidate, request=request, now=captured_at)
            for candidate in unique_candidates
        ]
        ranked.sort(
            key=lambda item: (
                item.fit_score,
                item.candidate.published_at or datetime.min.replace(tzinfo=UTC),
                item.candidate.title,
            ),
            reverse=True,
        )
        return TrendDiscoveryResult(
            items=ranked[: request.limit],
            warnings=_deduplicate_strings(warnings),
            used_fallback=used_fallback,
        )


def rank_candidate(
    candidate: TrendCandidate,
    *,
    request: TrendDiscoveryRequest,
    now: datetime,
) -> RankedTrend:
    searchable = f"{candidate.title} {candidate.summary}".strip()
    product_score, product_reason = _text_fit(
        searchable,
        [request.product_name],
        exact_reason=f"选题直接提到“{request.product_name}”",
        partial_reason="选题与产品名称存在可解释的词义重合",
        missing_reason="选题未直接体现当前产品",
    )
    selling_score, selling_reason = _text_fit(
        searchable,
        request.selling_points,
        exact_reason="选题直接承接至少一个产品卖点",
        partial_reason="选题与产品卖点有部分表达重合",
        missing_reason="选题尚未承接已提供的产品卖点",
        empty_score=55,
        empty_reason="尚未提供卖点，暂按中性适配处理",
    )
    audience_score, audience_reason = _text_fit(
        searchable,
        [request.audience] if request.audience else [],
        exact_reason="选题直接触达目标受众",
        partial_reason="选题语义与目标受众部分相关",
        missing_reason="选题与目标受众的关联不明显",
        empty_score=55,
        empty_reason="尚未指定受众，暂按中性适配处理",
    )
    platform_score, platform_reason = _platform_fit(searchable, request.platform)
    timeliness_score, timeliness_reason = _timeliness_fit(candidate, now)
    filmability_score, filmability_reason = _filmability_fit(searchable)

    fit = TrendFit(
        product=FitDimension(score=product_score, explanation=product_reason),
        selling_points=FitDimension(score=selling_score, explanation=selling_reason),
        audience=FitDimension(score=audience_score, explanation=audience_reason),
        platform=FitDimension(score=platform_score, explanation=platform_reason),
        timeliness=FitDimension(score=timeliness_score, explanation=timeliness_reason),
        filmability=FitDimension(score=filmability_score, explanation=filmability_reason),
    )
    weighted_score = round(
        product_score * 0.27
        + selling_score * 0.20
        + audience_score * 0.14
        + platform_score * 0.14
        + timeliness_score * 0.13
        + filmability_score * 0.12
    )
    if weighted_score >= 72:
        recommendation: Recommendation = "recommended"
        reason = "产品关联、平台表达和拍摄落地的综合适配较强，可优先进入脚本创作。"
    elif weighted_score >= 52:
        recommendation = "consider"
        reason = "存在可用切入点，但应先补强产品卖点或受众关联再写脚本。"
    else:
        recommendation = "skip"
        reason = "与当前产品经营目标的关联较弱，不建议为了追热点强行套用。"
    return RankedTrend(
        candidate=candidate,
        fit=fit,
        fit_score=weighted_score,
        recommendation=recommendation,
        recommendation_reason=reason,
    )


def _parse_feed(
    content: bytes,
    *,
    source: FeedSource,
    captured_at: datetime,
    limit: int,
) -> list[TrendCandidate]:
    root = ET.fromstring(content)
    root_name = _local_name(root.tag).lower()
    is_atom = root_name == "feed"
    item_name = "entry" if is_atom else "item"
    source_type: SourceType = "atom" if is_atom else "rss"
    candidates: list[TrendCandidate] = []
    for item in (node for node in root.iter() if _local_name(node.tag).lower() == item_name):
        title = _child_text(item, "title").strip()
        if not title:
            continue
        link = _extract_link(item, source.url, is_atom=is_atom)
        published_text = (
            _child_text(item, "published")
            or _child_text(item, "updated")
            or _child_text(item, "pubDate")
            or _child_text(item, "date")
        )
        summary = (
            _child_text(item, "summary")
            or _child_text(item, "description")
            or _child_text(item, "content")
        )
        candidates.append(
            TrendCandidate(
                title=_strip_markup(title)[:240],
                source_url=link,
                source_label=source.label,
                captured_at=captured_at,
                published_at=_parse_datetime(published_text),
                source_type=source_type,
                summary=_strip_markup(summary)[:1200],
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _parse_douyin_payload(
    payload: Any,
    *,
    source: DouyinOpenPlatformSource,
    captured_at: datetime,
    limit: int,
) -> list[TrendCandidate]:
    if not isinstance(payload, dict):
        raise TrendSourceError("抖音开放平台返回格式不可识别")
    data = payload.get("data", payload)
    if isinstance(data, dict):
        raw_items = data.get("list", data.get("items", []))
    else:
        raw_items = data
    if not isinstance(raw_items, list):
        raise TrendSourceError("抖音开放平台返回格式不可识别")
    candidates: list[TrendCandidate] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = raw.get("title") or raw.get("word") or raw.get("name")
        if not isinstance(title, str) or not title.strip():
            continue
        url = raw.get("share_url") or raw.get("url")
        summary = raw.get("summary") or raw.get("description") or ""
        published_at = _parse_datetime(raw.get("published_at") or raw.get("publish_time"))
        candidates.append(
            TrendCandidate(
                title=title.strip()[:240],
                source_url=url if isinstance(url, str) else None,
                source_label=source.source_label,
                captured_at=captured_at,
                published_at=published_at,
                source_type="douyin-open-platform",
                summary=summary[:1200] if isinstance(summary, str) else "",
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _fallback_candidates(product_name: str, *, captured_at: datetime) -> list[TrendCandidate]:
    month = captured_at.month
    if month in {3, 4, 5}:
        season = "春日上新与田间生长"
    elif month in {6, 7, 8}:
        season = "盛夏当季与清晨采收"
    elif month in {9, 10, 11}:
        season = "秋收上市与产地丰收"
    else:
        season = "冬日储鲜与年节备货"
    return [
        TrendCandidate(
            title=f"{product_name}：{season}怎么拍",
            source_url=None,
            source_label="季节性选题建议",
            captured_at=captured_at,
            published_at=None,
            source_type="seasonal",
            summary="结合当前月份、田间场景和当季购买理由设计，不代表实时平台热点。",
        ),
        TrendCandidate(
            title=f"一镜看懂{product_name}从采收到发货",
            source_url=None,
            source_label="常青内容建议",
            captured_at=captured_at,
            published_at=None,
            source_type="evergreen",
            summary="用可拍摄的过程展示回答消费者长期关心的产地、挑选和发货问题。",
        ),
    ]


def _text_fit(
    text: str,
    targets: Sequence[str],
    *,
    exact_reason: str,
    partial_reason: str,
    missing_reason: str,
    empty_score: int = 20,
    empty_reason: str = "没有可用于判断的信息",
) -> tuple[int, str]:
    targets = [target.strip() for target in targets if target.strip()]
    if not targets:
        return empty_score, empty_reason
    normalized_text = _normalize(text)
    if any(_normalize(target) in normalized_text for target in targets):
        return 100, exact_reason
    text_terms = _terms(text)
    target_terms = set().union(*(_terms(target) for target in targets))
    overlap = text_terms & target_terms
    if overlap:
        ratio = len(overlap) / max(1, len(target_terms))
        return min(88, 55 + round(ratio * 33)), partial_reason
    return 20, missing_reason


def _platform_fit(text: str, platform: Platform) -> tuple[int, str]:
    normalized = _normalize(text)
    aliases: dict[Platform, tuple[str, ...]] = {
        "douyin": ("抖音", "短视频", "挑战", "反转", "douyin"),
        "xiaohongshu": ("小红书", "笔记", "攻略", "清单", "xiaohongshu"),
        "wechat-channels": ("视频号", "朋友圈", "直播", "wechat"),
        "kuaishou": ("快手", "老铁", "短视频", "kuaishou"),
        "other": (),
    }
    matches = [alias for alias in aliases[platform] if _normalize(alias) in normalized]
    if matches:
        return 90, f"选题含有适合该平台的表达线索：{matches[0]}"
    if any(cue in normalized for cue in ("视频", "镜头", "现场", "教程", "故事")):
        return 68, "选题具备内容化表达空间，但尚未体现目标平台特性"
    return 52, "选题可跨平台改写，进入脚本前需要补充平台钩子"


def _timeliness_fit(candidate: TrendCandidate, now: datetime) -> tuple[int, str]:
    if candidate.source_type == "seasonal":
        return 78, "这是按当前月份生成的季节性信号，不代表实时榜单热度"
    if candidate.source_type == "evergreen":
        return 64, "这是长期有效的常青问题，不依赖实时热度"
    if candidate.published_at is None:
        return 48, "来源未提供发布时间，无法判断实时性"
    published_at = candidate.published_at.astimezone(UTC)
    age_days = max(0.0, (now.astimezone(UTC) - published_at).total_seconds() / 86400)
    if age_days <= 2:
        return 96, "来源发布时间在两天内"
    if age_days <= 7:
        return 86, "来源发布时间在一周内"
    if age_days <= 30:
        return 70, "来源发布时间在一个月内"
    if age_days <= 90:
        return 52, "来源发布时间超过一个月"
    return 30, "来源发布时间较早，建议核实是否仍适用"


def _filmability_fit(text: str) -> tuple[int, str]:
    normalized = _normalize(text)
    cues = (
        "采摘",
        "收获",
        "开箱",
        "对比",
        "挑战",
        "教程",
        "做法",
        "一天",
        "现场",
        "田间",
        "发货",
        "镜头",
        "过程",
        "探访",
        "vlog",
        "howto",
        "behindthescenes",
    )
    matched = [cue for cue in cues if _normalize(cue) in normalized]
    if len(matched) >= 2:
        return 92, f"可直接转成现场镜头：{'、'.join(matched[:3])}"
    if matched:
        return 78, f"具备明确可拍摄动作：{matched[0]}"
    if any(cue in normalized for cue in ("为什么", "怎么", "揭秘", "故事")):
        return 66, "可以转成问答或讲述，但需要补充动作和场景"
    return 42, "当前更像抽象话题，需要先改写成可见动作"


def _deduplicate(candidates: Iterable[TrendCandidate]) -> list[TrendCandidate]:
    """Collapse duplicate URLs or titles while retaining the best provenance.

    Feed aggregators frequently repeat the same story with a changed title, and
    operators may also paste a topic that later appears in an RSS source.  A
    first-item-wins strategy can accidentally keep an undated manual copy and
    discard the newer, traceable source.  Grouping both URL and title aliases
    lets us retain one canonical candidate using explicit quality rules.
    """

    groups: list[list[TrendCandidate]] = []
    for candidate in candidates:
        candidate_keys = _candidate_deduplication_keys(candidate)
        matching_groups = [
            index
            for index, group in enumerate(groups)
            if candidate_keys
            & set().union(*(_candidate_deduplication_keys(item) for item in group))
        ]
        if not matching_groups:
            groups.append([candidate])
            continue
        merged = [candidate]
        for index in reversed(matching_groups):
            merged.extend(groups.pop(index))
        groups.append(merged)

    return [max(group, key=_candidate_preference) for group in groups]


def _candidate_deduplication_keys(candidate: TrendCandidate) -> set[str]:
    keys = {f"title:{_normalize(candidate.title)}"}
    if candidate.source_url:
        keys.add(f"url:{_normalize(candidate.source_url)}")
    return keys


def _candidate_preference(candidate: TrendCandidate) -> tuple[int, datetime, int, int]:
    """Prefer observed, dated and information-rich candidates within a duplicate group."""

    source_priority: dict[SourceType, int] = {
        "douyin-open-platform": 6,
        "rss": 5,
        "atom": 5,
        "manual": 4,
        "seasonal": 2,
        "evergreen": 1,
    }
    published_at = candidate.published_at or datetime.min.replace(tzinfo=UTC)
    return (
        source_priority[candidate.source_type],
        published_at,
        int(bool(candidate.source_url)),
        len(candidate.summary.strip()),
    )


def _deduplicate_strings(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _terms(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    latin_terms = set(re.findall(r"[a-z0-9]{2,}", normalized))
    chinese_runs = re.findall(r"[\u3400-\u9fff]+", normalized)
    chinese_terms: set[str] = set()
    for run in chinese_runs:
        if len(run) <= 4:
            chinese_terms.add(run)
        for width in (2, 3, 4):
            chinese_terms.update(
                run[index : index + width] for index in range(len(run) - width + 1)
            )
    return latin_terms | chinese_terms


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, name: str) -> str:
    for child in element:
        if _local_name(child.tag).lower() == name.lower():
            return "".join(child.itertext())
    return ""


def _extract_link(element: ET.Element, base_url: str, *, is_atom: bool) -> str | None:
    for child in element:
        if _local_name(child.tag).lower() != "link":
            continue
        raw = child.attrib.get("href") if is_atom else child.text
        if raw and raw.strip():
            return urljoin(base_url, raw.strip())
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _strip_markup(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()
