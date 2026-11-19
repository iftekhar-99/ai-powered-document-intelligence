"""
Factory for creating and accessing the configured embedding provider.
"""

from typing import Optional

from app.core.config import settings
from app.services.search.embeddings.base import EmbeddingProvider
from app.services.search.embeddings.gemini import GeminiEmbeddingProvider
from app.services.search.embeddings.mock import MockEmbeddingProvider

_active_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    """
    Returns the active embedding provider based on environment configuration or override.
    """
    global _active_provider
    if _active_provider is not None:
        return _active_provider

    provider_name = getattr(settings, "EMBEDDING_PROVIDER", "gemini").lower().strip()
    model = (
        getattr(settings, "GEMINI_EMBEDDING_MODEL", None)
        or getattr(settings, "EMBEDDING_MODEL", None)
        or "gemini-embedding-2"
    ).strip()
    dimension = getattr(settings, "EMBEDDING_DIMENSION", 768)

    if provider_name == "mock":
        return MockEmbeddingProvider(dimension=dimension)
    elif provider_name == "gemini":
        return GeminiEmbeddingProvider(model=model, dimension=dimension)
    else:
        # If explicit non-mock provider is configured, default to Gemini if API key exists
        gemini_key = getattr(settings, "GEMINI_API_KEY", "")
        if gemini_key:
            return GeminiEmbeddingProvider(model=model, dimension=dimension)
        return MockEmbeddingProvider(dimension=dimension)



def set_embedding_provider(provider: Optional[EmbeddingProvider]) -> None:
    """Explicitly set or reset the embedding provider (useful in test suites)."""
    global _active_provider
    _active_provider = provider
