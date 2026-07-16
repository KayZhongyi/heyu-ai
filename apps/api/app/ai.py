import json
import time
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import Settings, get_settings
from app.models import (
    Brand,
    CampaignBriefRevision,
    CampaignFarmerEvidenceSnapshot,
    CampaignSupplySnapshot,
    ContentProject,
    ContentType,
    Product,
)

PROMPT_NAME = "agricultural-content-script"
PROMPT_VERSION = "1.2.0"


@dataclass(frozen=True)
class ContextSource:
    id: str
    title: str
    citation_label: str
    content: str
    content_sha256: str
    chunk_id: str | None = None
    locator: dict | None = None
    retrieval_score: float | None = None


@dataclass
class GenerationResult:
    content: dict
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None


class AIProvider(Protocol):
    name: str
    model: str

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
        supply: CampaignSupplySnapshot | None = None,
        farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
        brief: CampaignBriefRevision | None = None,
    ) -> GenerationResult: ...


class DeterministicProvider:
    """Offline provider for tests and zero-cost demos.

    It is deliberately transparent: this provider composes verified facts rather
    than pretending to be a trained model.
    """

    name = "mock"
    model = "deterministic-v1"

    @staticmethod
    def _common_context(
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
        locale: str = "zh-CN",
    ) -> tuple[str, str, list[dict], list[str]]:
        facts = [source.content.strip() for source in sources if source.content.strip()]
        if locale == "en":
            fact_text = "; ".join(facts[:3]) or "Add and approve product evidence first"
            selling_points = ", ".join(product.selling_points) or "its product characteristics"
            risk_notes = [f"Do not use: {claim}" for claim in product.prohibited_claims]
        elif locale == "zh-HK":
            fact_text = "；".join(facts[:3]) or "請先補充並審批產品資料"
            selling_points = "、".join(product.selling_points) or "產品資料及特色"
            risk_notes = [f"不得使用：{claim}" for claim in product.prohibited_claims]
        else:
            fact_text = "；".join(facts[:3]) or "请先补充并审核产品资料"
            selling_points = "、".join(product.selling_points) or "产品资料与特色"
            risk_notes = [f"禁止使用：{claim}" for claim in product.prohibited_claims]
        citations = [
            {"source_id": source.id, "label": source.citation_label or source.title}
            for source in sources
        ]
        return fact_text, selling_points, citations, risk_notes

    @staticmethod
    def _video_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
        supply: CampaignSupplySnapshot | None,
        locale: str = "zh-CN",
    ) -> dict:
        is_sixty_seconds = project.content_type == ContentType.short_video_60s
        end_second = 60 if is_sixty_seconds else 30
        middle_end = 48 if is_sixty_seconds else 20
        if locale == "en":
            if product.origin:
                hook = f"What makes {product.name} from {product.origin} worth a closer look?"
                origin_title = f"The verified origin story of {product.name}"
            else:
                hook = f"What makes {product.name} worth a closer look?"
                origin_title = f"The product story behind {product.name}"
            body = (
                f"This is {product.name} from {brand.name}. "
                f"Its verified product points are {selling_points}. "
                f"According to approved evidence: {fact_text}. "
            )
            if project.objective:
                body += f"This story is designed to help the audience {project.objective}. "
            if product.price_display:
                body += f"The current displayed offer is {product.price_display}. "
            if supply:
                body += (
                    f"This campaign uses the {supply.specification} specification, with "
                    f"{supply.available_quantity} {supply.quantity_unit} currently available "
                    f"and dispatch expected within {supply.ship_within_hours} hours. "
                )
            cta = "Ask us for the verified production or product details you want to check next."
            return {
                "format": "short_video_script",
                "duration_seconds": end_second,
                "title_options": [
                    origin_title,
                    f"Meet {product.name} in {end_second} seconds",
                    f"{brand.name}: a closer look at a real farm product",
                ],
                "hook": hook,
                "script": f"{hook} {body}{cta}",
                "shots": [
                    {
                        "seconds": "0-3",
                        "visual": "Reveal the real product and place of origin",
                        "voiceover": hook,
                    },
                    {
                        "seconds": f"3-{middle_end}",
                        "visual": "Show product details and real production scenes",
                        "voiceover": body.strip(),
                    },
                    {
                        "seconds": f"{middle_end}-{end_second}",
                        "visual": "Close on the brand and one clear next step",
                        "voiceover": cta,
                    },
                ],
                "cta": cta,
            }
        if locale == "zh-HK":
            if product.origin:
                hook = f"來自{product.origin}的{product.name}，有甚麼值得你留意？"
                origin_title = f"{product.name}的產地故事"
            else:
                hook = f"{product.name}有甚麼值得你留意？"
                origin_title = f"{product.name}的產品故事"
            body = (
                f"這是{brand.name}帶來的{product.name}。"
                f"已審批的產品重點包括{selling_points}。"
                f"根據經審核的產品資料：{fact_text}。"
            )
            if project.objective:
                body += f"這段內容希望幫助大家{project.objective}。"
            if product.price_display:
                body += f"目前展示資料為{product.price_display}。"
            if supply:
                body += (
                    f"本次活動規格為{supply.specification}，"
                    f"現時可售數量為{supply.available_quantity}{supply.quantity_unit}，"
                    f"下單後預計{supply.ship_within_hours}小時內寄出。"
                )
            cta = "想核實更多生產或產品資料，歡迎在留言區告訴我們。"
            return {
                "format": "short_video_script",
                "duration_seconds": end_second,
                "title_options": [
                    origin_title,
                    f"{end_second}秒認識{product.name}",
                    f"{brand.name}帶你細看真實農產",
                ],
                "hook": hook,
                "script": f"{hook}{body}{cta}",
                "shots": [
                    {"seconds": "0-3", "visual": "產品及產地快速亮相", "voiceover": hook},
                    {
                        "seconds": f"3-{middle_end}",
                        "visual": "產品細節及真實生產場景",
                        "voiceover": body,
                    },
                    {
                        "seconds": f"{middle_end}-{end_second}",
                        "visual": "品牌畫面及清晰行動提示",
                        "voiceover": cta,
                    },
                ],
                "cta": cta,
            }
        hook = f"你知道来自{product.origin or '产地'}的{product.name}有什么特别吗？"
        body = (
            f"这是{brand.name}带来的{product.name}。"
            f"它的主要特点是{selling_points}。"
            f"根据已审核资料：{fact_text}。"
        )
        if project.objective:
            body += f"这条内容希望帮助大家{project.objective}。"
        if product.price_display:
            body += f"当前展示信息为{product.price_display}。"
        if supply:
            body += (
                f"本次活动规格为{supply.specification}，"
                f"可售数量为{supply.available_quantity}{supply.quantity_unit}，"
                f"下单后预计{supply.ship_within_hours}小时内发货。"
            )
        cta = "想了解更多真实生产信息，欢迎在评论区留言。"
        return {
            "format": "short_video_script",
            "duration_seconds": end_second,
            "title_options": [
                f"{product.name}真实产地故事",
                f"{end_second}秒认识{product.name}",
                f"{brand.name}今天带你看好农产",
            ],
            "hook": hook,
            "script": f"{hook}{body}{cta}",
            "shots": [
                {"seconds": "0-3", "visual": "产品与产地快速亮相", "voiceover": hook},
                {
                    "seconds": f"3-{middle_end}",
                    "visual": "产品细节和生产场景",
                    "voiceover": body,
                },
                {
                    "seconds": f"{middle_end}-{end_second}",
                    "visual": "品牌与互动提示",
                    "voiceover": cta,
                },
            ],
            "cta": cta,
        }

    @staticmethod
    def _livestream_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
        supply: CampaignSupplySnapshot | None,
        locale: str = "zh-CN",
    ) -> dict:
        if locale == "en":
            greeting = (
                f"Welcome to {brand.name}. Today we are taking a closer look at {product.name}."
            )
            fact_statement = f"According to approved evidence: {fact_text}."
            if project.content_type == ContentType.livestream_opening:
                segments = [
                    {"stage": "Welcome", "script": greeting},
                    {
                        "stage": "Value preview",
                        "script": (
                            "We will cover its origin, verified characteristics and how to "
                            f"evaluate it, starting with {selling_points}."
                        ),
                    },
                    {
                        "stage": "Audience prompt",
                        "script": (
                            "Tell us in the comments: would you like to check the origin, "
                            "specification or storage guidance first?"
                        ),
                    },
                ]
                format_name = "livestream_opening"
            elif project.content_type == ContentType.livestream_interaction:
                segments = [
                    {
                        "stage": "Origin question",
                        "script": f"Where do you think {product.name} comes from?",
                    },
                    {
                        "stage": "Priority question",
                        "script": (
                            f"Which point would you like us to verify first: {selling_points}?"
                        ),
                    },
                    {
                        "stage": "Concern check",
                        "script": (
                            "When buying farm products, which matters most to you: quality, "
                            "storage or delivery?"
                        ),
                    },
                    {"stage": "Evidence-led answer", "script": fact_statement},
                ]
                format_name = "livestream_interaction"
            else:
                purchase_script = (
                    f"This campaign uses the {supply.specification} specification, with "
                    f"{supply.available_quantity} {supply.quantity_unit} currently available, "
                    f"dispatch expected within {supply.ship_within_hours} hours, and this "
                    f"freight policy: {supply.freight_policy}."
                    if supply
                    else (
                        "The specification is "
                        f"{product.specification or 'shown on the current product page'}, "
                        "and the storage guidance is "
                        + (product.storage_method or "provided in the approved product information")
                        + "."
                    )
                )
                segments = [
                    {"stage": "Product reveal", "script": greeting},
                    {
                        "stage": "Verified product points",
                        "script": f"The points worth checking are {selling_points}.",
                    },
                    {"stage": "Evidence", "script": fact_statement},
                    {"stage": "Purchase information", "script": purchase_script},
                    {
                        "stage": "Close and invite questions",
                        "script": (
                            "What else would you like to verify? Leave a question and we "
                            "will answer from the approved records."
                        ),
                    },
                ]
                format_name = "livestream_product_pitch"
            return {
                "format": format_name,
                "run_of_show": segments,
                "host_notes": [
                    "Use approved facts only; do not improvise health or outcome claims.",
                    "Confirm price, stock and delivery against the live campaign page.",
                ],
            }
        if locale == "zh-HK":
            greeting = f"歡迎來到{brand.name}直播，今日同大家認識{product.name}。"
            fact_statement = f"根據經審核的產品資料：{fact_text}。"
            if project.content_type == ContentType.livestream_opening:
                segments = [
                    {"stage": "歡迎", "script": greeting},
                    {
                        "stage": "內容預告",
                        "script": f"接下來會講清楚產地、特色及選購方法，先由{selling_points}說起。",
                    },
                    {
                        "stage": "互動",
                        "script": "新加入的朋友可以留言：你最想先了解產地、規格還是儲存方法？",
                    },
                ]
                format_name = "livestream_opening"
            elif project.content_type == ContentType.livestream_interaction:
                segments = [
                    {"stage": "產地提問", "script": f"大家估一估，{product.name}來自哪裏？"},
                    {"stage": "重點選擇", "script": f"{selling_points}之中，你最想先聽哪一點？"},
                    {"stage": "顧慮收集", "script": "選購農產品時，你最關心品質、儲存還是運送？"},
                    {"stage": "按證據回應", "script": fact_statement},
                ]
                format_name = "livestream_interaction"
            else:
                purchase_script = (
                    f"本次活動規格為{supply.specification}，"
                    f"現時可售{supply.available_quantity}{supply.quantity_unit}，"
                    f"下單後預計{supply.ship_within_hours}小時內寄出，"
                    f"運費安排為{supply.freight_policy}。"
                    if supply
                    else (
                        f"規格為{product.specification or '以目前商品頁為準'}，"
                        f"儲存建議為{product.storage_method or '請參閱已審批產品說明'}。"
                    )
                )
                segments = [
                    {"stage": "產品亮相", "script": greeting},
                    {"stage": "產品重點", "script": f"值得留意的已審批特點包括{selling_points}。"},
                    {"stage": "事實依據", "script": fact_statement},
                    {"stage": "選購提示", "script": purchase_script},
                    {
                        "stage": "互動收結",
                        "script": "還有哪項產品資料想核實？請留言，我們會按經審核的資料回覆。",
                    },
                ]
                format_name = "livestream_product_pitch"
            return {
                "format": format_name,
                "run_of_show": segments,
                "host_notes": [
                    "只陳述已審批事實，不即場延伸功效或結果承諾。",
                    "價格、庫存及物流以直播時的實際活動頁面為準。",
                ],
            }
        greeting = f"欢迎来到{brand.name}直播间，今天带大家认识{product.name}。"
        fact_statement = f"根据已审核资料：{fact_text}。"
        if project.content_type == ContentType.livestream_opening:
            segments = [
                {"stage": "欢迎", "script": greeting},
                {
                    "stage": "价值预告",
                    "script": f"接下来会讲清它的产地、特点和怎么选，核心特点是{selling_points}。",
                },
                {
                    "stage": "互动",
                    "script": "新进来的朋友可以在评论区告诉我，你最关心产地还是储存方法？",
                },
            ]
            format_name = "livestream_opening"
        elif project.content_type == ContentType.livestream_interaction:
            segments = [
                {"stage": "产地提问", "script": f"大家猜一猜，{product.name}来自哪里？"},
                {"stage": "选择提问", "script": f"你更想先听{selling_points}中的哪一点？"},
                {"stage": "顾虑收集", "script": "购买农产品时，你最担心品质、储存还是运输？"},
                {"stage": "事实回应", "script": fact_statement},
            ]
            format_name = "livestream_interaction"
        else:
            purchase_script = (
                f"本次活动规格为{supply.specification}，"
                f"可售数量为{supply.available_quantity}{supply.quantity_unit}，"
                f"下单后预计{supply.ship_within_hours}小时内发货，"
                f"运费规则为{supply.freight_policy}。"
                if supply
                else (
                    f"规格为{product.specification or '以实际商品页为准'}，"
                    f"储存建议是{product.storage_method or '请按商品说明储存'}。"
                )
            )
            segments = [
                {"stage": "产品亮相", "script": greeting},
                {"stage": "核心卖点", "script": f"它值得关注的特点是{selling_points}。"},
                {"stage": "事实依据", "script": fact_statement},
                {
                    "stage": "购买提示",
                    "script": purchase_script,
                },
                {"stage": "互动收口", "script": "还有哪项产品信息想核实？请留言，我们按资料回答。"},
            ]
            format_name = "livestream_product_pitch"
        return {
            "format": format_name,
            "run_of_show": segments,
            "host_notes": [
                "只陈述已审核事实，不临场扩展功效承诺。",
                "价格、库存和物流以直播时实际页面为准。",
            ],
        }

    @staticmethod
    def _text_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
        supply: CampaignSupplySnapshot | None,
        locale: str = "zh-CN",
    ) -> dict:
        if locale == "en":
            if project.content_type == ContentType.comment_reply:
                return {
                    "format": "comment_reply",
                    "reply_options": [
                        (
                            f"Thanks for asking. The verified points for {product.name} are "
                            f"{selling_points}; these details come from approved product records."
                        ),
                        f"The approved information we can confirm is: {fact_text}.",
                        (
                            "Tell us whether you want to check specification, storage or "
                            "delivery, and we will answer from the approved records."
                        ),
                    ],
                }
            if project.content_type == ContentType.title_and_cover:
                if product.origin:
                    origin_title = f"Meet {product.name} through its verified origin"
                    origin_cover = f"Verified origin · {product.name}"
                else:
                    origin_title = f"Meet {product.name} through its product story"
                    origin_cover = f"Product facts · {product.name}"
                return {
                    "format": "title_and_cover",
                    "title_options": [
                        origin_title,
                        f"Why {brand.name} chose {product.name}",
                        f"Check the facts before choosing {product.name}",
                    ],
                    "cover_copy_options": [
                        origin_cover,
                        "Check the facts. Choose with confidence.",
                        selling_points,
                    ],
                }
            supply_copy = (
                f"This campaign uses the {supply.specification} specification, with "
                f"{supply.available_quantity} {supply.quantity_unit} currently available "
                f"and dispatch expected within {supply.ship_within_hours} hours. "
                if supply
                else ""
            )
            headline = (
                f"A closer look at {product.name} from {product.origin}"
                if product.origin
                else f"A closer look at {product.name} and its product details"
            )
            return {
                "format": "social_post",
                "headline": headline,
                "body": (
                    f"{brand.name} is making the product information clear: the verified "
                    f"points are {selling_points}. According to approved evidence, "
                    f"{fact_text}. {supply_copy}"
                ).strip(),
                "cta": (
                    "What product detail would you like to verify next? Leave a question "
                    "and we will answer from the approved records."
                ),
                "hashtags": [f"#{product.name}", "#FarmProducts", "#OriginStory"],
            }
        if locale == "zh-HK":
            if project.content_type == ContentType.comment_reply:
                return {
                    "format": "comment_reply",
                    "reply_options": [
                        (
                            f"多謝關注。{product.name}的已審批重點包括{selling_points}，"
                            "相關資料來自經審核的產品檔案。"
                        ),
                        f"就你關心的產品資料，目前可以確認的是：{fact_text}。",
                        "如想了解規格、儲存或寄送資料，請告訴我們具體問題，我們會按資料核實。",
                    ],
                }
            if project.content_type == ContentType.title_and_cover:
                if product.origin:
                    origin_title = f"由產地認識{product.name}"
                    origin_cover = f"產地資料 · {product.name}"
                else:
                    origin_title = f"由產品故事認識{product.name}"
                    origin_cover = f"產品資料 · {product.name}"
                return {
                    "format": "title_and_cover",
                    "title_options": [
                        origin_title,
                        f"{brand.name}為何選擇{product.name}",
                        f"選購{product.name}前，先看清事實",
                    ],
                    "cover_copy_options": [
                        origin_cover,
                        "先看事實，再選農產",
                        selling_points,
                    ],
                }
            supply_copy = (
                f"本次活動規格為{supply.specification}，"
                f"現時可售{supply.available_quantity}{supply.quantity_unit}，"
                f"下單後預計{supply.ship_within_hours}小時內寄出。"
                if supply
                else ""
            )
            headline = (
                f"今日認真介紹來自{product.origin}的{product.name}"
                if product.origin
                else f"今日認真介紹{product.name}"
            )
            return {
                "format": "social_post",
                "headline": headline,
                "body": (
                    f"{brand.name}希望把產品資料講清楚：已審批重點包括{selling_points}。"
                    f"根據經審核的產品資料，{fact_text}。{supply_copy}"
                ),
                "cta": "你還想核實哪項產品資料？歡迎留言，我們會按經審核的資料補充。",
                "hashtags": [f"#{product.name}", "#農產品", "#產地故事"],
            }
        if project.content_type == ContentType.comment_reply:
            return {
                "format": "comment_reply",
                "reply_options": [
                    f"谢谢关注。{product.name}的主要特点是{selling_points}，相关信息来自已审核产品资料。",
                    f"关于您关心的产品信息，目前可确认的是：{fact_text}。",
                    "如果想了解规格、储存或发货信息，请告诉我们具体问题，我们会按资料核实。",
                ],
            }
        if project.content_type == ContentType.title_and_cover:
            return {
                "format": "title_and_cover",
                "title_options": [
                    f"从产地认识{product.name}",
                    f"{brand.name}为什么选择{product.name}",
                    f"{product.name}选购前先看这份事实卡",
                ],
                "cover_copy_options": [
                    f"真实产地 · {product.name}",
                    "先看事实，再选农产",
                    f"{selling_points}",
                ],
            }
        supply_copy = (
            f"本次活动规格为{supply.specification}，"
            f"可售{supply.available_quantity}{supply.quantity_unit}，"
            f"下单后预计{supply.ship_within_hours}小时内发货。"
            if supply
            else ""
        )
        return {
            "format": "social_post",
            "headline": f"今天认真介绍一份来自{product.origin or '真实产地'}的{product.name}",
            "body": (
                f"{brand.name}希望把产品信息讲清楚：它的主要特点是{selling_points}。"
                f"根据已审核资料，{fact_text}。{supply_copy}"
            ),
            "cta": "你还想了解哪项产品信息？欢迎留言，我们会继续补充可核实的答案。",
            "hashtags": [f"#{product.name}", "#农产品", "#产地故事"],
        }

    @staticmethod
    def _localized_shooting_checklist_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
        supply: CampaignSupplySnapshot | None,
        farmer_evidence: CampaignFarmerEvidenceSnapshot | None,
        locale: Literal["zh-HK", "en"],
    ) -> dict:
        is_english = locale == "en"
        origin = product.origin or (
            "the origin recorded in the approved product profile"
            if is_english
            else "已審核產品檔案記錄的產地"
        )
        if is_english:
            supply_task = (
                f"Confirm the current specification ({supply.specification}), available "
                f"quantity ({supply.available_quantity} {supply.quantity_unit}) and "
                "dispatch timing; update the approved snapshot if anything changed."
                if supply
                else "Before filming price, stock, harvest or delivery details, add and "
                "approve a current campaign supply snapshot."
            )
            farmer_task = (
                f"Before featuring {farmer_evidence.party_display_name}, verify each "
                "approved use of their name, image, voice and relationship wording."
                if farmer_evidence
                else "Do not film or describe a specific partnership or outcome without "
                "approved subject evidence and media consent."
            )
            supply_subject = (
                f"Current campaign specification: {supply.specification}"
                if supply
                else f"Approved specification for {product.name}"
            )
            supply_evidence = (
                f"Supply snapshot revision {supply.revision_number}; stock and delivery "
                "details must match the valid snapshot on filming day."
                if supply
                else "Do not show price, stock, harvest or delivery promises until a "
                "supply snapshot is approved."
            )
            return {
                "format": "mobile_shooting_checklist",
                "shooting_goal": (
                    f"Film a clear vertical story for {brand.name}'s {product.name}: show "
                    "the real product first, explain verified details, then close with one "
                    "specific next step."
                ),
                "before_shooting": [
                    {
                        "task": "Clean the phone lens, select vertical 9:16, lock focus and "
                        "exposure, and record five seconds of room sound.",
                        "required": True,
                        "reason": "Keep every clip clear, consistent and easier to edit.",
                    },
                    {
                        "task": f"Prepare an intact {product.name}, a clean background, its "
                        "packaging and approved proof of origin or specification.",
                        "required": True,
                        "reason": "Keep every visible product fact aligned with approved records.",
                    },
                    {
                        "task": supply_task,
                        "required": True,
                        "reason": "Price, stock, harvest and delivery details can change quickly.",
                    },
                    {
                        "task": farmer_task,
                        "required": True,
                        "reason": "Protect privacy, media rights and accurate relationship claims.",
                    },
                ],
                "shots": [
                    {
                        "sequence": 1,
                        "duration_seconds": 3,
                        "shot_size": "close-up",
                        "orientation": "vertical",
                        "subject": f"Front view of {product.name} and its packaging",
                        "action": "Hold a steady frame, then make one slow push-in.",
                        "voiceover_or_text": (
                            f"Start with a clear look at {product.name} from {origin}."
                        ),
                        "evidence_required": (
                            "Product name, packaging and origin must match approved records."
                        ),
                        "capture_notes": (
                            "Keep title space above the product and record at least two takes."
                        ),
                    },
                    {
                        "sequence": 2,
                        "duration_seconds": 8,
                        "shot_size": "detail",
                        "orientation": "vertical",
                        "subject": (
                            f"Visible texture, appearance or handling details of {product.name}"
                        ),
                        "action": (
                            "Record the same real detail from two angles without "
                            "appearance-altering filters."
                        ),
                        "voiceover_or_text": f"Verified product points: {selling_points}.",
                        "evidence_required": f"Approved knowledge: {fact_text}",
                        "capture_notes": (
                            "Use soft or natural light and keep one continuous original take."
                        ),
                    },
                    {
                        "sequence": 3,
                        "duration_seconds": 8,
                        "shot_size": "medium close-up",
                        "orientation": "vertical",
                        "subject": supply_subject,
                        "action": (
                            "Show weighing, packing or specification comparison without "
                            "fixing temporary stock in frame."
                        ),
                        "voiceover_or_text": (
                            "Use the currently approved campaign page for specification "
                            "and supply details."
                        ),
                        "evidence_required": supply_evidence,
                        "capture_notes": (
                            "Mask phone numbers, addresses and order numbers on labels "
                            "or documents."
                        ),
                    },
                    {
                        "sequence": 4,
                        "duration_seconds": 6,
                        "shot_size": "medium",
                        "orientation": "vertical",
                        "subject": f"A real use, packing or storage moment for {product.name}",
                        "action": (
                            "Complete one continuous action and keep two seconds before "
                            "and after it."
                        ),
                        "voiceover_or_text": product.storage_method
                        or "Follow the approved product guidance for storage and use.",
                        "evidence_required": (
                            "Storage and use guidance must come from approved product records."
                        ),
                        "capture_notes": (
                            "Keep packaging, tools, table position and hand movement continuous."
                        ),
                    },
                    {
                        "sequence": 5,
                        "duration_seconds": 5,
                        "shot_size": "close-up",
                        "orientation": "vertical",
                        "subject": f"{brand.name} identity with {product.name}",
                        "action": "Hold a clean closing frame with room for one button or caption.",
                        "voiceover_or_text": project.objective
                        or (
                            "Check the approved product information before deciding what "
                            "to explore next."
                        ),
                        "evidence_required": (
                            "The call to action must not include unapproved price, "
                            "scarcity or outcome promises."
                        ),
                        "capture_notes": (
                            "Hold the final frame for at least two seconds for safe "
                            "platform cropping."
                        ),
                    },
                ],
                "continuity_checks": [
                    (
                        "Keep every shot vertical 9:16 with consistent packaging, "
                        "surface and light direction."
                    ),
                    (
                        "Match every spoken and visible origin, specification and brand "
                        "name to approved records."
                    ),
                    (
                        "Remove private contact, address, order, vehicle and unapproved "
                        "face or voice details."
                    ),
                    (
                        "Keep original files, filming date and evidence revision for "
                        "review and traceability."
                    ),
                ],
                "do_not_capture_or_claim": [
                    (
                        "Do not use filters, substitutes or staging to change real "
                        "colour, size, quantity or freshness."
                    ),
                    (
                        "Do not claim unapproved certifications, health effects, sales, "
                        "income or customer outcomes."
                    ),
                    (
                        "Do not present expired price, stock, harvest or delivery details "
                        "as long-term promises."
                    ),
                    (
                        "Do not use a farmer's name, image, voice, story or relationship "
                        "outside the approved consent scope."
                    ),
                ],
            }

        supply_task = (
            f"核對本次活動規格「{supply.specification}」、可售數量 "
            f"{supply.available_quantity}{supply.quantity_unit} 及出貨時效；"
            "如拍攝當日有變，須先更新已審核快照。"
            if supply
            else "拍攝價格、庫存、採收或物流資訊前，先補充並審核本次活動供應快照。"
        )
        farmer_task = (
            f"如涉及{farmer_evidence.party_display_name}的姓名、聲音、影像或合作關係，"
            "逐項核對授權範圍及可用說法。"
            if farmer_evidence
            else "未取得已審核的主體證據及影像授權前，不拍攝或聲稱具體合作關係及成效。"
        )
        supply_subject = (
            f"本次活動規格：{supply.specification}" if supply else f"{product.name}的已審核規格"
        )
        supply_evidence = (
            f"供應快照第 {supply.revision_number} 版；庫存及物流以拍攝當日有效快照為準。"
            if supply
            else "供應快照審核通過前，不展示價格、庫存、採收或物流承諾。"
        )
        return {
            "format": "mobile_shooting_checklist",
            "shooting_goal": (
                f"以手機直度拍好{brand.name}的{product.name}：先讓觀眾看清真實產品，"
                "再用可核實畫面說明重點，最後給出一個清晰行動提示。"
            ),
            "before_shooting": [
                {
                    "task": "清潔手機鏡頭，設定直度 9:16，鎖定曝光及對焦，並錄下 5 秒環境聲。",
                    "required": True,
                    "reason": "確保素材清晰、方向一致，亦方便後期保留自然聲。",
                },
                {
                    "task": (
                        f"準備外觀完整的{product.name}、乾淨背景、包裝及可證明產地或規格的"
                        "已審核資料。"
                    ),
                    "required": True,
                    "reason": "確保畫面中的產品事實與已審核資料一致。",
                },
                {
                    "task": supply_task,
                    "required": True,
                    "reason": "價格、庫存、採收及物流屬易變資訊，不可沿用過期說法。",
                },
                {
                    "task": farmer_task,
                    "required": True,
                    "reason": "保障私隱、肖像及合作關係描述的真確性。",
                },
            ],
            "shots": [
                {
                    "sequence": 1,
                    "duration_seconds": 3,
                    "shot_size": "近鏡",
                    "orientation": "vertical",
                    "subject": f"{product.name}成品及包裝正面",
                    "action": "固定機位拍攝主體，再緩慢向前推近。",
                    "voiceover_or_text": f"先看清這份來自{origin}的{product.name}。",
                    "evidence_required": "產品名稱、包裝及產地必須與已審核資料一致。",
                    "capture_notes": "主體放在畫面中央偏下，上方預留標題位置；至少拍兩次。",
                },
                {
                    "sequence": 2,
                    "duration_seconds": 8,
                    "shot_size": "特寫",
                    "orientation": "vertical",
                    "subject": f"{product.name}可見的外觀、質感或處理細節",
                    "action": "從兩個角度記錄真實細節，不使用改變顏色或大小的濾鏡。",
                    "voiceover_or_text": f"已審核的產品重點：{selling_points}。",
                    "evidence_required": f"知識庫資料：{fact_text}",
                    "capture_notes": "使用自然光或柔光，並保留一段連續原片。",
                },
                {
                    "sequence": 3,
                    "duration_seconds": 8,
                    "shot_size": "中近鏡",
                    "orientation": "vertical",
                    "subject": supply_subject,
                    "action": "拍攝稱重、包裝或規格核對過程，不把臨時庫存數字永久放入畫面。",
                    "voiceover_or_text": "規格及供應資訊以本次活動已審核頁面為準。",
                    "evidence_required": supply_evidence,
                    "capture_notes": "如拍到標籤或單據，遮蓋電話、地址及訂單編號。",
                },
                {
                    "sequence": 4,
                    "duration_seconds": 6,
                    "shot_size": "中鏡",
                    "orientation": "vertical",
                    "subject": f"{product.name}的真實使用、分裝或儲存場景",
                    "action": "完成一個連貫動作，並在動作前後各多拍 2 秒。",
                    "voiceover_or_text": product.storage_method
                    or "儲存及使用方式以已審核產品說明為準。",
                    "evidence_required": "儲存或使用建議必須來自已審核產品資料。",
                    "capture_notes": "保持包裝、器具、檯面及手部動作連貫。",
                },
                {
                    "sequence": 5,
                    "duration_seconds": 5,
                    "shot_size": "近鏡",
                    "orientation": "vertical",
                    "subject": f"{brand.name}品牌標識及{product.name}",
                    "action": "穩定停留，並預留按鈕或字幕位置。",
                    "voiceover_or_text": project.objective
                    or "查看已審核產品資訊，再決定是否進一步了解。",
                    "evidence_required": "行動提示不可包含未審核價格、稀缺性或效果保證。",
                    "capture_notes": "最後一格至少靜止 2 秒，方便不同平台安全裁切。",
                },
            ],
            "continuity_checks": [
                "所有鏡頭保持直度 9:16，產品包裝、檯面及光線方向前後一致。",
                "逐鏡核對口述、字幕、包裝及畫面中的產地、規格與品牌名稱。",
                "確認沒有拍到私人電話、地址、訂單、車牌或未經授權的人臉與聲音。",
                "保留原始素材、拍攝日期及證據版本，方便審核追溯。",
            ],
            "do_not_capture_or_claim": [
                "不得使用濾鏡、替代品或擺拍改變產品真實顏色、大小、數量或新鮮度。",
                "不得聲稱未經審核的認證、治療或保健功效、銷量、收益及消費者結果。",
                "不得把過期價格、庫存、採收日期或物流時效拍成長期有效承諾。",
                "不得在授權範圍外使用農戶姓名、肖像、聲音、故事或合作關係。",
            ],
        }

    @staticmethod
    def _shooting_checklist_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
        supply: CampaignSupplySnapshot | None,
        farmer_evidence: CampaignFarmerEvidenceSnapshot | None,
        locale: str = "zh-CN",
    ) -> dict:
        if locale == "zh-HK":
            return DeterministicProvider._localized_shooting_checklist_content(
                project,
                brand,
                product,
                fact_text,
                selling_points,
                supply,
                farmer_evidence,
                "zh-HK",
            )
        if locale == "en":
            return DeterministicProvider._localized_shooting_checklist_content(
                project,
                brand,
                product,
                fact_text,
                selling_points,
                supply,
                farmer_evidence,
                "en",
            )
        product_origin = product.origin or "已审核资料记录的产地"
        supply_task = (
            f"核对本次活动规格“{supply.specification}”、可售数量"
            f"{supply.available_quantity}{supply.quantity_unit}和发货时效，"
            "拍摄当天如有变化须先更新审核快照。"
            if supply
            else "拍摄价格、库存、采收和物流信息前，先补充并审核本次活动供给快照。"
        )
        farmer_task = (
            f"涉及{farmer_evidence.party_display_name}的姓名、声音、影像或合作关系时，"
            "逐项核对授权范围和可用表述。"
            if farmer_evidence
            else "未取得已审核主体证据与影像授权时，不拍摄或声称具体合作关系和成效。"
        )
        supply_subject = (
            f"本次活动规格：{supply.specification}" if supply else f"{product.name}的已审核规格信息"
        )
        supply_evidence = (
            f"供给快照 #{supply.revision_number}；库存与物流以拍摄当天有效快照为准"
            if supply
            else "不得展示价格、库存、采收或物流承诺，直至供给快照审核通过"
        )
        return {
            "format": "mobile_shooting_checklist",
            "shooting_goal": (
                f"用手机竖屏拍清{brand.name}的{product.name}：先让观众看见产品，"
                "再用可核实画面说明特点，最后给出明确行动提示。"
            ),
            "before_shooting": [
                {
                    "task": "清洁手机镜头，开启竖屏 9:16，锁定曝光与对焦，并录制 5 秒环境声。",
                    "required": True,
                    "reason": "保证素材清晰、方向一致，并为后期剪辑保留自然声。",
                },
                {
                    "task": (
                        f"准备外观完整的{product.name}、干净背景、包装和能证明产地或规格的"
                        "已审核材料；不得用未审核道具暗示认证或功效。"
                    ),
                    "required": True,
                    "reason": "让画面中的产品事实与审核资料一致。",
                },
                {
                    "task": supply_task,
                    "required": True,
                    "reason": "价格、库存、采收和物流属于易变化信息，不能沿用过期口径。",
                },
                {
                    "task": farmer_task,
                    "required": True,
                    "reason": "保护农户隐私、肖像和合作关系表述的真实性。",
                },
            ],
            "shots": [
                {
                    "sequence": 1,
                    "duration_seconds": 3,
                    "shot_size": "近景",
                    "orientation": "vertical",
                    "subject": f"{product.name}成品与包装正面",
                    "action": "固定机位拍摄主体，再缓慢向前推进；补拍一条无手部遮挡的安全镜头。",
                    "voiceover_or_text": f"先看清这份来自{product_origin}的{product.name}。",
                    "evidence_required": "产品名称、包装和产地表述必须与已审核产品资料一致。",
                    "capture_notes": "主体置于画面中央偏下，顶部预留标题区；每条至少拍两遍。",
                },
                {
                    "sequence": 2,
                    "duration_seconds": 8,
                    "shot_size": "特写",
                    "orientation": "vertical",
                    "subject": f"{product.name}可见的外观、质地或处理细节",
                    "action": "从两个角度记录真实细节，不使用滤镜改变颜色或大小。",
                    "voiceover_or_text": f"已审核的产品特点：{selling_points}。",
                    "evidence_required": f"知识库事实：{fact_text}",
                    "capture_notes": "使用自然光或柔光；保留一条连续原片，避免只拍无法核验的局部。",
                },
                {
                    "sequence": 3,
                    "duration_seconds": 8,
                    "shot_size": "中近景",
                    "orientation": "vertical",
                    "subject": supply_subject,
                    "action": "拍摄称量、包装或规格对照过程；不要把临时库存数字永久印入画面。",
                    "voiceover_or_text": "规格与供给信息以本次活动已审核页面为准。",
                    "evidence_required": supply_evidence,
                    "capture_notes": "如拍到标签或单据，遮挡手机号、地址、订单号等个人信息。",
                },
                {
                    "sequence": 4,
                    "duration_seconds": 6,
                    "shot_size": "中景",
                    "orientation": "vertical",
                    "subject": f"{product.name}的真实使用、分装或储存场景",
                    "action": "完成一个连贯动作，并补拍动作开始和结束各 2 秒。",
                    "voiceover_or_text": (
                        product.storage_method or "储存与使用方式请以已审核产品说明为准。"
                    ),
                    "evidence_required": "储存或使用建议必须来自已审核产品资料。",
                    "capture_notes": "保持包装、器具和台面位置连续，避免跳轴和手部动作断裂。",
                },
                {
                    "sequence": 5,
                    "duration_seconds": 5,
                    "shot_size": "近景",
                    "orientation": "vertical",
                    "subject": f"{brand.name}品牌标识与{product.name}",
                    "action": "稳定停留并留出按钮或字幕区域，不用夸张促销贴纸遮挡产品。",
                    "voiceover_or_text": project.objective
                    or "查看已审核产品信息，再决定是否了解更多。",
                    "evidence_required": "行动引导不得包含未审核价格、稀缺性或效果保证。",
                    "capture_notes": "最后一帧至少静止 2 秒，便于不同平台安全裁切。",
                },
            ],
            "continuity_checks": [
                "所有镜头保持竖屏 9:16，产品包装、台面和光线方向前后一致。",
                "逐镜核对口播、字幕、包装和画面中的产地、规格及品牌名称。",
                "确认没有拍到个人电话、住址、订单、车牌或未经授权的人脸与声音。",
                "保留原始素材、拍摄日期和对应证据版本，便于审核追溯。",
            ],
            "do_not_capture_or_claim": [
                "不得用滤镜、替代品或摆拍改变产品真实颜色、大小、数量或新鲜度。",
                "不得声称未经审核的认证、治疗或保健功效、销量、收益及消费者结果。",
                "不得把过期价格、库存、采收日期或物流时效拍成长期有效承诺。",
                "不得在授权范围外使用农户姓名、肖像、声音、故事或合作关系。",
            ],
        }

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
        supply: CampaignSupplySnapshot | None = None,
        farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
        brief: CampaignBriefRevision | None = None,
    ) -> GenerationResult:
        started = time.perf_counter()
        locale = brief.locale if brief else "zh-CN"
        fact_text, selling_points, citations, risk_notes = self._common_context(
            brand, product, sources, locale
        )
        if project.content_type in {
            ContentType.short_video_30s,
            ContentType.short_video_60s,
        }:
            content = self._video_content(
                project, brand, product, fact_text, selling_points, supply, locale
            )
        elif project.content_type in {
            ContentType.livestream_opening,
            ContentType.livestream_product_pitch,
            ContentType.livestream_interaction,
        }:
            content = self._livestream_content(
                project, brand, product, fact_text, selling_points, supply, locale
            )
        elif project.content_type == ContentType.mobile_shooting_checklist:
            content = self._shooting_checklist_content(
                project,
                brand,
                product,
                fact_text,
                selling_points,
                supply,
                farmer_evidence,
                locale,
            )
        else:
            content = self._text_content(
                project, brand, product, fact_text, selling_points, supply, locale
            )
        if brief:
            required_copy = " ".join(
                message.strip() for message in brief.mandatory_messages if message.strip()
            )
            if content["format"] == "short_video_script":
                if brief.core_message:
                    content["hook"] = brief.core_message
                    content["script"] = f"{brief.core_message} {content['script']}"
                    content["shots"][0]["voiceover"] = brief.core_message
                if brief.desired_action:
                    content["cta"] = brief.desired_action
                    content["script"] = f"{content['script']} {brief.desired_action}"
                    content["shots"][-1]["voiceover"] = brief.desired_action
                if required_copy:
                    content["script"] = f"{content['script']} {required_copy}"
                    content["shots"][1]["voiceover"] = (
                        f"{content['shots'][1]['voiceover']} {required_copy}"
                    )
            elif content["format"] == "social_post":
                if brief.core_message:
                    content["headline"] = brief.core_message
                if brief.audience_need:
                    content["body"] = f"{brief.audience_need} {content['body']}"
                if brief.desired_action:
                    content["cta"] = brief.desired_action
                if required_copy:
                    content["body"] = f"{content['body']} {required_copy}"
            elif content["format"] == "title_and_cover":
                if brief.core_message:
                    content["title_options"][0] = brief.core_message
                    content["cover_copy_options"][0] = brief.core_message
                if required_copy:
                    content["title_options"].append(required_copy)
            elif content["format"] == "comment_reply":
                if brief.desired_action:
                    content["reply_options"].append(brief.desired_action)
                if required_copy:
                    content["reply_options"].append(required_copy)
            elif content["format"].startswith("livestream_"):
                if brief.core_message:
                    content["run_of_show"][0]["script"] = brief.core_message
                if brief.desired_action:
                    content["run_of_show"][-1]["script"] = brief.desired_action
                if required_copy:
                    stage = {
                        "en": "Required campaign message",
                        "zh-HK": "活動必須提及",
                    }.get(locale, "活动必讲信息")
                    content["run_of_show"].insert(
                        -1,
                        {"stage": stage, "script": required_copy},
                    )
            elif content["format"] == "mobile_shooting_checklist":
                if brief.core_message:
                    content["shots"][0]["voiceover_or_text"] = brief.core_message
                if required_copy:
                    content["shots"][1]["voiceover_or_text"] = (
                        f"{content['shots'][1]['voiceover_or_text']} {required_copy}"
                    )
                if brief.desired_action:
                    content["shots"][-1]["voiceover_or_text"] = brief.desired_action
        content["risk_notes"] = risk_notes
        if brief:
            prohibited_prefix = {
                "en": "Do not use the campaign brief's prohibited wording: ",
                "zh-HK": "不得使用活動 Brief 的禁用字句：",
            }.get(locale, "不得使用活动简报禁用表述：")
            content["risk_notes"].extend(
                f"{prohibited_prefix}{message}" for message in brief.prohibited_messages
            )
        if farmer_evidence:
            farmer_risk = {
                "en": (
                    "Farmer-impact and partnership claims must stay within approved "
                    "evidence and consent."
                ),
                "zh-HK": "助農及合作關係說法只可使用已審批且在授權範圍內的表述。",
            }.get(locale, "助农与合作关系声明只能使用已审核且在授权范围内的表述。")
            content["risk_notes"].append(farmer_risk)
        content["citations"] = citations
        return GenerationResult(
            content=content,
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
        )


