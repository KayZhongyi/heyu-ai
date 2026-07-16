"""Deterministic, manual-first export packages for Chinese content platforms.

This module deliberately does not publish content. ``export_only`` creates a
package for a person to review and upload, while ``mock`` creates the same
artifacts for a no-side-effect demonstration. ``authorized_api`` is declared as
unavailable until a real, reviewed platform integration exists.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from typing import Any, Literal
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

Platform = Literal["douyin", "xiaohongshu", "wechat_channels"]
ExecutionMode = Literal["export_only", "mock"]

EXPORT_FILENAMES = (
    "title.txt",
    "caption.txt",
    "hashtags.txt",
    "cover-copy.txt",
    "subtitles.srt",
    "shot-list.csv",
    "publishing-checklist.txt",
    "manifest.json",
)
_CONTENT_FILENAMES = EXPORT_FILENAMES[:-1]
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_HASHTAG_PREFIX = re.compile(r"^#+")
_WHITESPACE = re.compile(r"[ \t]+")
_DANGEROUS_CSV_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


class PlatformExportError(ValueError):
    """Base error for invalid or unsupported platform exports."""


class PlatformValidationError(PlatformExportError):
    """Raised when content does not satisfy the selected export profile."""


class ExportCapabilityUnavailable(PlatformExportError):
    """Raised when a caller requests a capability that is not implemented."""


@dataclass(frozen=True, slots=True)
class PlatformExportProfile:
    """Conservative package constraints, not official platform API guarantees."""

    platform: Platform
    display_name: str
    title_max_characters: int
    caption_max_characters: int
    hashtag_max_count: int


PLATFORM_PROFILES: dict[Platform, PlatformExportProfile] = {
    "douyin": PlatformExportProfile(
        platform="douyin",
        display_name="抖音",
        title_max_characters=55,
        caption_max_characters=2200,
        hashtag_max_count=10,
    ),
    "xiaohongshu": PlatformExportProfile(
        platform="xiaohongshu",
        display_name="小红书",
        title_max_characters=20,
        caption_max_characters=1000,
        hashtag_max_count=10,
    ),
    "wechat_channels": PlatformExportProfile(
        platform="wechat_channels",
        display_name="视频号",
        title_max_characters=30,
        caption_max_characters=2000,
        hashtag_max_count=10,
    ),
}

PLATFORM_CAPABILITIES: dict[Platform, dict[str, dict[str, Any]]] = {
    platform: {
        "export_only": {
            "available": True,
            "performs_external_action": False,
            "description": "生成供人工审核和上传的平台文件包。",
        },
        "mock": {
            "available": True,
            "performs_external_action": False,
            "description": "仅模拟导出流程，不连接平台，也不执行发布。",
        },
        "authorized_api": {
            "available": False,
            "performs_external_action": False,
            "description": "尚未连接经授权的平台发布 API；当前版本不可用。",
        },
    }
    for platform in PLATFORM_PROFILES
}


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class ShotListItem:
    order: int
    timing: str
    visual: str
    voiceover: str = ""
    filming_tip: str = ""


@dataclass(frozen=True, slots=True)
class PlatformExportInput:
    platform: Platform
    title: str
    caption: str
    hashtags: Sequence[str] = field(default_factory=tuple)
    cover_copy: str = ""
    subtitles: Sequence[SubtitleCue | Mapping[str, Any]] = field(default_factory=tuple)
    shots: Sequence[ShotListItem | Mapping[str, Any]] = field(default_factory=tuple)
    checklist: Sequence[str] = field(default_factory=tuple)
    locale: str = "zh-CN"
    mode: ExecutionMode = "export_only"


@dataclass(frozen=True, slots=True)
class PlatformExportPackage:
    platform: Platform
    mode: ExecutionMode
    files: Mapping[str, bytes]
    content_hash: str
    manifest: Mapping[str, Any]

    def zip_bytes(self) -> bytes:
        """Return byte-for-byte deterministic ZIP output."""

        return build_zip_bytes(self.files)


class BasePlatformExportAdapter:
    platform: Platform

    def export(
        self,
        payload: PlatformExportInput | Mapping[str, Any] | Any,
    ) -> PlatformExportPackage:
        data = _coerce_input(payload, expected_platform=self.platform)
        return _generate_package(data)

    def validate(
        self,
        payload: PlatformExportInput | Mapping[str, Any] | Any,
    ) -> None:
        data = _coerce_input(payload, expected_platform=self.platform)
        _validate_input(data)


class DouyinExportAdapter(BasePlatformExportAdapter):
    platform: Platform = "douyin"


class XiaohongshuExportAdapter(BasePlatformExportAdapter):
    platform: Platform = "xiaohongshu"


class WechatChannelsExportAdapter(BasePlatformExportAdapter):
    platform: Platform = "wechat_channels"


_ADAPTERS: dict[Platform, BasePlatformExportAdapter] = {
    "douyin": DouyinExportAdapter(),
    "xiaohongshu": XiaohongshuExportAdapter(),
    "wechat_channels": WechatChannelsExportAdapter(),
}


def get_platform_capabilities(platform: Platform | str) -> Mapping[str, Mapping[str, Any]]:
    """Return an immutable-by-convention capability declaration."""

    normalized = _normalize_platform(platform)
    return PLATFORM_CAPABILITIES[normalized]


def get_platform_adapter(platform: Platform | str) -> BasePlatformExportAdapter:
    return _ADAPTERS[_normalize_platform(platform)]


def generate_platform_export(
    payload: PlatformExportInput | Mapping[str, Any] | Any,
) -> PlatformExportPackage:
    platform = _normalize_platform(_read(payload, "platform", ""))
    return get_platform_adapter(platform).export(payload)


def build_zip_bytes(files: Mapping[str, bytes | str]) -> bytes:
    """Build a deterministic ZIP and reject unsafe or duplicate archive paths."""

    normalized: dict[str, bytes] = {}
    for raw_path, raw_content in files.items():
        path = _validate_archive_path(raw_path)
        if path in normalized:
            raise PlatformValidationError(f"duplicate ZIP path: {path}")
        normalized[path] = (
            raw_content.encode("utf-8") if isinstance(raw_content, str) else bytes(raw_content)
        )

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(normalized):
            info = ZipInfo(filename=path, date_time=_ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            archive.writestr(info, normalized[path], compress_type=ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def protect_csv_cell(value: Any) -> str:
    """Prevent spreadsheet programs from interpreting exported text as a formula."""

    text = _clean_multiline_text(value)
    candidate = text.lstrip(" ")
    if candidate.startswith(_DANGEROUS_CSV_PREFIXES):
        return "'" + text
    return text


def render_srt(cues: Sequence[SubtitleCue | Mapping[str, Any]]) -> str:
    normalized = tuple(_coerce_subtitle(cue) for cue in cues)
    _validate_subtitles(normalized)
    blocks = [
        f"{index}\n{_format_srt_timestamp(cue.start_ms)} --> "
        f"{_format_srt_timestamp(cue.end_ms)}\n{_clean_multiline_text(cue.text)}"
        for index, cue in enumerate(normalized, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _generate_package(data: PlatformExportInput) -> PlatformExportPackage:
    _validate_input(data)
    profile = PLATFORM_PROFILES[data.platform]
    hashtags = tuple(_normalize_hashtag(value) for value in data.hashtags)
    shots = tuple(_coerce_shot(value, index) for index, value in enumerate(data.shots, start=1))

    text_files = {
        "title.txt": _text_file(data.title),
        "caption.txt": _text_file(data.caption),
        "hashtags.txt": _text_file(" ".join(f"#{value}" for value in hashtags)),
        "cover-copy.txt": _text_file(data.cover_copy),
        "subtitles.srt": render_srt(data.subtitles),
        "shot-list.csv": _render_shot_list_csv(shots),
        "publishing-checklist.txt": _render_checklist(data, profile),
    }
    content_files = {name: value.encode("utf-8") for name, value in text_files.items()}
    file_hashes = {
        name: hashlib.sha256(content_files[name]).hexdigest() for name in _CONTENT_FILENAMES
    }
    content_hash = _package_content_hash(file_hashes)
    manifest: dict[str, Any] = {
        "schema_version": "platform-export-v1",
        "platform": data.platform,
        "platform_name": profile.display_name,
        "execution_mode": data.mode,
        "locale": data.locale,
        "performs_external_action": False,
        "automatic_publish": False,
        "authorized_api": PLATFORM_CAPABILITIES[data.platform]["authorized_api"],
        "notice": _mode_notice(data.mode),
        "package_content_sha256": content_hash,
        "files": [
            {
                "path": name,
                "media_type": _media_type(name),
                "sha256": file_hashes[name],
                "size_bytes": len(content_files[name]),
            }
            for name in _CONTENT_FILENAMES
        ],
        "validation_profile": {
            "title_max_characters": profile.title_max_characters,
            "caption_max_characters": profile.caption_max_characters,
            "hashtag_max_count": profile.hashtag_max_count,
            "profile_notice": "导出约束为平台协作基线，不代表官方 API 发布校验。",
        },
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    files = {**content_files, "manifest.json": manifest_bytes}
    return PlatformExportPackage(
        platform=data.platform,
        mode=data.mode,
        files=files,
        content_hash=content_hash,
        manifest=manifest,
    )


def _validate_input(data: PlatformExportInput) -> None:
    if data.mode not in ("export_only", "mock"):
        if data.mode == "authorized_api":
            raise ExportCapabilityUnavailable(
                "authorized_api is unavailable; use export_only or mock instead"
            )
        raise PlatformValidationError(f"unsupported execution mode: {data.mode}")

    profile = PLATFORM_PROFILES[data.platform]
    title = _clean_single_line_text(data.title)
    caption = _clean_multiline_text(data.caption)
    cover_copy = _clean_single_line_text(data.cover_copy)
    if not title:
        raise PlatformValidationError("title is required")
    if not caption:
        raise PlatformValidationError("caption is required")
    if not cover_copy:
        raise PlatformValidationError("cover_copy is required")
    if len(title) > profile.title_max_characters:
        raise PlatformValidationError(
            f"{profile.display_name} export title exceeds {profile.title_max_characters} characters"
        )
    if len(caption) > profile.caption_max_characters:
        raise PlatformValidationError(
            f"{profile.display_name} export caption exceeds "
            f"{profile.caption_max_characters} characters"
        )

    hashtags = tuple(_normalize_hashtag(value) for value in data.hashtags)
    if len(hashtags) > profile.hashtag_max_count:
        raise PlatformValidationError(
            f"{profile.display_name} export has more than {profile.hashtag_max_count} hashtags"
        )
    if len(set(hashtags)) != len(hashtags):
        raise PlatformValidationError("hashtags must be unique after normalization")
    if not data.shots:
        raise PlatformValidationError("at least one shot is required")
    _validate_subtitles(tuple(_coerce_subtitle(cue) for cue in data.subtitles))
    for index, raw_shot in enumerate(data.shots, start=1):
        shot = _coerce_shot(raw_shot, index)
        if shot.order < 1:
            raise PlatformValidationError("shot order must be positive")
        if not shot.timing or not shot.visual:
            raise PlatformValidationError("every shot requires timing and visual")


def _validate_subtitles(cues: Sequence[SubtitleCue]) -> None:
    previous_end = -1
    for cue in cues:
        if cue.start_ms < 0:
            raise PlatformValidationError("subtitle start_ms cannot be negative")
        if cue.end_ms <= cue.start_ms:
            raise PlatformValidationError("subtitle end_ms must be greater than start_ms")
        if cue.start_ms < previous_end:
            raise PlatformValidationError("subtitle cues cannot overlap")
        if not _clean_multiline_text(cue.text):
            raise PlatformValidationError("subtitle text cannot be empty")
        previous_end = cue.end_ms


def _render_shot_list_csv(shots: Sequence[ShotListItem]) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("order", "timing", "visual", "voiceover", "filming_tip"))
    for shot in sorted(shots, key=lambda item: item.order):
        writer.writerow(
            (
                shot.order,
                protect_csv_cell(shot.timing),
                protect_csv_cell(shot.visual),
                protect_csv_cell(shot.voiceover),
                protect_csv_cell(shot.filming_tip),
            )
        )
    return output.getvalue()


def _render_checklist(data: PlatformExportInput, profile: PlatformExportProfile) -> str:
    mode_line = (
        "当前为演示模式：不会连接平台，也不会执行真实发布。"
        if data.mode == "mock"
        else "当前为人工导出模式：请审核文件后，由负责人手动上传和发布。"
    )
    default_items = (
        "确认标题、正文、封面文案与产品事实一致",
        "确认字幕时间轴和镜头清单与最终视频一致",
        "确认音乐、图片、字体和人物肖像已获得使用许可",
        f"在{profile.display_name}发布页再次检查平台提示与最新规则",
        "由负责人完成最终审核并手动确认发布",
    )
    items = tuple(_clean_single_line_text(item) for item in data.checklist if str(item).strip())
    lines = [
        f"{profile.display_name}发布协作清单",
        "",
        mode_line,
        "本导出包不具备自动发布能力。",
        "",
    ]
    lines.extend(f"[ ] {item}" for item in (*default_items, *items))
    return "\n".join(lines) + "\n"


def _coerce_input(
    payload: PlatformExportInput | Mapping[str, Any] | Any,
    *,
    expected_platform: Platform,
) -> PlatformExportInput:
    if isinstance(payload, PlatformExportInput):
        data = payload
    else:
        data = PlatformExportInput(
            platform=_normalize_platform(_read(payload, "platform", expected_platform)),
            title=_text(_read(payload, "title", "")),
            caption=_text(_read(payload, "caption", "")),
            hashtags=_sequence(_read(payload, "hashtags", ())),
            cover_copy=_text(_read_first(payload, ("cover_copy", "cover_text"), "")),
            subtitles=_sequence(_read(payload, "subtitles", ())),
            shots=_sequence(_read_first(payload, ("shots", "shot_list"), ())),
            checklist=_sequence(_read(payload, "checklist", ())),
            locale=_text(_read(payload, "locale", "zh-CN")),
            mode=_text(_read(payload, "mode", "export_only")),  # type: ignore[arg-type]
        )
    if data.platform != expected_platform:
        raise PlatformValidationError(
            f"adapter for {expected_platform} cannot export {data.platform}"
        )
    return data


def _coerce_subtitle(value: SubtitleCue | Mapping[str, Any] | Any) -> SubtitleCue:
    if isinstance(value, SubtitleCue):
        return value
    return SubtitleCue(
        start_ms=_integer(_read(value, "start_ms", -1), "subtitle start_ms"),
        end_ms=_integer(_read(value, "end_ms", -1), "subtitle end_ms"),
        text=_text(_read(value, "text", "")),
    )


def _coerce_shot(
    value: ShotListItem | Mapping[str, Any] | Any,
    default_order: int,
) -> ShotListItem:
    if isinstance(value, ShotListItem):
        return value
    return ShotListItem(
        order=_integer(_read(value, "order", default_order), "shot order"),
        timing=_text(_read_first(value, ("timing", "seconds"), "")),
        visual=_text(_read(value, "visual", "")),
        voiceover=_text(_read(value, "voiceover", "")),
        filming_tip=_text(_read(value, "filming_tip", "")),
    )


def _normalize_platform(value: Any) -> Platform:
    normalized = _text(value).strip().lower().replace("-", "_")
    aliases = {
        "douyin": "douyin",
        "抖音": "douyin",
        "xiaohongshu": "xiaohongshu",
        "xhs": "xiaohongshu",
        "小红书": "xiaohongshu",
        "wechat_channels": "wechat_channels",
        "wechat_video": "wechat_channels",
        "视频号": "wechat_channels",
        "視頻號": "wechat_channels",
    }
    try:
        return aliases[normalized]  # type: ignore[return-value]
    except KeyError as exc:
        raise PlatformValidationError(f"unsupported platform: {value}") from exc


def _normalize_hashtag(value: Any) -> str:
    text = _clean_single_line_text(value)
    text = _HASHTAG_PREFIX.sub("", text).strip()
    text = _WHITESPACE.sub("", text)
    if not text:
        raise PlatformValidationError("hashtags cannot be empty")
    if any(character in text for character in ("\n", "\r", "\x00")):
        raise PlatformValidationError("hashtags must be single-line text")
    return text


def _validate_archive_path(value: Any) -> str:
    path = _text(value).replace("\\", "/")
    pure_path = PurePosixPath(path)
    if (
        not path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or any(part in ("", ".", "..") for part in pure_path.parts)
        or str(pure_path) != path
    ):
        raise PlatformValidationError(f"unsafe ZIP path: {value}")
    return path


def _package_content_hash(file_hashes: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(file_hashes):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hashes[name].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _format_srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _mode_notice(mode: ExecutionMode) -> str:
    if mode == "mock":
        return "演示导出：未连接外部平台，未执行真实发布。"
    return "人工导出：文件需经审核后由负责人手动上传；未执行自动发布。"


def _media_type(filename: str) -> str:
    if filename.endswith(".json"):
        return "application/json"
    if filename.endswith(".csv"):
        return "text/csv; charset=utf-8"
    if filename.endswith(".srt"):
        return "application/x-subrip; charset=utf-8"
    return "text/plain; charset=utf-8"


def _text_file(value: Any) -> str:
    return _clean_multiline_text(value).rstrip("\n") + "\n"


def _clean_single_line_text(value: Any) -> str:
    return " ".join(_text(value).replace("\x00", "").split())


def _clean_multiline_text(value: Any) -> str:
    text = _text(value).replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(" ".join(line.split()) for line in text.split("\n")).strip()


def _read(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _read_first(value: Any, names: Sequence[str], default: Any) -> Any:
    for name in names:
        result = _read(value, name, None)
        if result is not None:
            return result
    return default


def _sequence(value: Any) -> Sequence[Any]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _integer(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PlatformValidationError(f"{field_name} must be an integer") from exc


def _text(value: Any) -> str:
    return "" if value is None else str(value)


__all__ = [
    "BasePlatformExportAdapter",
    "DouyinExportAdapter",
    "ExecutionMode",
    "EXPORT_FILENAMES",
    "ExportCapabilityUnavailable",
    "PLATFORM_CAPABILITIES",
    "PLATFORM_PROFILES",
    "Platform",
    "PlatformExportError",
    "PlatformExportInput",
    "PlatformExportPackage",
    "PlatformExportProfile",
    "PlatformValidationError",
    "ShotListItem",
    "SubtitleCue",
    "WechatChannelsExportAdapter",
    "XiaohongshuExportAdapter",
    "build_zip_bytes",
    "generate_platform_export",
    "get_platform_adapter",
    "get_platform_capabilities",
    "protect_csv_cell",
    "render_srt",
]
