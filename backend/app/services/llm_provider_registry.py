"""Safe LLM provider registry data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    adapter: str
    base_url: str | None
    default_model: str
    models: list[str]
    requires_api_key: bool
    implemented: bool


def provider_registry() -> dict[str, ProviderDefinition]:
    """Return provider metadata without API keys."""
    return {
        "openai": ProviderDefinition(
            id="openai",
            name="OpenAI",
            adapter="openai-compatible",
            base_url=settings.OPENAI_BASE_URL,
            default_model=settings.OPENAI_MODEL,
            models=[settings.OPENAI_MODEL, "gpt-4o-mini", "gpt-4o"],
            requires_api_key=True,
            implemented=True,
        ),
        "deepseek": ProviderDefinition(
            id="deepseek",
            name="DeepSeek",
            adapter="openai-compatible",
            base_url=settings.DEEPSEEK_BASE_URL,
            default_model=settings.DEEPSEEK_MODEL,
            models=[settings.DEEPSEEK_MODEL],
            requires_api_key=True,
            implemented=True,
        ),
        "qwen": ProviderDefinition(
            id="qwen",
            name="Qwen",
            adapter="openai-compatible",
            base_url=settings.QWEN_BASE_URL,
            default_model=settings.QWEN_MODEL,
            models=[settings.QWEN_MODEL],
            requires_api_key=True,
            implemented=True,
        ),
        "linkapi": ProviderDefinition(
            id="linkapi",
            name="LinkAPI",
            adapter="openai-compatible",
            base_url=settings.LINKAPI_BASE_URL,
            default_model=settings.LINKAPI_MODEL,
            models=[settings.LINKAPI_MODEL, "claude-sonnet-4-20250514", "gpt-4o-mini", "deepseek-chat"],
            requires_api_key=True,
            implemented=True,
        ),
        "ollama": ProviderDefinition(
            id="ollama",
            name="Ollama",
            adapter="openai-compatible",
            base_url=settings.OLLAMA_BASE_URL,
            default_model=settings.OLLAMA_MODEL,
            models=[settings.OLLAMA_MODEL],
            requires_api_key=False,
            implemented=True,
        ),
        "anthropic": ProviderDefinition(
            id="anthropic",
            name="Anthropic Claude",
            adapter="native",
            base_url=None,
            default_model=settings.ANTHROPIC_MODEL,
            models=[settings.ANTHROPIC_MODEL],
            requires_api_key=True,
            implemented=False,
        ),
        "gemini": ProviderDefinition(
            id="gemini",
            name="Google Gemini",
            adapter="openai-compatible",
            base_url=settings.GEMINI_BASE_URL,
            default_model=settings.GEMINI_MODEL,
            models=[settings.GEMINI_MODEL, "gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"],
            requires_api_key=True,
            implemented=True,
        ),
    }


def global_provider_credentials(provider_id: str) -> dict[str, Any]:
    """Return backend global fallback credentials for one provider."""
    credentials: dict[str, dict[str, Any]] = {
        "openai": {"api_key": settings.OPENAI_API_KEY, "base_url": settings.OPENAI_BASE_URL},
        "deepseek": {"api_key": settings.DEEPSEEK_API_KEY, "base_url": settings.DEEPSEEK_BASE_URL},
        "qwen": {"api_key": settings.QWEN_API_KEY, "base_url": settings.QWEN_BASE_URL},
        "linkapi": {"api_key": settings.LINKAPI_API_KEY, "base_url": settings.LINKAPI_BASE_URL},
        "ollama": {"api_key": "ollama", "base_url": settings.OLLAMA_BASE_URL},
        "anthropic": {"api_key": settings.ANTHROPIC_API_KEY, "base_url": None},
        "gemini": {"api_key": settings.GEMINI_API_KEY, "base_url": settings.GEMINI_BASE_URL},
    }
    return credentials.get(provider_id, {"api_key": None, "base_url": None})
