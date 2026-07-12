import time
from dataclasses import dataclass
from typing import Protocol

from app.models import Brand, ContentProject, KnowledgeSource, Product

PROMPT_NAME = "agricultural-content-script"
PROMPT_VERSION = "1.0.0"


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
        sources: list[KnowledgeSource],
    ) -> GenerationResult: ...


class DeterministicProvider:
    """Offline provider for tests and zero-cost demos.

    It is deliberately transparent: this provider composes verified facts rather
    than pretending to be a trained model.
    """

    name = "mock"
    model = "deterministic-v1"

    def generate_script(
        self,
        project: ContentProject,
        brand: Brand,
        product: Product,
        sources: list[KnowledgeSource],
    ) -> GenerationResult:
        started = time.perf_counter()
        facts = [source.content.strip() for source in sources if source.content.strip()]
        fact_text = "；".join(facts[:3]) or "请先补充并审核产品资料"
        selling_points = "、".join(product.selling_points) or "真实产地与产品特色"
        hook = f"你知道来自{product.origin or '产地'}的{product.name}有什么特别吗？"
        body = (
            f"这是{brand.name}带来的{product.name}。"
            f"它的主要特点是{selling_points}。"
            f"根据已审核资料：{fact_text}。"
        )
        if product.price_display:
            body += f"当前展示信息为{product.price_display}。"
        cta = "想了解更多真实生产信息，欢迎在评论区留言。"
        content = {
            "title_options": [
                f"{product.name}真实产地故事",
                f"一分钟认识{product.name}",
                f"{brand.name}今天带你看好农产",
            ],
            "hook": hook,
            "script": f"{hook}{body}{cta}",
            "shots": [
                {"seconds": "0-3", "visual": "产品与产地快速亮相", "voiceover": hook},
                {"seconds": "3-20", "visual": "产品细节和生产场景", "voiceover": body},
                {"seconds": "20-30", "visual": "品牌与互动提示", "voiceover": cta},
            ],
            "cta": cta,
            "risk_notes": [f"禁止使用：{claim}" for claim in product.prohibited_claims],
            "citations": [
                {
                    "source_id": source.id,
                    "label": source.citation_label or source.title,
                }
                for source in sources
            ],
        }
        return GenerationResult(
            content=content,
            latency_ms=max(1, int((time.perf_counter() - started) * 1000)),
        )


def get_ai_provider() -> AIProvider:
    return DeterministicProvider()
