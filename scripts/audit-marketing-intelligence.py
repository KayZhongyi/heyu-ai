#!/usr/bin/env python3
"""Run repeatable quality checks for the farmer marketing intelligence flow."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.marketing import (  # noqa: E402
    DeterministicMarketingProvider,
    MarketingPlanRequest,
)


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    request: dict[str, Any]


SCENARIOS = (
    Scenario(
        key="tomato-douyin",
        label="当季番茄 × 抖音",
        request={
            "locale": "zh-CN",
            "persona": "farmer",
            "goals": ["sell", "gain-followers"],
            "product_name": "当季番茄",
            "origin": "广东清远",
            "product_description": (
                "自然成熟后采摘，清甜多汁，农场会在采摘当天完成分选和装箱，"
                "适合家庭鲜食与日常做菜。"
            ),
            "selling_points": ["自然成熟", "清甜多汁", "当天分选"],
            "audience": "重视新鲜食材的年轻家庭",
            "platform": "douyin",
            "tone": "lively",
            "trend": "夏日轻食",
        },
    ),
    Scenario(
        key="tea-xiaohongshu",
        label="高山云雾茶 × 小红书",
        request={
            "locale": "zh-CN",
            "persona": "cooperative",
            "goals": ["sell", "build-brand"],
            "product_name": "高山云雾茶",
            "origin": "贵州黔南",
            "product_description": (
                "春季嫩叶分批采摘，由合作社统一摊晾、制作和分级。"
                "茶汤清爽，带自然花香，适合日常清饮。"
            ),
            "selling_points": ["高山茶园", "春季嫩叶", "合作社分级", "清爽花香"],
            "audience": "关注产地与制作过程的城市饮茶人群",
            "platform": "xiaohongshu",
            "tone": "premium",
            "trend": "办公室轻养生",
        },
    ),
    Scenario(
        key="fruit-wechat",
        label="岭南时令水果礼盒 × 视频号",
        request={
            "locale": "zh-HK",
            "persona": "rural-operator",
            "goals": ["sell", "build-brand", "promote-tourism"],
            "product_name": "嶺南時令水果禮盒",
            "origin": "廣東茂名",
            "product_description": (
                "按每週成熟情況組合本地時令水果，由鄉村營運團隊與果園確認"
                "採摘批次、分選標準及送貨安排，適合家庭分享及節日送禮。"
            ),
            "selling_points": ["時令組合", "果園直採", "按批次分選", "適合分享"],
            "audience": "重視時令風味及果園故事的家庭與送禮人士",
            "platform": "wechat-channels",
            "tone": "warm",
            "trend": "週末果園與時令伴手禮",
        },
    ),
)

CORRUPTION_MARKERS = ("\ufffd", "????", "锛", "鈥", "銆")
EXPECTED_ROUTES = ["practical-hook", "people-story", "playful-contrast"]
EXPECTED_SIGNALS = ["manual-hotspot", "seasonal-farming", "evergreen-pain-point"]


def contains_corruption(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=False)
    return any(marker in text for marker in CORRUPTION_MARKERS)


def audit_scenario(scenario: Scenario) -> dict[str, Any]:
    request = MarketingPlanRequest.model_validate(scenario.request)
    result = DeterministicMarketingProvider().generate(request)
    payload = result.model_dump(mode="json")
    route_ids = [item["route_id"] for item in payload["creative_routes"]]
    video_route_ids = [item["route_id"] for item in payload["videos"]]
    signal_types = [item["signal_type"] for item in payload["topic_signals"]]
    quality_scores = [
        int(item["quality_assessment"]["total_score"]) for item in payload["videos"]
    ]
    checks = {
        "three_distinct_routes": route_ids == EXPECTED_ROUTES,
        "videos_map_to_routes": video_route_ids == EXPECTED_ROUTES,
        "three_topic_signal_types": signal_types == EXPECTED_SIGNALS,
        "topic_scores_explained": all(
            item["explanation"] and item["usage_caution"] and item["source_note"]
            for item in payload["topic_signals"]
        ),
        "quality_scores_pass_floor": all(score >= 70 for score in quality_scores),
        "quality_feedback_actionable": all(
            len(item["quality_assessment"]["strengths"]) >= 2
            and len(item["quality_assessment"]["improvements"]) >= 1
            for item in payload["videos"]
        ),
        "workflow_has_three_stages": len(payload["next_step"]["stages"]) == 3,
        "no_encoding_corruption": not contains_corruption(payload),
        "product_preserved": scenario.request["product_name"]
        in payload["product_profile"]["one_line_value"],
    }
    return {
        "key": scenario.key,
        "label": scenario.label,
        "passed": all(checks.values()),
        "checks": checks,
        "quality_scores": quality_scores,
        "recommended_topic": max(
            payload["topic_signals"], key=lambda item: item["total_score"]
        ),
        "routes": [
            {
                "route_id": video["route_id"],
                "angle": video["angle"],
                "title": video["title"],
                "cover_text": video["cover_text"],
                "hook": video["hook"],
                "script": video["script"],
                "background_music": video["background_music"],
                "shots": video["shots"],
                "call_to_action": video["call_to_action"],
                "quality_score": video["quality_assessment"]["total_score"],
                "strengths": video["quality_assessment"]["strengths"],
                "improvements": video["quality_assessment"]["improvements"],
            }
            for video in payload["videos"]
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 禾语 AI 营销智能质量审计",
        "",
        f"- 总体结果：{'通过' if report['passed'] else '未通过'}",
        f"- 场景数：{len(report['scenarios'])}",
        "",
    ]
    for scenario in report["scenarios"]:
        lines.extend(
            [
                f"## {scenario['label']}",
                "",
                f"- 结果：{'通过' if scenario['passed'] else '未通过'}",
                f"- 三条路线质量分：{', '.join(map(str, scenario['quality_scores']))}",
                f"- 推荐选题：{scenario['recommended_topic']['title']} "
                f"({scenario['recommended_topic']['total_score']}/100)",
                "",
                "| 检查项 | 结果 |",
                "| --- | --- |",
            ]
        )
        for name, passed in scenario["checks"].items():
            lines.append(f"| `{name}` | {'通过' if passed else '失败'} |")
        lines.extend(["", "| 路线 | 标题 | 质量分 |", "| --- | --- | --- |"])
        for route in scenario["routes"]:
            lines.append(
                f"| `{route['route_id']}` | {route['title']} | {route['quality_score']} |"
            )
        lines.append("")
        for route in scenario["routes"]:
            lines.extend(
                [
                    f"### {route['angle']}（`{route['route_id']}`）",
                    "",
                    f"- 封面：{route['cover_text']}",
                    f"- 前三秒：{route['hook']}",
                    f"- BGM：{route['background_music']}",
                    f"- CTA：{route['call_to_action']}",
                    f"- 脚本：{route['script']}",
                    "",
                    "| 时间 | 画面 | 口播/字幕 | 拍摄提示 |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for shot in route["shots"]:
                lines.append(
                    f"| {shot['seconds']} | {shot['visual']} | {shot['voiceover']} | "
                    f"{shot['filming_tip']} |"
                )
            lines.extend(
                [
                    "",
                    f"- 优点：{'；'.join(route['strengths'])}",
                    f"- 下一轮改进：{'；'.join(route['improvements'])}",
                    "",
                ]
            )
    lines.extend(
        [
            "## 人工复核清单",
            "",
            "- 开头是否在三秒内建立明确问题、反差或人物悬念。",
            "- 农户能否仅使用手机和现有场地完成拍摄。",
            "- 热点是否与产品和人群自然相关，而不是机械拼接。",
            "- 文案是否只使用输入中能够证实的产品事实。",
            "- 三条路线是否在叙事机制上明显不同，而不只是换标题。",
            "- 结尾是否只有一个清楚、可执行的互动或转化动作。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json-output",
        type=Path,
        default=ROOT / "outputs" / "marketing-intelligence-audit.json",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=ROOT / "outputs" / "marketing-intelligence-audit.md",
    )
    args = parser.parse_args()

    scenarios = [audit_scenario(scenario) for scenario in SCENARIOS]
    report = {
        "passed": all(item["passed"] for item in scenarios),
        "scenarios": scenarios,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