class AIProviderError(RuntimeError):
    """A safe, credential-free error raised when an external provider fails."""

    def __init__(self, message: str, *, code: str = "provider_error") -> None:
        super().__init__(message)
        self.code = code


class _StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citations: list["_Citation"]
    risk_notes: list[str]


class _Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    label: str


class _Shot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seconds: str = Field(min_length=1)
    visual: str = Field(min_length=1)
    voiceover: str = Field(min_length=1)


class _ShortVideoOutput(_StrictOutput):
    format: Literal["short_video_script"]
    duration_seconds: int
    title_options: list[str] = Field(min_length=1)
    hook: str = Field(min_length=1)
    script: str = Field(min_length=1)
    shots: list[_Shot] = Field(min_length=1)
    cta: str = Field(min_length=1)


class _RunOfShowItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(min_length=1)
    script: str = Field(min_length=1)


class _LivestreamOutput(_StrictOutput):
    format: Literal[
        "livestream_opening",
        "livestream_product_pitch",
        "livestream_interaction",
    ]
    run_of_show: list[_RunOfShowItem] = Field(min_length=1)
    host_notes: list[str] = Field(min_length=1)


class _CommentReplyOutput(_StrictOutput):
    format: Literal["comment_reply"]
    reply_options: list[str] = Field(min_length=1)


