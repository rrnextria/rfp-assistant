from __future__ import annotations

import json
import sys

from pydantic import BaseModel

from common.config import get_settings

# Ensure adapters package is importable
sys.path.insert(0, "/home/ravi/git/rfp-assistant/services/adapters")

from base import AdapterError, ModelAdapter  # noqa: E402


class TenantConfig(BaseModel):
    preferred_provider: str = "claude"
    fallback_provider: str | None = "ollama"
    model_name: str | None = None


def _get_adapter(provider: str, model_name: str | None = None) -> ModelAdapter:
    """Instantiate the adapter for the given provider."""
    from claude import ClaudeAdapter
    from gemini import GeminiAdapter
    from ollama import OllamaAdapter

    settings = get_settings()
    if provider == "claude":
        return ClaudeAdapter(
            model=model_name or "claude-3-5-sonnet-20241022",
            api_key=settings.anthropic_api_key,
        )
    elif provider == "gemini":
        return GeminiAdapter(
            model=model_name or "gemini-1.5-pro",
            api_key=settings.google_api_key,
        )
    elif provider == "ollama":
        return OllamaAdapter(
            base_url=settings.ollama_base_url,
            model=model_name or "llama3.2",
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


def select(tenant_config: TenantConfig) -> ModelAdapter:
    return _get_adapter(tenant_config.preferred_provider, tenant_config.model_name)


async def generate_with_fallback(
    adapter: ModelAdapter,
    fallback_adapter: ModelAdapter | None,
    prompt: str,
    context: list[str],
):
    try:
        return await adapter.generate(prompt, context)
    except AdapterError:
        if fallback_adapter:
            return await fallback_adapter.generate(prompt, context)
        raise


def load_tenant_config(user: dict) -> TenantConfig:
    """Load tenant config from user record (tenant_config JSONB)."""
    tc = user.get("tenant_config") or {}
    if isinstance(tc, str):
        tc = json.loads(tc)
    return TenantConfig(**{k: v for k, v in tc.items() if k in TenantConfig.model_fields})
