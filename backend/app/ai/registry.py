"""Provider registry.

Resolves the provider *name* configured in settings to an implementation, so
business code never imports a vendor SDK (docs/04_TECH_ARCHITECTURE.md).
"""

from __future__ import annotations

from app.ai.mock import MockAIProvider, MockOCRProvider
from app.ai.openai_provider import OpenAIProvider
from app.ai.providers import AIProvider, OCRProvider, ProviderNotFound
from app.config import settings

_AI_PROVIDERS: dict[str, type] = {
    "mock": MockAIProvider,
    "openai": OpenAIProvider,
    # "anthropic": AnthropicProvider,
}

_OCR_PROVIDERS: dict[str, type] = {
    "mock": MockOCRProvider,
    # "paddle": PaddleOCRProvider,
    # "cloud": CloudOCRProvider,
}


def get_ai_provider(name: str | None = None) -> AIProvider:
    key = (name or settings.ai_provider).lower()
    cls = _AI_PROVIDERS.get(key)
    if cls is None:
        raise ProviderNotFound(
            f"未知的 AI provider: {key!r}（可用：{sorted(_AI_PROVIDERS)}）"
        )
    return cls()


def get_ocr_provider(name: str | None = None) -> OCRProvider:
    key = (name or settings.ocr_provider).lower()
    cls = _OCR_PROVIDERS.get(key)
    if cls is None:
        raise ProviderNotFound(
            f"未知的 OCR provider: {key!r}（可用：{sorted(_OCR_PROVIDERS)}）"
        )
    return cls()
