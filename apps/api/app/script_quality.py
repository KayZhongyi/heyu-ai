"""Deterministic quality checks for short-video scripts.

The evaluator intentionally uses transparent rules instead of an LLM so the
same input always produces the same scores and issue codes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

SCORE_NAMES = (
    "hook_product",
    "hook_structure",
    "opening_0_3",
    "visual_proof_3_8",
    "voice_visual_alignment",
    "cta_interaction",
    "bgm_direction",
    "trend_integration",
    "specificity",
    "filmability",
)

_QUESTION_MARKERS = ("?", "？", "吗", "么", "why", "how", "what", "which", "can you")
_PROBLEM_MARKERS = (
    "难",
    "问题",
    "困扰",
    "踩坑",
    "别再",
    "为什么",
    "怎么",
    "如何",
    "problem",
    "struggle",
    "mistake",
    "avoid",
    "why",
    "how",
)
_CHOICE_MARKERS = (
    "选哪个",
    "怎么选",
    "你会选",
    "还是",
    "二选一",
    "左边",
    "右边",
    "which",
    "choose",
    "pick",
    "or",
    "left",
    "right",
)
_CONTRAST_MARKERS = (
    "不是",
    "而是",
    "却",
    "反差",
    "对比",
    "vs",
    "versus",
    "but",
    "instead",
    "looks",
    "actually",
)
_RESULT_MARKERS = (
    "结果",
    "秒变",
    "前后",
    "最后",
    "看完",
    "之后",
    "before",
    "after",
    "result",
    "in seconds",
    "finally",
)
_ACTION_MARKERS = (
    "拿",
    "切",
    "掰",
    "撕",
    "挤",
    "倒",
    "拉",
    "按",
    "擦",
    "洗",
    "咬",
    "打开",
    "翻转",
    "对比",
    "测量",
    "展示",
    "放入",
    "take",
    "cut",
    "slice",
    "open",
    "pour",
    "press",
    "pull",
    "wipe",
    "wash",
    "bite",
    "compare",
    "measure",
    "show",
    "place",
    "apply",
)
_PROOF_MARKERS = (
    "近景",
    "特写",
    "细节",
    "纹理",
    "果肉",
    "汁水",
    "刻度",
    "数据",
    "前后",
    "对比",
    "实测",
    "横切面",
    "close-up",
    "close up",
    "detail",
    "texture",
    "inside",
    "measurement",
    "reading",
    "before",
    "after",
    "compare",
    "proof",
)
_INTERACTION_MARKERS = (
    "评论",
    "留言",
    "告诉我",
    "投票",
    "你会选",
    "你觉得",
    "收藏",
    "关注",
    "转发",
    "comment",
    "reply",
    "tell me",
    "vote",
    "which would you",
    "save",
    "follow",
    "share",
)
_BGM_ENTRY_MARKERS = (
    "0秒",
    "0s",
    "开场",
    "一开始",
    "第一帧",
    "进入",
    "起",
    "from 0",
    "at 0",
    "opening",
    "starts",
    "enters",
    "first frame",
)
_BGM_DUCK_MARKERS = (
    "压低",
    "降低",
    "淡出",
    "口播时",
    "人声下",
    "duck",
    "lower",
    "under voice",
    "under dialogue",
    "fade",
)
_GENERIC_AD_PHRASES = (
    "品质保证",
    "高品质",
    "匠心打造",
    "严选好物",
    "不容错过",
    "值得拥有",
    "极致体验",
    "好吃到停不下来",
    "领先行业",
    "闭眼入",
    "quality guaranteed",
    "high quality",
    "premium quality",
    "best ever",
    "must-have",
    "must have",
    "game changer",
    "unmatched",
    "perfect choice",
    "worth buying",
)
_HIGH_RESOURCE_GROUPS = {
    "aerial equipment": ("无人机", "航拍", "drone", "aerial shot"),
    "studio or set": ("影棚", "摄影棚", "搭景", "租棚", "studio set", "soundstage"),
    "specialized camera rig": (
        "摇臂",
        "轨道车",
        "斯坦尼康",
        "电影机",
        "高速摄影机",
        "crane",
        "camera dolly",
        "steadicam",
        "cinema camera",
        "high-speed camera",
    ),
    "large crew or cast": (
        "演员",
        "群演",
        "摄制组",
        "灯光师",
        "专业灯光",
        "三机位",
        "多机位",
        "actors",
        "extras",
        "film crew",
        "lighting crew",
        "professional lighting",
        "three-camera",
        "multi-camera",
    ),
    "post-production effects": (
        "三维特效",
        "粒子特效",
        "绿幕",
        "cg",
        "cgi",
        "vfx",
        "green screen",
        "particle effects",
    ),
}
_STOPWORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "into",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
    "一个",
    "一下",
    "这个",
    "然后",
    "我们",
    "就是",
    "可以",
}
_PRODUCT_QUALIFIERS = (
    "有机",
    "新鲜",
    "本地",
    "当季",
    "特级",
    "精选",
    "天然",
    "手工",
    "organic",
    "fresh",
    "local",
    "seasonal",
    "premium",
    "natural",
    "handmade",
)
_WORD_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
_BPM_RE = re.compile(
    r"(?:"
    r"(?<!\d)\d{2,3}\s*(?:-|–|—|~|至|到)?\s*\d{0,3}\s*bpm\b"
    r"|"
    r"\bbpm\s*\d{2,3}(?:\s*(?:-|–|—|~|至|到)\s*\d{2,3})?"
    r")",
    re.I,
)


@dataclass(frozen=True, slots=True)
class NormalizedShot:
    timing: str
    visual: str
    voiceover: str
    filming_tip: str


class ScriptQualityEvaluator:
    """Reusable deterministic evaluator with no external dependencies."""

    def evaluate(
        self,
        product_name: str,
        trend: str,
        hook: str,
        script: str,
        shots: Sequence[Mapping[str, Any] | Any],
        cta: str,
        bgm: str,
    ) -> dict[str, Any]:
        normalized_shots = tuple(_normalize_shot(shot) for shot in shots)
        issues: list[dict[str, str]] = []
        product_terms = _product_terms(product_name)

        scores = {
            "hook_product": self._score_hook_product(hook, product_name, product_terms, issues),
            "hook_structure": self._score_hook_structure(hook, issues),
            "opening_0_3": self._score_opening(normalized_shots, product_terms, issues),
            "visual_proof_3_8": self._score_visual_proof(normalized_shots, product_terms, issues),
            "voice_visual_alignment": self._score_alignment(
                normalized_shots, product_terms, issues
            ),
            "cta_interaction": self._score_cta(cta, issues),
            "bgm_direction": self._score_bgm(bgm, issues),
            "trend_integration": self._score_trend(trend, hook, script, normalized_shots, issues),
            "specificity": self._score_specificity(hook, script, cta, issues),
            "filmability": self._score_filmability(normalized_shots, issues),
        }
        total_score = round(sum(scores.values()) / len(scores))
        return {
            "scores": scores,
            "total_score": total_score,
            "issues": issues,
        }

    @staticmethod
    def _score_hook_product(
        hook: str,
        product_name: str,
        product_terms: tuple[str, ...],
        issues: list[dict[str, str]],
    ) -> int:
        text = _fold(hook)
        exact = bool(product_name.strip()) and _fold(product_name) in text
        matched = [term for term in product_terms if term in text]
        if exact:
            return 100
        if matched:
            return 90
        _issue(
            issues,
            "hook_missing_product",
            "hook_product",
            "high",
            f"Hook does not name the product or a concrete product object: {product_name!r}.",
        )
        return 15

    @staticmethod
    def _score_hook_structure(hook: str, issues: list[dict[str, str]]) -> int:
        text = _fold(hook)
        detected = []
        if _contains_any(text, _PROBLEM_MARKERS):
            detected.append("problem")
        if _contains_any(text, _CHOICE_MARKERS):
            detected.append("choice")
        if _contains_any(text, _CONTRAST_MARKERS):
            detected.append("contrast")
        if _contains_any(text, _RESULT_MARKERS):
            detected.append("result")
        if detected:
            return 100
        if _contains_any(text, _QUESTION_MARKERS):
            _issue(
                issues,
                "hook_weak_question",
                "hook_structure",
                "medium",
                "Hook is a question, but it lacks a concrete problem, choice, contrast, or result.",
            )
            return 55
        _issue(
            issues,
            "hook_no_tension",
            "hook_structure",
            "high",
            "Hook needs a problem, choice, contrast, or result-based tension.",
        )
        return 15

    @staticmethod
    def _score_opening(
        shots: tuple[NormalizedShot, ...],
        product_terms: tuple[str, ...],
        issues: list[dict[str, str]],
    ) -> int:
        if not shots:
            _issue(
                issues,
                "opening_missing",
                "opening_0_3",
                "high",
                "No opening shot is provided for the first three seconds.",
            )
            return 0
        shot = shots[0]
        visual = _fold(shot.visual)
        action_text = _fold(f"{shot.visual} {shot.filming_tip}")
        product_visible = any(term in visual for term in product_terms)
        has_action = _contains_any(action_text, _ACTION_MARKERS)
        timing_ok = not shot.timing or _covers_window(shot.timing, 0, 3)
        score = (
            (45 if product_visible else 0) + (40 if has_action else 0) + (15 if timing_ok else 0)
        )
        if not product_visible:
            _issue(
                issues,
                "opening_product_not_visible",
                "opening_0_3",
                "high",
                "The first shot does not visibly name or show the product.",
            )
        if not has_action:
            _issue(
                issues,
                "opening_no_action",
                "opening_0_3",
                "high",
                "The first shot has no concrete on-screen action within 0-3 seconds.",
            )
        if not timing_ok:
            _issue(
                issues,
                "opening_wrong_timing",
                "opening_0_3",
                "medium",
                f"First shot timing {shot.timing!r} does not cover 0-3 seconds.",
            )
        return score

    @staticmethod
    def _score_visual_proof(
        shots: tuple[NormalizedShot, ...],
        product_terms: tuple[str, ...],
        issues: list[dict[str, str]],
    ) -> int:
        if len(shots) < 2:
            _issue(
                issues,
                "proof_shot_missing",
                "visual_proof_3_8",
                "high",
                "No second shot supplies visual proof for 3-8 seconds.",
            )
            return 0
        shot = shots[1]
        visual = _fold(shot.visual)
        timing_ok = not shot.timing or _covers_window(shot.timing, 3, 8)
        has_proof = _contains_any(visual, _PROOF_MARKERS)
        has_action = _contains_any(visual, _ACTION_MARKERS)
        has_product_or_detail = any(term in visual for term in product_terms) or has_proof
        score = (
            (20 if timing_ok else 0)
            + (35 if has_proof else 0)
            + (25 if has_action else 0)
            + (20 if has_product_or_detail else 0)
        )
        if not has_proof or not has_action:
            _issue(
                issues,
                "proof_not_visual",
                "visual_proof_3_8",
                "high",
                "The 3-8 second shot should prove a claim with a close-up, comparison, "
                "measurement, or visible action.",
            )
        if not timing_ok:
            _issue(
                issues,
                "proof_wrong_timing",
                "visual_proof_3_8",
                "medium",
                f"Second shot timing {shot.timing!r} does not cover 3-8 seconds.",
            )
        return score

    @staticmethod
    def _score_alignment(
        shots: tuple[NormalizedShot, ...],
        product_terms: tuple[str, ...],
        issues: list[dict[str, str]],
    ) -> int:
        if not shots:
            _issue(
                issues,
                "alignment_unscorable",
                "voice_visual_alignment",
                "high",
                "Voiceover-to-visual alignment cannot be checked without shots.",
            )
            return 0
        shot_scores = []
        mismatches = []
        for index, shot in enumerate(shots, start=1):
            visual_concepts = _concepts(shot.visual, product_terms)
            voice_concepts = _concepts(shot.voiceover, product_terms)
            shared = visual_concepts & voice_concepts
            if len(shared) >= 2:
                shot_scores.append(100)
            elif shared:
                shot_scores.append(75)
            elif not shot.voiceover.strip():
                shot_scores.append(20)
                mismatches.append(index)
            else:
                shot_scores.append(35)
                mismatches.append(index)
        score = round(sum(shot_scores) / len(shot_scores))
        if mismatches:
            _issue(
                issues,
                "voice_visual_mismatch",
                "voice_visual_alignment",
                "high" if score < 60 else "medium",
                "Voiceover and visual lack shared product, action, or evidence concepts in "
                f"shot(s): {', '.join(map(str, mismatches))}.",
            )
        return score

    @staticmethod
    def _score_cta(cta: str, issues: list[dict[str, str]]) -> int:
        text = _fold(cta)
        interaction = _contains_any(text, _INTERACTION_MARKERS)
        choice_or_question = _contains_any(text, _CHOICE_MARKERS + _QUESTION_MARKERS)
        clear_action = bool(text.strip()) and (interaction or _contains_any(text, ("点击", "buy")))
        score = (
            (55 if interaction else 0)
            + (25 if choice_or_question else 0)
            + (20 if clear_action else 0)
        )
        if score < 80:
            _issue(
                issues,
                "cta_not_interactive",
                "cta_interaction",
                "high",
                "CTA should ask viewers to comment, choose, vote, save, share, or answer a "
                "specific question.",
            )
        return score

    @staticmethod
    def _score_bgm(bgm: str, issues: list[dict[str, str]]) -> int:
        text = _fold(bgm)
        has_bpm = bool(_BPM_RE.search(bgm))
        has_entry = _contains_any(text, _BGM_ENTRY_MARKERS)
        has_duck = _contains_any(text, _BGM_DUCK_MARKERS)
        score = (40 if has_bpm else 0) + (30 if has_entry else 0) + (30 if has_duck else 0)
        missing = []
        if not has_bpm:
            missing.append("BPM")
        if not has_entry:
            missing.append("entry point")
        if not has_duck:
            missing.append("voiceover duck/lower point")
        if missing:
            _issue(
                issues,
                "bgm_incomplete_direction",
                "bgm_direction",
                "medium",
                f"BGM direction is missing: {', '.join(missing)}.",
            )
        return score

    @staticmethod
    def _score_trend(
        trend: str,
        hook: str,
        script: str,
        shots: tuple[NormalizedShot, ...],
        issues: list[dict[str, str]],
    ) -> int:
        if not trend.strip():
            return 100
        content = _fold(
            " ".join(
                [
                    hook,
                    script,
                    *(f"{shot.visual} {shot.voiceover}" for shot in shots),
                ]
            )
        )
        folded_trend = _fold(trend)
        if folded_trend in content:
            return 100
        terms = _meaningful_terms(trend)
        matched = [term for term in terms if term in content]
        if terms and len(matched) / len(terms) >= 0.6:
            return 75
        _issue(
            issues,
            "trend_not_integrated",
            "trend_integration",
            "high",
            f"Trend {trend!r} is supplied but not meaningfully used in the hook, script, or shots.",
        )
        return 0

    @staticmethod
    def _score_specificity(
        hook: str,
        script: str,
        cta: str,
        issues: list[dict[str, str]],
    ) -> int:
        content = _fold(f"{hook} {script} {cta}")
        matched = sorted({phrase for phrase in _GENERIC_AD_PHRASES if phrase in content})
        score = max(0, 100 - len(matched) * 25)
        if matched:
            _issue(
                issues,
                "generic_ad_copy",
                "specificity",
                "medium" if score >= 50 else "high",
                f"Replace vague advertising phrase(s) with observable evidence: {matched!r}.",
            )
        return score

    @staticmethod
    def _score_filmability(
        shots: tuple[NormalizedShot, ...],
        issues: list[dict[str, str]],
    ) -> int:
        if not shots:
            _issue(
                issues,
                "shots_missing",
                "filmability",
                "high",
                "No shot list is provided.",
            )
            return 0
        content = _fold(" ".join(f"{shot.visual} {shot.filming_tip}" for shot in shots))
        resources = [
            label
            for label, markers in _HIGH_RESOURCE_GROUPS.items()
            if _contains_any(content, markers)
        ]
        score = 100 - len(resources) * 25
        if len(shots) > 6:
            score -= min(30, (len(shots) - 6) * 5)
        score = max(0, score)
        if resources:
            _issue(
                issues,
                "high_resource_shoot",
                "filmability",
                "high",
                f"Shot plan depends on high-threshold resources: {', '.join(resources)}.",
            )
        if len(shots) > 6:
            _issue(
                issues,
                "too_many_shots",
                "filmability",
                "medium",
                f"{len(shots)} shots may be unnecessarily complex for a short video; aim for 3-6.",
            )
        return score


def evaluate_script_quality(
    product_name: str,
    trend: str,
    hook: str,
    script: str,
    shots: Sequence[Mapping[str, Any] | Any],
    cta: str,
    bgm: str,
) -> dict[str, Any]:
    """Evaluate one short-video script and return scores, total score, and issues."""

    return ScriptQualityEvaluator().evaluate(
        product_name=product_name,
        trend=trend,
        hook=hook,
        script=script,
        shots=shots,
        cta=cta,
        bgm=bgm,
    )


evaluate_short_video_script_quality = evaluate_script_quality


def _normalize_shot(value: Mapping[str, Any] | Any) -> NormalizedShot:
    if isinstance(value, Mapping):
        data = value
    elif hasattr(value, "model_dump"):
        data = value.model_dump()
    elif is_dataclass(value) and not isinstance(value, type):
        data = asdict(value)
    else:
        data = {
            "seconds": getattr(value, "seconds", ""),
            "timing": getattr(value, "timing", ""),
            "visual": getattr(value, "visual", ""),
            "voiceover": getattr(value, "voiceover", ""),
            "filming_tip": getattr(value, "filming_tip", ""),
        }
    return NormalizedShot(
        timing=_string(data.get("seconds") or data.get("timing") or data.get("time")),
        visual=_string(data.get("visual")),
        voiceover=_string(data.get("voiceover") or data.get("voiceover_or_text")),
        filming_tip=_string(data.get("filming_tip")),
    )


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _fold(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    return any(_contains_marker(text, marker) for marker in markers)


def _contains_marker(text: str, marker: str) -> bool:
    folded_marker = _fold(marker)
    if re.fullmatch(r"[a-z0-9]+", folded_marker):
        return bool(re.search(rf"\b{re.escape(folded_marker)}\b", text))
    return folded_marker in text


def _product_terms(product_name: str) -> tuple[str, ...]:
    folded = _fold(product_name)
    terms = {folded} if folded else set()
    stripped = folded
    for qualifier in _PRODUCT_QUALIFIERS:
        qualifier = _fold(qualifier)
        stripped = re.sub(rf"\b{re.escape(qualifier)}\b", " ", stripped)
        stripped = stripped.replace(qualifier, "")
    terms.update(_meaningful_terms(stripped))
    for token in _WORD_RE.findall(stripped):
        if re.fullmatch(r"[\u3400-\u9fff]+", token) and len(token) >= 3:
            terms.add(token[-2:])
            terms.add(token[-3:])
    return tuple(
        sorted(
            (term for term in terms if len(term) >= 2),
            key=lambda item: (-len(item), item),
        )
    )


def _meaningful_terms(value: str) -> tuple[str, ...]:
    terms: set[str] = set()
    for token in _WORD_RE.findall(_fold(value)):
        if token in _STOPWORDS:
            continue
        if re.fullmatch(r"[a-z0-9]+", token):
            if len(token) >= 3:
                terms.add(token)
        elif len(token) >= 2:
            terms.add(token)
            if len(token) >= 4:
                terms.update(token[index : index + 2] for index in range(len(token) - 1))
    return tuple(sorted(terms))


def _concepts(value: str, product_terms: tuple[str, ...]) -> set[str]:
    text = _fold(value)
    concepts = {f"product:{term}" for term in product_terms if term in text}
    for label, markers in (
        ("action", _ACTION_MARKERS),
        ("proof", _PROOF_MARKERS),
        ("choice", _CHOICE_MARKERS),
        ("interaction", _INTERACTION_MARKERS),
    ):
        concepts.update(f"{label}:{marker}" for marker in markers if _contains_marker(text, marker))
    concepts.update(f"term:{term}" for term in _meaningful_terms(value))
    return concepts


def _covers_window(timing: str, expected_start: int, expected_end: int) -> bool:
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", timing)]
    if len(numbers) < 2:
        return False
    start, end = numbers[0], numbers[1]
    return start <= expected_start and end >= expected_end


def _issue(
    issues: list[dict[str, str]],
    code: str,
    dimension: str,
    severity: str,
    message: str,
) -> None:
    issues.append(
        {
            "code": code,
            "dimension": dimension,
            "severity": severity,
            "message": message,
        }
    )