class _SocialPostOutput(_StrictOutput):
    format: Literal["social_post"]
    headline: str = Field(min_length=1)
    body: str = Field(min_length=1)
    cta: str = Field(min_length=1)
    hashtags: list[str]


class _TitleAndCoverOutput(_StrictOutput):
    format: Literal["title_and_cover"]
    title_options: list[str] = Field(min_length=1)
    cover_copy_options: list[str] = Field(min_length=1)


class _ShootingPreparationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1)
    required: bool
    reason: str = Field(min_length=1)


class _ShootingShot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    duration_seconds: int = Field(ge=1, le=120)
    shot_size: str = Field(min_length=1)
    orientation: Literal["vertical"]
    subject: str = Field(min_length=1)
    action: str = Field(min_length=1)
    voiceover_or_text: str = Field(min_length=1)
    evidence_required: str = Field(min_length=1)
    capture_notes: str = Field(min_length=1)


class _MobileShootingChecklistOutput(_StrictOutput):
    format: Literal["mobile_shooting_checklist"]
    shooting_goal: str = Field(min_length=1)
    before_shooting: list[_ShootingPreparationItem] = Field(min_length=1)
    shots: list[_ShootingShot] = Field(min_length=1)
    continuity_checks: list[str] = Field(min_length=1)
    do_not_capture_or_claim: list[str] = Field(min_length=1)


