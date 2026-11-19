"""
Provider factory for initializing LLM providers based on application configuration.
"""

from typing import Any, Optional

from app.core.config import settings
from app.services.extraction.providers.base import (
    LLMConfigurationError,
    LLMProvider,
)
from app.services.extraction.providers.gemini import GeminiProvider


def get_llm_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    api_version: Optional[str] = None,
    timeout: Optional[float] = None,
    client: Optional[Any] = None,
) -> LLMProvider:
    """
    Factory that instantiates and returns the configured LLMProvider.

    Enforces:
    1. Verifies that LLM_ENABLED is True.
    2. Identifies the designated provider (defaults to settings.LLM_PROVIDER).
    3. Initializes the corresponding provider adapter (currently GeminiProvider).
    4. Raises LLMConfigurationError if disabled, unconfigured, or unsupported.

    Args:
        provider_name: Override for provider name (e.g. 'gemini').
        api_key: Override for API key.
        model: Override for model name.
        api_version: Override for API version.
        timeout: Override for request timeout.
        client: Pre-instantiated SDK client (primarily for testing/mocking).

    Returns:
        An instance conforming to LLMProvider.

    Raises:
        LLMConfigurationError: If LLM is disabled or provider is invalid/unsupported.
    """
    if not settings.LLM_ENABLED:
        raise LLMConfigurationError(
            "AI invoice extraction is disabled in configuration (LLM_ENABLED=false)."
        )

    resolved_provider = (provider_name or settings.LLM_PROVIDER or "").strip().lower()

    if not resolved_provider:
        raise LLMConfigurationError(
            "No LLM provider configured. Set LLM_PROVIDER in the root .env file."
        )

    if resolved_provider == "gemini":
        return GeminiProvider(
            api_key=api_key,
            model=model,
            api_version=api_version,
            timeout=timeout,
            client=client,
        )

    raise LLMConfigurationError(
        f"Unsupported LLM provider '{resolved_provider}'. Currently supported providers: ['gemini']."
    )
