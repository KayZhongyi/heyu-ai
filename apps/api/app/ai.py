import time
from dataclasses import dataclass
from typing import Protocol

from app.models import Brand, ContentProject, ContentType, Product

PROMPT_NAME = "agricultural-content-script"
PROMPT_VERSION = "1.2.0"


@dataclass(frozen=True)
class ContextSource:
    id: str
    title: str
    citation_label: str
    content: str
    content_sha256: str


@dataclass
class GenerationResult:
    content: dict
    latency_ms: int


class AIProvider(Protocol):
    name: str
    model: str

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
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
    ) -> tuple[str, str, list[dict], list[str]]:
        facts = [source.content.strip() for source in sources if source.content.strip()]
        fact_text = "；".join(facts[:3]) or "请先补充并审核产品资料"
        selling_points = "、".join(product.selling_points) or "真实产地与产品特色"
        citations = [
            {"source_id": source.id, "label": source.citation_label or source.title}
            for source in sources
        ]
        risk_notes = [f"禁止使用：{claim}" for claim in product.prohibited_claims]
        return fact_text, selling_points, citations, risk_notes

    @staticmethod
    def _video_content(
        project: ContentProject,
        brand: Brand,
        product: Product,
        fact_text: str,
        selling_points: str,
    ) -> dict:
        is_sixty_seconds = project.content_type == ContentType.short_video_60s
        end_second = 60 if is_sixty_seconds else 30
        middle_end = 48 if is_sixty_seconds else 20
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
    ) -> dict:
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
            segments = [
                {"stage": "产品亮相", "script": greeting},
                {"stage": "核心卖点", "script": f"它值得关注的特点是{selling_points}。"},
                {"stage": "事实依据", "script": fact_statement},
                {
                    "stage": "购买提示",
                    "script": f"规格为{product.specification or '以实际商品页为准'}，"
                    f"储存建议是{product.storage_method or '请按商品说明储存'}。",
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
    ) -> dict:
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
        return {
            "format": "social_post",
            "headline": f"今天认真介绍一份来自{product.origin or '真实产地'}的{product.name}",
            "body": (
                f"{brand.name}希望把产品信息讲清楚：它的主要特点是{selling_points}。"
                f"根据已审核资料，{fact_text}。"
            ),
            "cta": "你还想了解哪项产品信息？欢迎留言，我们会继续补充可核实的答案。",
            "hashtags": [f"#{product.name}", "#农产品", "#产地故事"],
        }

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[ContextSource],
    ) -> GenerationResult:
        started = time.perf_counter()
        fact_text, selling_points, citations, risk_notes = self._common_context(
            brand, product, sources
        )
        if project.content_type in {
            ContentType.short_video_30s,
            ContentType.short_video_60s,
        }:
            content = self._video_content(project, brand, product, fact_text, selling_points)
        elif project.content_type in {
            ContentType.livestream_opening,
            ContentType.livestream_product_pitch,
            ContentType.livestream_interaction,
        }:
            content = self._livestream_content(project, brand, product, fact_text, selling_points)
        else:
            content = self._text_content(project, brand, product, fact_text, selling_points)
        content["risk_notes"] = risk_notes
        content["citations"] = citations
        return GenerationResult(
            content=content,
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
        )


def get_ai_provider() -> AIProvider:
    return DeterministicProvider()