_OUTPUT_MODELS: dict[ContentType, type[_StrictOutput]] = {
    ContentType.short_video_30s: _ShortVideoOutput,
    ContentType.short_video_60s: _ShortVideoOutput,
    ContentType.livestream_opening: _LivestreamOutput,
    ContentType.livestream_product_pitch: _LivestreamOutput,
    ContentType.livestream_interaction: _LivestreamOutput,
    ContentType.comment_reply: _CommentReplyOutput,
    ContentType.social_post: _SocialPostOutput,
    ContentType.title_and_cover: _TitleAndCoverOutput,
    ContentType.mobile_shooting_checklist: _MobileShootingChecklistOutput,
}

_EXPECTED_FORMATS = {
    ContentType.short_video_30s: "short_video_script",
    ContentType.short_video_60s: "short_video_script",
    ContentType.livestream_opening: "livestream_opening",
    ContentType.livestream_product_pitch: "livestream_product_pitch",
    ContentType.livestream_interaction: "livestream_interaction",
    ContentType.comment_reply: "comment_reply",
    ContentType.social_post: "social_post",
    ContentType.title_and_cover: "title_and_cover",
    ContentType.mobile_shooting_checklist: "mobile_shooting_checklist",
}


def validate_generation_output(
    content: object,
    content_type: ContentType,
    trusted_source_labels: dict[str, str],
) -> dict:
    """Validate provider output before it can become a durable content version."""

    if not isinstance(content, dict):
        raise AIProviderError(
            "The configured AI provider returned a non-object response",
            code="provider_invalid_output",
        )
    if content.get("format") != _EXPECTED_FORMATS[content_type]:
        raise AIProviderError(
            "The configured AI provider returned the wrong content format",
            code="provider_invalid_output",
        )
    try:
        validated = _OUTPUT_MODELS[content_type].model_validate(content)
    except ValidationError:
        raise AIProviderError(
            "The configured AI provider returned content that failed validation",
            code="provider_invalid_output",
        ) from None

    normalized = validated.model_dump(mode="json")
    if content_type == ContentType.short_video_30s and normalized["duration_seconds"] != 30:
        raise AIProviderError(
            "The configured AI provider returned the wrong video duration",
            code="provider_invalid_output",
        )
    if content_type == ContentType.short_video_60s and normalized["duration_seconds"] != 60:
        raise AIProviderError(
            "The configured AI provider returned the wrong video duration",
            code="provider_invalid_output",
        )
    if content_type == ContentType.mobile_shooting_checklist and [
        shot["sequence"] for shot in normalized["shots"]
    ] != [1, 2, 3, 4, 5]:
        raise AIProviderError(
            "The configured AI provider must return five consecutive shooting steps",
            code="provider_invalid_output",
        )

    if trusted_source_labels and not normalized["citations"]:
        raise AIProviderError(
            "The configured AI provider omitted required source citations",
            code="provider_missing_citation",
        )

    normalized_citations: list[dict[str, str]] = []
    seen_source_ids: set[str] = set()
    for citation in normalized["citations"]:
        source_id = citation["source_id"]
        if source_id not in trusted_source_labels:
            raise AIProviderError(
                "The configured AI provider cited an unavailable knowledge source",
                code="provider_unknown_citation",
            )
        if source_id in seen_source_ids:
            continue
        seen_source_ids.add(source_id)
        normalized_citations.append(
            {
                "source_id": source_id,
                "label": trusted_source_labels[source_id],
            }
        )
    normalized["citations"] = normalized_citations
    return normalized


