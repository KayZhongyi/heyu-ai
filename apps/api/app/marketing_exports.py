"""Convert a saved marketing plan route into a ready-to-download platform ZIP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

from app.marketing import MarketingPlanRequest, MarketingPlanResponse, VideoScript
from app.platform_exports import (
    PLATFORM_PROFILES,
    Platform,
    PlatformExportInput,
    PlatformExportPackage,
    PlatformValidationError,
    ShotListItem,
    SubtitleCue,
    get_platform_adapter,
)
from app.schemas import MarketingPlanDetailRead

_TIMING_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_PLATFORM_MAP = {
    "douyin": "douyin",
    "xiaohongshu": "xiaohongshu",
    "wechat-channels": "wechat_channels",
    "wechat_channels": "wechat_channels",
}


@dataclass(frozen=True, slots=True)
class MarketingPlanExport:
    filename: str
    package: PlatformExportPackage


def export_saved_marketing_plan(
    plan: MarketingPlanDetailRead,
    route_id: str,
) -> MarketingPlanExport:
    """Build a deterministic manual-upload package for one creative route."""

    request = MarketingPlanRequest.model_validate(plan.current_version.request_payload)
    content = MarketingPlanResponse.model_validate(plan.current_version.content)
    video = _find_video(content, route_id)
    platform = _platform_for_export(request.platform)
    profile = PLATFORM_PROFILES[platform]

    title = _truncate(video.title, profile.title_max_characters)
    caption = _truncate(
        "\n\n".join(part for part in (video.script.strip(), video.call_to_action.strip()) if part),
        profile.caption_max_characters,
    )
    cover_copy = video.cover_text.strip() or title
    subtitles = _subtitle_cues(video)
    shots = tuple(
        ShotListItem(
            order=index,
            timing=shot.seconds,
            visual=shot.visual,
            voiceover=shot.voiceover,
            filming_tip=shot.filming_tip,
        )
        for index, shot in enumerate(video.shots, start=1)
    )
    hashtags = _hashtags(
        request.product_name,
        request.origin,
        _route_label(video.route_id, request.locale),
    )
    checklist = (
        _localized(
            request.locale,
            zh_cn="按分镜逐项确认素材已经拍齐",
            zh_hk="按分鏡逐項確認素材已經拍齊",
            en="Confirm that every shot in the shot list has been recorded",
        ),
        _localized(
            request.locale,
            zh_cn="发布前预览标题、字幕、封面和背景音乐音量",
            zh_hk="發佈前預覽標題、字幕、封面和背景音樂音量",
            en="Preview the title, subtitles, cover and music level before publishing",
        ),
    )

    package = get_platform_adapter(platform).export(
        PlatformExportInput(
            platform=platform,
            title=title,
            caption=caption,
            hashtags=hashtags,
            cover_copy=cover_copy,
            subtitles=subtitles,
            shots=shots,
            checklist=checklist,
            locale=request.locale,
            mode="export_only",
        )
    )
    filename = f"heyu-{platform}-{video.route_id}.zip"
    return MarketingPlanExport(filename=filename, package=package)


def _find_video(content: MarketingPlanResponse, route_id: str) -> VideoScript:
    normalized = route_id.strip()
    for video in content.videos:
        if video.route_id == normalized:
            return video
    allowed = ", ".join(video.route_id for video in content.videos)
    raise PlatformValidationError(f"unknown creative route: {route_id}; choose one of {allowed}")


def _platform_for_export(platform: str) -> Platform:
    try:
        return cast(Platform, _PLATFORM_MAP[platform.strip().lower()])
    except KeyError as exc:
        if platform.strip().lower() == "kuaishou":
            raise PlatformValidationError(
                "Kuaishou export is not available yet; choose Douyin, Xiaohongshu "
                "or WeChat Channels"
            ) from exc
        raise PlatformValidationError(f"platform export is not available for {platform}") from exc


def _subtitle_cues(video: VideoScript) -> tuple[SubtitleCue, ...]:
    cues: list[SubtitleCue] = []
    previous_end = 0
    for index, shot in enumerate(video.shots):
        start_ms, end_ms = _parse_timing(shot.seconds, index=index, previous_end=previous_end)
        text = shot.voiceover.strip()
        if not text:
            previous_end = end_ms
            continue
        start_ms = max(start_ms, previous_end)
        if end_ms <= start_ms:
            end_ms = start_ms + 3000
        cues.append(SubtitleCue(start_ms=start_ms, end_ms=end_ms, text=text))
        previous_end = end_ms
    return tuple(cues)


def _parse_timing(value: str, *, index: int, previous_end: int) -> tuple[int, int]:
    numbers = [float(match) for match in _TIMING_NUMBER.findall(value)]
    if len(numbers) >= 2:
        start_ms = round(numbers[0] * 1000)
        end_ms = round(numbers[1] * 1000)
        return start_ms, end_ms
    if len(numbers) == 1:
        start_ms = previous_end
        return start_ms, max(start_ms + 1000, round(numbers[0] * 1000))
    start_ms = previous_end if previous_end else index * 5000
    return start_ms, start_ms + 5000


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1].rstrip("，,。.!！？?、；;：: ") + "…"


def _hashtags(*values: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = re.sub(r"\s+", "", value.strip().lstrip("#"))
        if normalized and normalized.casefold() not in seen:
            result.append(normalized)
            seen.add(normalized.casefold())
    return tuple(result)


def _route_label(route_id: str, locale: str) -> str:
    labels = {
        "practical-hook": ("实用吸睛", "實用吸睛", "PracticalHook"),
        "people-story": ("人物故事", "人物故事", "FarmerStory"),
        "playful-contrast": ("轻松反差", "輕鬆反差", "PlayfulContrast"),
    }
    zh_cn, zh_hk, en = labels[route_id]
    return _localized(locale, zh_cn=zh_cn, zh_hk=zh_hk, en=en)


def _localized(locale: str, *, zh_cn: str, zh_hk: str, en: str) -> str:
    if locale == "en":
        return en
    if locale == "zh-HK":
        return zh_hk
    return zh_cn
