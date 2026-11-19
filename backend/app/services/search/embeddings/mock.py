"""
Deterministic mock embedding provider for tests and offline development.
Generates unit-normalized float vectors with semantic correlation based on word token hashing.
"""

import hashlib
import math
import re
from typing import List, Tuple

from app.services.search.embeddings.base import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """
    Mock embedding provider for reliable, hermetic testing.
    Produces deterministic vectors where shared tokens result in higher cosine similarity.
    """

    def __init__(
        self,
        dimension: int = 768,
        model_name: str = "mock-embedding-v1",
        is_available: bool = True,
    ):
        self._dimension = dimension
        self._model_name = model_name
        self._is_available = is_available

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def check_availability(self) -> Tuple[bool, str]:
        if not self._is_available:
            return False, "Mock embedding provider explicitly disabled for test."
        return True, "Mock embedding provider is active (offline/hermetic mode)."


    def _generate_vector(self, text: str) -> List[float]:
        vec = [0.0] * self._dimension
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            # Baseline unit vector
            vec[0] = 1.0
            return vec

        for token in tokens:
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self._dimension
            sign = 1.0 if ((h >> 8) % 2 == 0) else -1.0
            vec[idx] += sign

        # Unit-normalize vector
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        else:
            vec[0] = 1.0
        return vec

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]

    async def embed_query(self, query: str) -> List[float]:
        return self._generate_vector(query)
