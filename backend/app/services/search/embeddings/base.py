"""
Base abstraction and vector similarity utilities for Embedding Providers.
"""

from abc import ABC, abstractmethod
import math
from typing import List, Tuple


class EmbeddingError(Exception):
    """Base exception for vector embedding operations."""
    pass


class EmbeddingUnavailableError(EmbeddingError):
    """Raised when the embedding provider cannot be reached or is offline."""
    pass


class EmbeddingAuthError(EmbeddingError):
    """Raised when API credentials for the embedding provider are invalid."""
    pass


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    Computes cosine similarity between two float vectors.
    Returns float in range [-1.0, 1.0].
    """
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class EmbeddingProvider(ABC):
    """Abstract base class for vector embedding generation."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'gemini', 'mock')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier (e.g. 'text-embedding-004')."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality (e.g. 768)."""
        pass

    @abstractmethod
    def check_availability(self) -> Tuple[bool, str]:
        """
        Check if the embedding service is currently usable.
        Returns (is_available, status_message).
        """
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of document texts."""
        pass

    async def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single document text."""
        res = await self.embed_texts([text])
        return res[0] if res else [0.0] * self.dimension

    @abstractmethod
    async def embed_query(self, query: str) -> List[float]:
        """Generate embedding vector for a search query."""
        pass
