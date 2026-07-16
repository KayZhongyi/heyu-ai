import csv
import hashlib
import json
from io import BytesIO, StringIO
from zipfile import ZipFile

import pytest

from app.platform_exports import (
    EXPORT_FILENAMES,
    ExportCapabilityUnavailable,
    PlatformExportInput,
    PlatformValidationError,
    ShotListItem,
    SubtitleCue,
    build_zip_bytes,
    generate_platform_export,
    get_platform_adapter,
    get_platform_capabilities,
    protect_csv_cell,
    render_srt,
)


def _payload(platform: str, *, mode: str = "export_only") -> dict:
    return {
        "platform": platform,
        "mode": mode,
        "locale": "zh-CN",
        "title": "当季番茄，今天从田里出发",
        "caption": "清晨采摘，当天分拣。跟着镜头看看一颗番茄如何从田间走向餐桌。",
        "hashtags": ["#当季番茄", "助农", "乡村生活"],
        "cover_copy": "今天摘，今天讲",
        "subtitles": [
            {"start_ms": 0, "end_ms": 1750, "text": "你吃到的番茄，是什么时候摘的？"},
            {"start_ms": 1750, "end_ms": 4200, "text": "今天带你从田里看起。"},
        ],
        "shots": [
            {
                "order": 1,
                "seconds": "0-2秒",
                "visual": "番茄近景和清晨露水",
                "voiceover": "你吃到的番茄，是什么时候摘的？",
                "filming_tip": "逆光低机位",
            },
            ShotListItem(
                order=2,
                timing="2-5秒",
                visual="农户采摘并展示果实",
                voiceover="今天带你从田里看起。",
                filming_tip="手持跟拍",
            ),
        ],
        "checklist": ["核对商品链接和库存"],
    }


@pytest.mark.parametrize(
    ("platform", "adapter_name"),
    [
        ("douyin", "DouyinExportAdapter"),
        ("xiaohongshu", "XiaohongshuExportAdapter"),
        ("wechat_channels", "WechatChannelsExportAdapter"),
    ],
)
def test_each_platform_generates_complete_deterministic_package(platform, adapter_name):
    payload = _payload(platform)

    first = generate_platform_export(payload)
    second = get_platform_adapter(platform).export(payload)

    assert type(get_platform_adapter(platform)).__name__ == adapter_name
    assert tuple(first.files) == EXPORT_FILENAMES
    assert first.files == second.files
    assert first.zip_bytes() == second.zip_bytes()
    assert first.content_hash == second.content_hash
    assert first.zip_bytes().startswith(b"PK")

    with ZipFile(BytesIO(first.zip_bytes())) as archive:
        assert tuple(sorted(archive.namelist())) == tuple(sorted(EXPORT_FILENAMES))
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["platform"] == platform
        assert manifest["execution_mode"] == "export_only"
        assert manifest["performs_external_action"] is False
        assert manifest["automatic_publish"] is False
        assert manifest["package_content_sha256"] == first.content_hash
        assert manifest["authorized_api"]["available"] is False
        assert "未执行自动发布" in manifest["notice"]

        for record in manifest["files"]:
            content = archive.read(record["path"])
            assert hashlib.sha256(content).hexdigest() == record["sha256"]
            assert len(content) == record["size_bytes"]


def test_export_only_and_mock_are_explicitly_different_without_external_actions():
    exported = generate_platform_export(_payload("douyin", mode="export_only"))
    mocked = generate_platform_export(_payload("douyin", mode="mock"))

    assert exported.content_hash != mocked.content_hash
    assert exported.manifest["execution_mode"] == "export_only"
    assert mocked.manifest["execution_mode"] == "mock"
    assert exported.manifest["performs_external_action"] is False
    assert mocked.manifest["performs_external_action"] is False
    assert "人工导出模式" in exported.files["publishing-checklist.txt"].decode("utf-8")
    assert "演示模式" in mocked.files["publishing-checklist.txt"].decode("utf-8")
    assert "不会连接平台" in mocked.files["publishing-checklist.txt"].decode("utf-8")