def _content_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            text
            for key, nested in value.items()
            if key not in {"citations", "risk_notes", "do_not_capture_or_claim"}
            for text in _content_strings(nested)
        ]
    if isinstance(value, list):
        return [text for nested in value for text in _content_strings(nested)]
    return []


def validate_campaign_brief_output(
    content: dict,
    brief: CampaignBriefRevision | None,
) -> None:
    """Apply small deterministic marketing constraints after model validation."""

    if brief is None:
        return
    searchable = "\n".join(_content_strings(content)).casefold()
    missing = [
        message
        for message in brief.mandatory_messages
        if message.strip() and message.strip().casefold() not in searchable
    ]
    if missing:
        raise AIProviderError(
            "Generated content omitted a mandatory campaign message",
            code="campaign_mandatory_message_missing",
        )
    prohibited = [
        message
        for message in brief.prohibited_messages
        if message.strip() and message.strip().casefold() in searchable
    ]
    if prohibited:
        raise AIProviderError(
            "Generated content used a prohibited campaign message",
            code="campaign_prohibited_message_used",
        )

    constraints = brief.channel_constraints or {}
    maximum_duration = constraints.get("max_duration_seconds")
    duration = content.get("duration_seconds")
    if (
        isinstance(maximum_duration, (int, float))
        and not isinstance(maximum_duration, bool)
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and duration > maximum_duration
    ):
        raise AIProviderError(
            "Generated content exceeds the campaign duration limit",
            code="campaign_duration_exceeded",
        )


