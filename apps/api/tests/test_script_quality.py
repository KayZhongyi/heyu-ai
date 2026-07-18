from __future__ import annotations

from dataclasses import dataclass

from app.script_quality import SCORE_NAMES, evaluate_script_quality


@dataclass
class ShotObject:
    seconds: str
    visual: str
    voiceover: str
    filming_tip: str


def test_excellent_chinese_script_scores_high_and_accepts_objects_and_dicts():
    result = evaluate_script_quality(
        product_name="有机草莓",
        trend="多巴胺配色",
        hook="多巴胺配色的有机草莓，左边和右边你会选哪一盒？",
        script=("多巴胺配色不只看颜色。切开有机草莓，近景看果肉和汁水，再对比两盒草莓的成熟度。"),
        shots=[
            ShotObject(
                seconds="0-3s",
                visual="手拿两盒有机草莓放到镜头前，左右快速对比",
                voiceover="有机草莓左边和右边，你会选哪一盒？",
                filming_tip="手机竖拍，第一帧拿起产品",
            ),
            {
                "seconds": "3-8s",
                "visual": "切开有机草莓，近景展示果肉、籽和汁水",
                "voiceover": "切开草莓，近景看果肉和汁水是否饱满",
                "filming_tip": "自然光下拍横切面，不用额外设备",
            },
            {
                "seconds": "8-18s",
                "visual": "对比两盒草莓的颜色和果肉细节",
                "voiceover": "对比颜色和果肉细节，再判断成熟度",
                "filming_tip": "口播说到颜色和果肉时切对应特写",
            },
        ],
        cta="左边还是右边？评论区告诉我你的选择，也可以先收藏。",
        bgm="96-104 BPM 轻快节奏，0秒第一帧进入，口播时压低到人声下。",
    )

    assert set(result["scores"]) == set(SCORE_NAMES)
    assert all(0 <= score <= 100 for score in result["scores"].values())
    assert result["total_score"] >= 90
    assert result["issues"] == []


def test_low_quality_script_reports_concrete_problems():
    result = evaluate_script_quality(
        product_name="便携榨汁杯",
        trend="办公室健康挑战",
        hook="今天给大家推荐一个好东西",
        script="高品质，匠心打造，不容错过，值得拥有。",
        shots=[
            {
                "seconds": "0-5s",
                "visual": "模特站在影棚里微笑",
                "voiceover": "这是一个高品质好物",
                "filming_tip": "使用演员、电影机、三机位和专业摄制组",
            }
        ],
        cta="立即购买。",
        bgm="轻快音乐。",
    )

    codes = {issue["code"] for issue in result["issues"]}
    assert result["total_score"] < 45
    assert {
        "hook_missing_product",
        "hook_no_tension",
        "opening_product_not_visible",
        "opening_no_action",
        "proof_shot_missing",
        "cta_not_interactive",
        "bgm_incomplete_direction",
        "trend_not_integrated",
        "generic_ad_copy",
        "high_resource_shoot",
    } <= codes
    assert result["scores"]["specificity"] == 0
    assert result["scores"]["filmability"] <= 50


def test_supplied_trend_must_be_integrated_into_the_content():
    common = {
        "product_name": "露营咖啡杯",
        "hook": "露营咖啡杯为什么倒过来也不漏？",
        "shots": [
            {
                "seconds": "0-3",
                "visual": "拿起露营咖啡杯并快速倒置",
                "voiceover": "露营咖啡杯倒过来也不漏吗？",
                "filming_tip": "手机近景拍摄倒置动作",
            },
            {
                "seconds": "3-8",
                "visual": "近景按压杯盖并展示密封圈细节",
                "voiceover": "按压杯盖，近景看密封圈细节",
                "filming_tip": "自然光拍密封圈",
            },
        ],
        "cta": "你露营时更怕漏水还是难清洗？评论告诉我。",
        "bgm": "90 BPM，开场进入，口播时压低。",
    }
    missing = evaluate_script_quality(
        trend="citywalk",
        script="倒置杯子，再按压杯盖展示密封圈。",
        **common,
    )
    integrated = evaluate_script_quality(
        trend="citywalk",
        script="citywalk 途中把杯子倒置，再按压杯盖展示密封圈。",
        **common,
    )

    assert missing["scores"]["trend_integration"] == 0
    assert any(issue["code"] == "trend_not_integrated" for issue in missing["issues"])
    assert integrated["scores"]["trend_integration"] == 100
    assert integrated["total_score"] > missing["total_score"]


def test_excellent_english_script_is_supported():
    result = evaluate_script_quality(
        product_name="portable blender",
        trend="desk reset",
        hook="Desk reset test: which portable blender finishes frozen berries first?",
        script=(
            "For this desk reset, place frozen berries in both cups. Press start, compare "
            "the texture after ten seconds, and show the result in a close-up."
        ),
        shots=[
            {
                "timing": "0-3s",
                "visual": "Place two portable blenders on the desk and press both start buttons",
                "voiceover": "Which portable blender finishes frozen berries first?",
                "filming_tip": "Use a phone; show the products and press start in the first frame",
            },
            {
                "timing": "3-8s",
                "visual": "Close-up: compare the berry texture inside each portable blender",
                "voiceover": "Compare the berry texture in each portable blender after ten seconds",
                "filming_tip": "Hold the phone close to the cups in window light",
            },
            {
                "timing": "8-15s",
                "visual": "Pour both berry drinks side by side to show the final texture",
                "voiceover": "Pour both drinks and show the final texture side by side",
                "filming_tip": "Keep the spoken detail and matching action in one frame",
            },
        ],
        cta="Which result would you choose? Comment A or B, then save the test.",
        bgm="100 BPM upbeat loop, enters at 0s, lower under voiceover.",
    )

    assert result["total_score"] >= 90
    assert result["scores"]["hook_structure"] == 100
    assert result["scores"]["trend_integration"] == 100
    assert result["scores"]["bgm_direction"] == 100