def test_authorized_api_is_declared_but_cannot_be_executed():
    capabilities = get_platform_capabilities("抖音")

    assert capabilities["export_only"]["available"] is True
    assert capabilities["mock"]["available"] is True
    assert capabilities["authorized_api"] == {
        "available": False,
        "performs_external_action": False,
        "description": "尚未连接经授权的平台发布 API；当前版本不可用。",
    }

    with pytest.raises(ExportCapabilityUnavailable, match="authorized_api is unavailable"):
        generate_platform_export(_payload("douyin", mode="authorized_api"))


def test_srt_has_standard_timestamps_sequence_and_spacing():
    output = render_srt(
        [
            SubtitleCue(start_ms=0, end_ms=1234, text="第一句"),
            SubtitleCue(start_ms=62_345, end_ms=3_661_007, text="第二句\n第二行"),
        ]
    )

    assert output == (
        "1\n"
        "00:00:00,000 --> 00:00:01,234\n"
        "第一句\n\n"
        "2\n"
        "00:01:02,345 --> 01:01:01,007\n"
        "第二句\n"
        "第二行\n"
    )


@pytest.mark.parametrize(
    "cues",
    [
        [SubtitleCue(start_ms=-1, end_ms=100, text="bad")],
        [SubtitleCue(start_ms=100, end_ms=100, text="bad")],
        [
            SubtitleCue(start_ms=0, end_ms=200, text="one"),
            SubtitleCue(start_ms=199, end_ms=300, text="two"),
        ],
        [SubtitleCue(start_ms=0, end_ms=100, text="")],
    ],
)
def test_srt_rejects_invalid_timing_or_empty_text(cues):
    with pytest.raises(PlatformValidationError):
        render_srt(cues)


def test_shot_csv_protects_formula_injection_and_remains_parseable():
    payload = _payload("wechat_channels")
    payload["shots"] = [
        {
            "order": 1,
            "timing": "+1",
            "visual": '=HYPERLINK("https://evil.invalid")',
            "voiceover": " @SUM(A1:A2)",
            "filming_tip": "-2+3",
        }
    ]

    package = generate_platform_export(payload)
    rows = list(csv.reader(StringIO(package.files["shot-list.csv"].decode("utf-8"), newline="")))

    assert rows[0] == ["order", "timing", "visual", "voiceover", "filming_tip"]
    assert rows[1] == [
        "1",
        "'+1",
        '\'=HYPERLINK("https://evil.invalid")',
        "'@SUM(A1:A2)",
        "'-2+3",
    ]
    assert protect_csv_cell("ordinary text") == "ordinary text"
    assert protect_csv_cell("\t=1+1") == "'=1+1"


@pytest.mark.parametrize(
    "path",
    [
        "../secret.txt",
        "/absolute.txt",
        "folder/../../secret.txt",
        r"C:\secret.txt",
        r"..\secret.txt",
        "folder//file.txt",
    ],
)
def test_zip_builder_rejects_unsafe_paths(path):
    with pytest.raises(PlatformValidationError, match="unsafe ZIP path"):
        build_zip_bytes({path: b"content"})


def test_platform_specific_validation_is_applied():
    xiaohongshu = _payload("xiaohongshu")
    xiaohongshu["title"] = "很长的标题" * 10
    with pytest.raises(PlatformValidationError, match="小红书 export title exceeds 20"):
        generate_platform_export(xiaohongshu)

    douyin = _payload("douyin")
    douyin["hashtags"] = [f"话题{index}" for index in range(11)]
    with pytest.raises(PlatformValidationError, match="抖音 export has more than 10"):
        generate_platform_export(douyin)

    mismatch = PlatformExportInput(
        platform="douyin",
        title="标题",
        caption="正文",
        cover_copy="封面",
        shots=(ShotListItem(order=1, timing="0-2秒", visual="田间"),),
    )
    with pytest.raises(PlatformValidationError, match="cannot export"):
        get_platform_adapter("xiaohongshu").export(mismatch)


def test_manifest_hash_changes_when_content_changes_but_not_between_identical_runs():
    original = _payload("douyin")
    changed = _payload("douyin")
    changed["caption"] = changed["caption"] + " 明天继续记录。"

    first = generate_platform_export(original)
    repeated = generate_platform_export(original)
    modified = generate_platform_export(changed)

    assert first.content_hash == repeated.content_hash
    assert first.zip_bytes() == repeated.zip_bytes()
    assert first.content_hash != modified.content_hash
    assert first.zip_bytes() != modified.zip_bytes()
