"""
Embedding providers package.
"""

from app.services.search.embeddings.base import (
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    cosine_similarity,
)
from app.services.search.embeddings.factory import (
    get_embedding_provider,
    set_embedding_provider,
)
from app.services.search.embeddings.gemini import GeminiEmbeddingProvider
from app.services.search.embeddings.mock import MockEmbeddingProvider

__all__ = [
    "EmbeddingError",
    "EmbeddingUnavailableError",
    "EmbeddingAuthError",
    "EmbeddingProvider",
    "cosine_similarity",
    "GeminiEmbeddingProvider",
    "MockEmbeddingProvider",
    "get_embedding_provider",
    "set_embedding_provider",
]
