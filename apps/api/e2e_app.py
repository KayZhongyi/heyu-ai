"""Browser-E2E application overrides.

This module is intentionally separate from the production entrypoint. It gives
the browser suite one deterministic project that returns invalid provider
output, while every other project still uses the normal zero-cost provider.
"""

import app.services as services
from app.ai import DeterministicProvider, GenerationResult
from app.main import app as application


class BrowserE2EProvider:
    name = "browser-e2e"
    model = "deterministic-invalid-citation-v1"

    def __init__(self) -> None:
        self._fallback = DeterministicProvider()

    def generate_script(
        self,
        project,
        brand,
        product,
        sources,
        supply=None,
        farmer_evidence=None,
        brief=None,
    ):
        if project.title.startswith("[E2E invalid citation]"):
            return GenerationResult(
                content={
                    "format": "social_post",
                    "headline": "This output must never become content.",
                    "body": "The provider intentionally omitted provenance.",
                    "cta": "Do not publish.",
                    "hashtags": [],
                    "citations": [],
                    "risk_notes": [],
                },
                latency_ms=1,
            )
        return self._fallback.generate_script(
            project,
            brand,
            product,
            sources,
            supply,
            farmer_evidence,
            brief,
        )


services.get_ai_provider = lambda: BrowserE2EProvider()

app = application
