#!/usr/bin/env python3
"""Run the versioned, offline marketing-content quality baseline.

The evaluator intentionally calls the deterministic marketing provider directly.
It does not open a database session or create business records.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.marketing import (  # noqa: E402
    DeterministicMarketingProvider,
    MarketingPlanRequest,
    MarketingPlanResponse,
)

EVALUATOR_VERSION = "marketing-rules-v2"
DEFAULT_DATASET = ROOT / "evals" / "marketing" / "dataset-v1.json"
DEFAULT_BASELINE = ROOT / "evals" / "marketing" / "baseline-v2.json"
DEFAULT_OUTPUT = ROOT / "outputs" / "content-quality-evaluation.json"
DIMENSIONS = (
    "schema",
    "factual_grounding",
    "prohibited_claims",
    "citations",
    "language",
    "marketing_expression",
    "platform_fit",
    "filmability",
    "hook_specificity",
    "curiosity_gap",
    "route_distinctiveness",
    "visual_proof",
    "trend_integration",
    "interaction_trigger",
    "shot_voice_alignment",
    "farmer_filmability",
    "ad_cliche_penalty",
)
DISCLAIMER = (
    "Rule scores assess structure, factual retention, prohibited claims, citation "
    "allowlisting, language, platform fit, hook specificity, route separation, "
    "visual proof, trend integration, interaction design and phone-filmability. "
    "They do not predict or guarantee views, engagement, sales or real-world reach."
)

SIMPLIFIED_ONLY_TERMS = (
    "这个",
    "视频",
    "数据",
    "用户",
    "产品",
    "农户",
    "选择",
    "真实",
    "发布",
    "问题",
    "评论",
    "价格",
    "发货",
    "不一样",
)
HIGH_RISK_PATTERNS = (
    re.compile(
        r"(治疗|治愈|抗癌|防癌|降血糖|百分之百有效|100\s*%\s*有效|"
        r"全网(?:销量)?第一|国家级认证)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(cures?|treats?|anti-cancer|prevents? cancer|lowers? blood sugar|"
        r"guaranteed weight loss|number one|100\s*%\s*effective)\b",
        re.IGNORECASE,
    ),
)
VAGUE_HOOK_PATTERNS = (
    re.compile(r"(这个|這個|this)\s*(细节|細節|detail)", re.IGNORECASE),
    re.compile(r"(下一镜|下一鏡|next shot).*(不一样|不一樣|different)", re.IGNORECASE),
    re.compile(r"(先看|先睇|check)\s*(这里|這裡|this)", re.IGNORECASE),
)
HOOK_DEVICES = (
    "？",
    "?",
    "为什么",
    "為什麼",
    "why",
    "先别",
    "先別",
    "before",
    "哪一",
    "哪份",
    "which",
    "你会选",
    "你會選",
    "would you choose",
    "不是",
    "而是",
    "not",
    "——",
)
VISUAL_ACTION_TOKENS = (
    "切",
    "称",
    "稱",
    "翻",
    "拍",
    "摘",
    "采",
    "採",
    "装箱",
    "裝箱",
    "冲泡",
    "沖泡",
    "注水",
    "出汤",
    "出湯",
    "对比",
    "對比",
    "并排",
    "並排",
    "近景",
    "特写",
    "特寫",
    "close-up",
    "cut",
    "weigh",
    "pour",
    "compare",
    "side by side",
    "harvest",
    "sort",
    "pack",
)
CLICHE_PATTERNS = (
    re.compile(r"(品质好|品質好|味道好|值得购买|值得購買|不容错过|不容錯過|匠心打造)"),
    re.compile(
        r"\b(high quality|great taste|worth buying|must[- ]buy|best choice|"
        r"you won'?t want to miss)\b",
        re.IGNORECASE,
    ),
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return "\n".join(_flatten_text(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "\n".join(_flatten_text(item) for item in value)
    return ""


def _score(checks: Iterable[bool]) -> int:
    values = list(checks)
    if not values:
        return 100
    return round(sum(1 for value in values if value) * 100 / len(values))


def _rule(score: int, details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "score": max(0, min(100, int(score))),
        "passed": score >= 70,
        "details": dict(details),
    }


def _extract_citation_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "source_id" and isinstance(item, str):
                found.add(item)
            elif (
                key == "source_ids"
                and isinstance(item, Sequence)
                and not isinstance(item, (str, bytes, bytearray))
            ):
                found.update(str(source_id) for source_id in item)
            elif (
                key == "citations"
                and isinstance(item, Sequence)
                and not isinstance(item, (str, bytes, bytearray))
            ):
                for citation in item:
                    if isinstance(citation, str):
                        found.add(citation)
                    elif isinstance(citation, Mapping):
                        source_id = citation.get("source_id")
                        if isinstance(source_id, str):
                            found.add(source_id)
            found.update(_extract_citation_ids(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            found.update(_extract_citation_ids(item))
    return found


def _evaluate_schema(
    output: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        validated = MarketingPlanResponse.model_validate(output)
    except ValidationError as exc:
        errors = [
            {
                "location": ".".join(str(part) for part in error["loc"]),
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return _rule(0, {"valid": False, "errors": errors}), dict(output)
    return _rule(100, {"valid": True, "errors": []}), validated.model_dump(mode="json")


def _evaluate_facts(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    text = _normalize(_flatten_text(output))
    expected = [str(item) for item in case.get("expected_facts", [])]
    present = [fact for fact in expected if _normalize(fact) in text]
    missing = [fact for fact in expected if fact not in present]
    return _rule(
        _score(fact in present for fact in expected),
        {"expected": expected, "present": present, "missing": missing},
    )


def _evaluate_prohibited_claims(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    text = _flatten_text(output)
    case_claims = [str(item) for item in case.get("forbidden_claims", [])]
    matched = [claim for claim in case_claims if _normalize(claim) in _normalize(text)]
    generic_matches = sorted(
        {
            match.group(0)
            for pattern in HIGH_RISK_PATTERNS
            for match in pattern.finditer(text)
        }
    )
    all_matches = sorted(set(matched + generic_matches))
    return _rule(
        100 if not all_matches else 0,
        {"matched": all_matches, "case_forbidden_claims": case_claims},
    )


def _evaluate_citations(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    expected = {str(item) for item in case.get("expected_source_ids", [])}
    cited = _extract_citation_ids(output)
    unknown = cited - expected
    policy = str(case.get("citation_policy", "required"))
    missing = expected - cited if policy == "required" else set()
    passed = not unknown and not missing
    status = (
        "not_required"
        if not expected and not cited and policy != "required"
        else "checked"
    )
    return _rule(
        100 if passed else 0,
        {
            "policy": policy,
            "status": status,
            "expected_source_ids": sorted(expected),
            "cited_source_ids": sorted(cited),
            "unknown_source_ids": sorted(unknown),
            "missing_source_ids": sorted(missing),
        },
    )


def _evaluate_language(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    locale = str(case["locale"])
    text = _flatten_text(output)
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    if locale == "en":
        cjk_ratio = cjk_count / max(cjk_count + latin_count, 1)
        checks = [latin_count >= 120, cjk_ratio <= 0.02]
        details = {
            "locale": locale,
            "latin_characters": latin_count,
            "cjk_characters": cjk_count,
            "cjk_ratio": round(cjk_ratio, 4),
        }
    elif locale == "zh-HK":
        simplified_hits = [term for term in SIMPLIFIED_ONLY_TERMS if term in text]
        checks = [cjk_count >= 120, not simplified_hits]
        details = {
            "locale": locale,
            "cjk_characters": cjk_count,
            "simplified_only_terms": simplified_hits,
        }
    else:
        checks = [cjk_count >= 120]
        details = {"locale": locale, "cjk_characters": cjk_count}
    return _rule(_score(checks), details)


def _evaluate_marketing_expression(output: Mapping[str, Any]) -> dict[str, Any]:
    videos = output.get("videos", [])
    routes = output.get("creative_routes", [])
    if not isinstance(videos, list):
        videos = []
    if not isinstance(routes, list):
        routes = []
    route_ids = [item.get("route_id") for item in routes if isinstance(item, Mapping)]
    titles = [
        _normalize(str(item.get("title", "")))
        for item in videos
        if isinstance(item, Mapping)
    ]
    hooks = [
        _normalize(str(item.get("hook", "")))
        for item in videos
        if isinstance(item, Mapping)
    ]
    calls_to_action = [
        str(item.get("call_to_action", "")).strip()
        for item in videos
        if isinstance(item, Mapping)
    ]
    checks = {
        "three_routes": route_ids
        == ["practical-hook", "people-story", "playful-contrast"],
        "three_videos": len(videos) == 3,
        "distinct_titles": len(titles) == 3 and len(set(titles)) == 3 and all(titles),
        "distinct_hooks": len(hooks) == 3 and len(set(hooks)) == 3 and all(hooks),
        "clear_calls_to_action": len(calls_to_action) == 3 and all(calls_to_action),
    }
    return _rule(_score(checks.values()), checks)


def _evaluate_platform_fit(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    strategy = output.get("strategy")
    if not isinstance(strategy, Mapping):
        strategy = {}
    expected_platform = str(case["expected_platform"])
    checks = {
        "platform_matches_request": strategy.get("platform") == expected_platform,
        "platform_name_present": bool(str(strategy.get("platform_name", "")).strip()),
        "content_focus_present": bool(str(strategy.get("content_focus", "")).strip()),
        "duration_present": bool(str(strategy.get("recommended_duration", "")).strip()),
        "conversion_action_present": bool(
            str(strategy.get("conversion_action", "")).strip()
        ),
    }
    return _rule(_score(checks.values()), checks)


def _evaluate_filmability(output: Mapping[str, Any]) -> dict[str, Any]:
    videos = output.get("videos", [])
    if not isinstance(videos, list):
        videos = []
    valid_videos = [item for item in videos if isinstance(item, Mapping)]
    shot_lists = [item.get("shots", []) for item in valid_videos]
    checks = {
        "three_video_options": len(valid_videos) == 3,
        "at_least_three_shots_each": bool(shot_lists)
        and all(isinstance(shots, list) and len(shots) >= 3 for shots in shot_lists),
        "shots_have_timing_visual_and_tip": bool(shot_lists)
        and all(
            isinstance(shot, Mapping)
            and bool(str(shot.get("seconds", "")).strip())
            and bool(str(shot.get("visual", "")).strip())
            and bool(str(shot.get("filming_tip", "")).strip())
            for shots in shot_lists
            if isinstance(shots, list)
            for shot in shots
        ),
        "scripts_present": len(valid_videos) == 3
        and all(bool(str(item.get("script", "")).strip()) for item in valid_videos),
        "music_direction_present": len(valid_videos) == 3
        and all(
            bool(str(item.get("background_music", "")).strip()) for item in valid_videos
        ),
    }
    return _rule(_score(checks.values()), checks)


def _videos(output: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = output.get("videos", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize(left), _normalize(right)).ratio()


def _evaluate_hook_specificity(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    videos = _videos(output)
    request = case.get("request", {})
    product = str(request.get("product_name", "")).strip()
    records: list[dict[str, Any]] = []
    checks: list[bool] = []
    for video in videos:
        hook = str(video.get("hook", "")).strip()
        vague = [pattern.pattern for pattern in VAGUE_HOOK_PATTERNS if pattern.search(hook)]
        has_product = bool(product and _normalize(product) in _normalize(hook))
        has_device = any(token.casefold() in hook.casefold() for token in HOOK_DEVICES)
        concrete_length = 12 <= len(hook) <= 140
        passed = bool(hook) and has_product and has_device and concrete_length and not vague
        checks.append(passed)
        records.append(
            {
                "route_id": video.get("route_id"),
                "hook": hook,
                "has_product": has_product,
                "has_hook_device": has_device,
                "length": len(hook),
                "vague_patterns": vague,
                "passed": passed,
            }
        )
    return _rule(_score(checks) if len(videos) == 3 else 0, {"hooks": records})


def _evaluate_curiosity_gap(output: Mapping[str, Any]) -> dict[str, Any]:
    videos = _videos(output)
    records: list[dict[str, Any]] = []
    checks: list[bool] = []
    for video in videos:
        title = str(video.get("title", "")).strip()
        hook = str(video.get("hook", "")).strip()
        similarity = _similarity(title, hook)
        creates_open_loop = any(
            token.casefold() in f"{title}\n{hook}".casefold() for token in HOOK_DEVICES
        )
        not_repetition = similarity < 0.78
        passed = bool(title and hook and creates_open_loop and not_repetition)
        checks.append(passed)
        records.append(
            {
                "route_id": video.get("route_id"),
                "title_hook_similarity": round(similarity, 3),
                "creates_open_loop": creates_open_loop,
                "not_repetition": not_repetition,
                "passed": passed,
            }
        )
    return _rule(_score(checks) if len(videos) == 3 else 0, {"videos": records})


def _evaluate_route_distinctiveness(output: Mapping[str, Any]) -> dict[str, Any]:
    videos = _videos(output)
    route_ids = [str(video.get("route_id", "")) for video in videos]
    hooks = [str(video.get("hook", "")) for video in videos]
    scripts = [str(video.get("script", "")) for video in videos]
    hook_pairs: list[float] = []
    script_pairs: list[float] = []
    for left in range(len(videos)):
        for right in range(left + 1, len(videos)):
            hook_pairs.append(_similarity(hooks[left], hooks[right]))
            script_pairs.append(_similarity(scripts[left], scripts[right]))
    checks = {
        "ordered_routes": route_ids
        == ["practical-hook", "people-story", "playful-contrast"],
        "hooks_structurally_distinct": bool(hook_pairs) and max(hook_pairs) < 0.72,
        "scripts_structurally_distinct": bool(script_pairs) and max(script_pairs) < 0.82,
        "different_opening_shots": len(
            {
                _normalize(
                    str(
                        (
                            video.get("shots", [{}])[0]
                            if isinstance(video.get("shots"), list)
                            and video.get("shots")
                            else {}
                        ).get("visual", "")
                    )
                )
                for video in videos
            }
        )
        == 3,
    }
    return _rule(
        _score(checks.values()),
        {
            **checks,
            "maximum_hook_similarity": round(max(hook_pairs), 3) if hook_pairs else None,
            "maximum_script_similarity": (
                round(max(script_pairs), 3) if script_pairs else None
            ),
        },
    )


def _evaluate_visual_proof(output: Mapping[str, Any]) -> dict[str, Any]:
    videos = _videos(output)
    records: list[dict[str, Any]] = []
    checks: list[bool] = []
    for video in videos:
        shots = video.get("shots", [])
        if not isinstance(shots, list):
            shots = []
        early_visuals = " ".join(
            str(shot.get("visual", ""))
            for shot in shots[:3]
            if isinstance(shot, Mapping)
        )
        action_hits = sorted(
            {
                token
                for token in VISUAL_ACTION_TOKENS
                if token.casefold() in early_visuals.casefold()
            }
        )
        early_proof = len(action_hits) >= 2
        timeline = [str(shot.get("seconds", "")) for shot in shots if isinstance(shot, Mapping)]
        has_proof_by_eight_seconds = any(
            ("3" in timing and "8" in timing) or ("0" in timing and "8" in timing)
            for timing in timeline[:2]
        )
        passed = early_proof and has_proof_by_eight_seconds
        checks.append(passed)
        records.append(
            {
                "route_id": video.get("route_id"),
                "visual_action_hits": action_hits,
                "proof_by_eight_seconds": has_proof_by_eight_seconds,
                "passed": passed,
            }
        )
    return _rule(_score(checks) if len(videos) == 3 else 0, {"videos": records})


def _evaluate_trend_integration(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    request = case.get("request", {})
    trend = str(request.get("trend", "")).strip()
    product = str(request.get("product_name", "")).strip()
    trend_brief = output.get("trend", {})
    if not isinstance(trend_brief, Mapping):
        trend_brief = {}
    scripts = "\n".join(str(video.get("script", "")) for video in _videos(output))
    if trend:
        checks = {
            "selected_trend_retained": _normalize(trend)
            in _normalize(str(trend_brief.get("trend_used", ""))),
            "trend_reaches_at_least_one_script": _normalize(trend) in _normalize(scripts),
            "script_returns_to_product": _normalize(product) in _normalize(scripts),
            "integration_method_present": bool(
                str(trend_brief.get("integration_method", "")).strip()
            ),
        }
        status = "selected_trend_checked"
    else:
        checks = {
            "no_fake_live_trend": not any(
                token in _normalize(_flatten_text(output))
                for token in ("实时热度第一", "全网爆款", "trending number one")
            ),
            "fallback_topic_signals_present": len(output.get("topic_signals", [])) >= 3,
            "integration_method_present": bool(
                str(trend_brief.get("integration_method", "")).strip()
            ),
        }
        status = "fallback_checked"
    return _rule(_score(checks.values()), {"status": status, **checks})


def _evaluate_interaction_trigger(output: Mapping[str, Any]) -> dict[str, Any]:
    videos = _videos(output)
    calls = [str(video.get("call_to_action", "")).strip() for video in videos]
    interactive_tokens = (
        "？",
        "?",
        "留言",
        "评论",
        "評論",
        "选",
        "選",
        "告诉",
        "告訴",
        "comment",
        "choose",
        "tell us",
    )
    per_video = [
        bool(call)
        and any(token.casefold() in call.casefold() for token in interactive_tokens)
        for call in calls
    ]
    checks = {
        "each_video_has_interaction": len(per_video) == 3 and all(per_video),
        "calls_are_not_identical": len(calls) == 3
        and len({_normalize(call) for call in calls}) == 3,
        "at_least_two_are_questions": sum(
            "？" in call or "?" in call for call in calls
        )
        >= 2,
    }
    return _rule(_score(checks.values()), {**checks, "calls_to_action": calls})


def _evaluate_shot_voice_alignment(
    case: Mapping[str, Any], output: Mapping[str, Any]
) -> dict[str, Any]:
    product = str(case.get("request", {}).get("product_name", "")).strip()
    videos = _videos(output)
    records: list[dict[str, Any]] = []
    checks: list[bool] = []
    for video in videos:
        shots = video.get("shots", [])
        if not isinstance(shots, list):
            shots = []
        first = shots[0] if shots and isinstance(shots[0], Mapping) else {}
        first_pair = f"{first.get('visual', '')} {first.get('voiceover', '')}"
        every_shot_has_pair = bool(shots) and all(
            isinstance(shot, Mapping)
            and bool(str(shot.get("visual", "")).strip())
            and bool(str(shot.get("voiceover", "")).strip())
            for shot in shots
        )
        product_in_opening = bool(
            product and _normalize(product) in _normalize(first_pair)
        )
        no_empty_generic_voice = all(
            len(str(shot.get("voiceover", "")).strip()) >= 6
            for shot in shots
            if isinstance(shot, Mapping)
        )
        passed = every_shot_has_pair and product_in_opening and no_empty_generic_voice
        checks.append(passed)
        records.append(
            {
                "route_id": video.get("route_id"),
                "every_shot_has_visual_voice_pair": every_shot_has_pair,
                "product_in_opening": product_in_opening,
                "voiceovers_are_substantive": no_empty_generic_voice,
                "passed": passed,
            }
        )
    return _rule(_score(checks) if len(videos) == 3 else 0, {"videos": records})


def _evaluate_farmer_filmability(output: Mapping[str, Any]) -> dict[str, Any]:
    videos = _videos(output)
    text = _normalize("\n".join(str(video) for video in videos))
    expensive_tokens = (
        "无人机",
        "無人機",
        "专业摄影棚",
        "專業攝影棚",
        "演员团队",
        "演員團隊",
        "crane shot",
        "film crew",
        "studio set",
    )
    shot_counts = [
        len(video.get("shots", [])) if isinstance(video.get("shots"), list) else 0
        for video in videos
    ]
    tips = "\n".join(
        str(shot.get("filming_tip", ""))
        for video in videos
        for shot in (
            video.get("shots", []) if isinstance(video.get("shots"), list) else []
        )
        if isinstance(shot, Mapping)
    )
    checks = {
        "three_to_six_shots": len(shot_counts) == 3
        and all(3 <= count <= 6 for count in shot_counts),
        "phone_or_simple_camera_guidance": any(
            token in tips.casefold()
            for token in ("手机", "手機", "竖拍", "豎拍", "近景", "phone", "vertical")
        ),
        "no_expensive_production_dependency": not any(
            token.casefold() in text for token in expensive_tokens
        ),
        "clear_timing_on_every_shot": all(
            bool(str(shot.get("seconds", "")).strip())
            for video in videos
            for shot in (
                video.get("shots", []) if isinstance(video.get("shots"), list) else []
            )
            if isinstance(shot, Mapping)
        ),
    }
    return _rule(_score(checks.values()), checks)


def _evaluate_ad_cliche_penalty(output: Mapping[str, Any]) -> dict[str, Any]:
    text = _flatten_text(output)
    matches = sorted(
        {
            match.group(0)
            for pattern in CLICHE_PATTERNS
            for match in pattern.finditer(text)
        }
    )
    generic_openings = sum(
        1
        for video in _videos(output)
        if any(pattern.search(str(video.get("hook", ""))) for pattern in VAGUE_HOOK_PATTERNS)
    )
    score = max(0, 100 - len(matches) * 25 - generic_openings * 20)
    return _rule(
        score,
        {
            "cliche_matches": matches,
            "generic_opening_count": generic_openings,
            "penalty": 100 - score,
        },
    )


def evaluate_output(
    case: Mapping[str, Any],
    output: Mapping[str, Any],
    *,
    latency_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    estimated_cost: float | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    """Evaluate one already-generated output without any database access."""
    schema_rule, normalized_output = _evaluate_schema(output)
    rules = {
        "schema": schema_rule,
        "factual_grounding": _evaluate_facts(case, normalized_output),
        "prohibited_claims": _evaluate_prohibited_claims(case, normalized_output),
        "citations": _evaluate_citations(case, normalized_output),
        "language": _evaluate_language(case, normalized_output),
        "marketing_expression": _evaluate_marketing_expression(normalized_output),
        "platform_fit": _evaluate_platform_fit(case, normalized_output),
        "filmability": _evaluate_filmability(normalized_output),
        "hook_specificity": _evaluate_hook_specificity(case, normalized_output),
        "curiosity_gap": _evaluate_curiosity_gap(normalized_output),
        "route_distinctiveness": _evaluate_route_distinctiveness(normalized_output),
        "visual_proof": _evaluate_visual_proof(normalized_output),
        "trend_integration": _evaluate_trend_integration(case, normalized_output),
        "interaction_trigger": _evaluate_interaction_trigger(normalized_output),
        "shot_voice_alignment": _evaluate_shot_voice_alignment(case, normalized_output),
        "farmer_filmability": _evaluate_farmer_filmability(normalized_output),
        "ad_cliche_penalty": _evaluate_ad_cliche_penalty(normalized_output),
    }
    overall_score = round(
        sum(int(rules[name]["score"]) for name in DIMENSIONS) / len(DIMENSIONS), 2
    )
    return {
        "case_key": case["case_key"],
        "locale": case["locale"],
        "tags": case.get("tags", []),
        "passed": all(bool(rules[name]["passed"]) for name in DIMENSIONS),
        "overall_score": overall_score,
        "rules": rules,
        "measurements": {
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimated_cost,
            "currency": currency,
            "token_and_cost_status": (
                "known"
                if input_tokens is not None
                and output_tokens is not None
                and estimated_cost is not None
                else "unknown"
            ),
        },
    }


def load_dataset(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(dataset.get("cases"), list) or not dataset["cases"]:
        raise ValueError("evaluation dataset must contain at least one case")
    return dataset


def generate_and_evaluate_case(
    case: Mapping[str, Any],
    provider: DeterministicMarketingProvider | None = None,
) -> dict[str, Any]:
    """Generate one offline plan and evaluate it without persisting business data."""
    offline_provider = provider or DeterministicMarketingProvider()
    request = MarketingPlanRequest.model_validate(case["request"])
    response = offline_provider.generate(request)
    payload = response.model_dump(mode="json")
    result = evaluate_output(
        case,
        payload,
        latency_ms=response.latency_ms,
        input_tokens=None,
        output_tokens=None,
        estimated_cost=None,
        currency=None,
    )
    result["generation"] = {
        "provider": response.provider,
        "model": response.model,
        "degraded": response.degraded,
    }
    return result


def run_evaluation(dataset: Mapping[str, Any]) -> dict[str, Any]:
    cases = [generate_and_evaluate_case(case) for case in dataset["cases"]]
    minimum_overall = int(dataset.get("minimum_overall_score", 80))
    minimum_dimension = int(dataset.get("minimum_dimension_score", 70))
    for case_result in cases:
        case_result["passed"] = case_result["overall_score"] >= minimum_overall and all(
            case_result["rules"][dimension]["score"] >= minimum_dimension
            for dimension in DIMENSIONS
        )
    aggregate_dimensions = {
        dimension: round(
            sum(case["rules"][dimension]["score"] for case in cases) / len(cases), 2
        )
        for dimension in DIMENSIONS
    }
    return {
        "report_version": "marketing-quality-report-v2",
        "dataset_version": dataset["dataset_version"],
        "evaluator_version": EVALUATOR_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "disclaimer": DISCLAIMER,
        "thresholds": {
            "minimum_overall_score": minimum_overall,
            "minimum_dimension_score": minimum_dimension,
        },
        "passed": all(case["passed"] for case in cases),
        "aggregate": {
            "case_count": len(cases),
            "passed_case_count": sum(1 for case in cases if case["passed"]),
            "overall_score": round(
                sum(case["overall_score"] for case in cases) / len(cases), 2
            ),
            "dimension_scores": aggregate_dimensions,
        },
        "cases": cases,
    }


def baseline_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "baseline_version": "marketing-baseline-v2",
        "dataset_version": report["dataset_version"],
        "evaluator_version": report["evaluator_version"],
        "disclaimer": DISCLAIMER,
        "aggregate": report["aggregate"],
        "cases": [
            {
                "case_key": case["case_key"],
                "overall_score": case["overall_score"],
                "dimension_scores": {
                    dimension: case["rules"][dimension]["score"]
                    for dimension in DIMENSIONS
                },
            }
            for case in report["cases"]
        ],
    }


def compare_with_baseline(
    report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    tolerance: float = 0,
) -> dict[str, Any]:
    if baseline.get("dataset_version") != report.get("dataset_version"):
        raise ValueError("baseline dataset_version does not match the current dataset")
    if baseline.get("evaluator_version") != report.get("evaluator_version"):
        raise ValueError(
            "baseline evaluator_version does not match the current evaluator"
        )
    current_cases = {case["case_key"]: case for case in report["cases"]}
    regressions: list[dict[str, Any]] = []
    for expected in baseline.get("cases", []):
        case_key = expected["case_key"]
        current = current_cases.get(case_key)
        if current is None:
            regressions.append(
                {"case_key": case_key, "metric": "case", "reason": "missing_case"}
            )
            continue
        expected_overall = float(expected["overall_score"])
        current_overall = float(current["overall_score"])
        if current_overall + tolerance < expected_overall:
            regressions.append(
                {
                    "case_key": case_key,
                    "metric": "overall_score",
                    "baseline": expected_overall,
                    "current": current_overall,
                }
            )
        for dimension in DIMENSIONS:
            expected_score = float(expected["dimension_scores"][dimension])
            current_score = float(current["rules"][dimension]["score"])
            if current_score + tolerance < expected_score:
                regressions.append(
                    {
                        "case_key": case_key,
                        "metric": dimension,
                        "baseline": expected_score,
                        "current": current_score,
                    }
                )
    return {
        "baseline_version": baseline.get("baseline_version"),
        "tolerance": tolerance,
        "passed": not regressions,
        "regressions": regressions,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the offline, versioned Heyu AI marketing-content baseline."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-baseline", action="store_true")
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--regression-tolerance", type=float, default=0)
    args = parser.parse_args(argv)

    dataset = load_dataset(args.dataset)
    report = run_evaluation(dataset)

    if args.write_baseline is not None:
        _write_json(args.write_baseline, baseline_from_report(report))

    if not args.no_baseline and args.write_baseline is None:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        report["baseline_comparison"] = compare_with_baseline(
            report,
            baseline,
            tolerance=args.regression_tolerance,
        )
    else:
        report["baseline_comparison"] = {
            "passed": True,
            "status": "not_compared",
            "regressions": [],
        }

    _write_json(args.output, report)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "overall_score": report["aggregate"]["overall_score"],
                "baseline_passed": report["baseline_comparison"]["passed"],
                "output": str(args.output),
                "disclaimer": DISCLAIMER,
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] and report["baseline_comparison"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