def _optional_usage_count(payload: object, key: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenAICompatibleProvider:
    """Adapter for servers implementing the OpenAI chat-completions contract."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 45,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    @staticmethod
    def _payload(
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
        supply: CampaignSupplySnapshot | None = None,
        farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
        brief: CampaignBriefRevision | None = None,
    ) -> dict:
        verified_sources = [
            {
                "source_id": source.id,
                "label": source.citation_label or source.title,
                "content": source.content,
            }
            for source in sources
        ]
        task = {
            "content_type": project.content_type.value,
            "platform": project.platform,
            "target_audience": project.target_audience,
            "objective": project.objective,
            "tone": project.tone,
            "extra_requirements": project.extra_requirements,
            "brand": {"name": brand.name, "story": brand.story, "voice": brand.voice},
            "product": {
                "name": product.name,
                "origin": product.origin,
                "specification": product.specification,
                "price_display": product.price_display,
                "storage_method": product.storage_method,
                "selling_points": product.selling_points,
                "prohibited_claims": product.prohibited_claims,
            },
            "verified_sources": verified_sources,
            "campaign_brief": (
                {
                    "brief_revision_id": brief.id,
                    "revision_number": brief.revision_number,
                    "platform": brief.platform,
                    "target_audience": brief.target_audience,
                    "objective": brief.objective,
                    "tone": brief.tone,
                    "core_message": brief.core_message,
                    "audience_need": brief.audience_need,
                    "desired_action": brief.desired_action,
                    "proof_points": brief.proof_points,
                    "claim_evidence": brief.claim_evidence,
                    "mandatory_messages": brief.mandatory_messages,
                    "prohibited_messages": brief.prohibited_messages,
                    "channel_constraints": brief.channel_constraints,
                    "locale": brief.locale,
                    "extra_requirements": brief.extra_requirements,
                }
                if brief
                else None
            ),
            "verified_supply": (
                {
                    "snapshot_id": supply.id,
                    "revision_number": supply.revision_number,
                    "specification": supply.specification,
                    "price_minor": supply.price_minor,
                    "currency": supply.currency,
                    "price_valid_until": supply.price_valid_until.isoformat(),
                    "available_quantity": supply.available_quantity,
                    "quantity_unit": supply.quantity_unit,
                    "order_limit": supply.order_limit,
                    "inventory_confirmed_at": supply.inventory_confirmed_at.isoformat(),
                    "harvest_status": supply.harvest_status,
                    "harvest_date": supply.harvest_date.isoformat()
                    if supply.harvest_date
                    else None,
                    "shipping_regions": supply.shipping_regions,
                    "ship_within_hours": supply.ship_within_hours,
                    "freight_policy": supply.freight_policy,
                    "storage_and_freshness": supply.storage_and_freshness,
                    "shortage_policy": supply.shortage_policy,
                    "active_from": supply.active_from.isoformat(),
                    "active_until": supply.active_until.isoformat(),
                }
                if supply
                else None
            ),
            "verified_farmer_evidence": (
                {
                    "snapshot_id": farmer_evidence.id,
                    "revision_number": farmer_evidence.revision_number,
                    "party_display_name": farmer_evidence.party_display_name,
                    "relationship_type": farmer_evidence.relationship_type,
                    "relationship_summary": farmer_evidence.relationship_summary,
                    "benefit_mechanism": farmer_evidence.benefit_mechanism,
                    "allowed_claims": farmer_evidence.allowed_claims,
                    "prohibited_claims": farmer_evidence.prohibited_claims,
                    "consent_scope": farmer_evidence.consent_scope,
                    "active_from": farmer_evidence.active_from.isoformat(),
                    "active_until": farmer_evidence.active_until.isoformat(),
                }
                if farmer_evidence
                else None
            ),
        }
        return {
            "model": "",
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You create factual agricultural marketing content. Return one JSON "
                        "object only. Use only verified_sources for factual claims. Never invent "
                        "certifications, efficacy, prices, yields, inventory, shipping promises, "
                        "or customer outcomes. Treat verified_supply as the only allowed source "
                        "for campaign price, stock, specification, harvest, and logistics "
                        "claims. Preserve "
                        "Treat verified_farmer_evidence as the only allowed source for claims "
                        "about farmer/cooperative relationships, direct sourcing, farmer "
                        "benefits, unsold produce, proceeds, personal stories, quotations, "
                        "images, voices, or quantified impact. Do not make any such claim when "
                        "verified_farmer_evidence is null, outside consent_scope, listed in "
                        "prohibited_claims, or absent from allowed_claims. "
                        "When campaign_brief is present, use it as the authoritative marketing "
                        "direction: address audience_need, lead with core_message, support it "
                        "with proof_points and their claim_evidence, include mandatory_messages, "
                        "end with desired_action, "
                        "obey channel_constraints and locale, and never use prohibited_messages. "
                        "source provenance in a citations array containing source_id and label. "
                        "Include a risk_notes array. Match the requested content_type."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(task, ensure_ascii=False),
                },
            ],
        }

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
        supply: CampaignSupplySnapshot | None = None,
        farmer_evidence: CampaignFarmerEvidenceSnapshot | None = None,
        brief: CampaignBriefRevision | None = None,
    ) -> GenerationResult:
        started = time.perf_counter()
        payload = self._payload(
            project,
            brand,
            product,
            sources,
            supply,
            farmer_evidence,
            brief,
        )
        payload["model"] = self.model
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            raw_content = data["choices"][0]["message"]["content"]
            content = json.loads(raw_content)
        except httpx.TimeoutException:
            raise AIProviderError(
                "The configured AI provider timed out",
                code="provider_timeout",
            ) from None
        except httpx.HTTPStatusError:
            raise AIProviderError(
                "The configured AI provider request failed",
                code="provider_http_error",
            ) from None
        except httpx.HTTPError:
            raise AIProviderError(
                "The configured AI provider could not be reached",
                code="provider_connection_error",
            ) from None
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise AIProviderError(
                "The configured AI provider did not return valid structured content",
                code="provider_invalid_response",
            ) from None
        if not isinstance(content, dict):
            raise AIProviderError(
                "The configured AI provider returned a non-object response",
                code="provider_invalid_response",
            )
        return GenerationResult(
            content=content,
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
            input_tokens=_optional_usage_count(data, "prompt_tokens"),
            output_tokens=_optional_usage_count(data, "completion_tokens"),
            provider_request_id=data.get("id") if isinstance(data.get("id"), str) else None,
        )


def get_ai_provider(settings: Settings | None = None) -> AIProvider:
    settings = settings or get_settings()
    if settings.ai_provider.strip().lower() == "openai-compatible":
        return OpenAICompatibleProvider(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    return DeterministicProvider()
