"""
Google Gemini embedding provider adapter using the official google-genai SDK.
Generates vector representations using gemini-embedding-2.
"""

import asyncio
import logging
from typing import Any, List, Optional, Tuple

from app.core.config import settings
from app.services.search.embeddings.base import (
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingUnavailableError,
)

logger = logging.getLogger("doc_intel.search.embeddings.gemini")


def _mask_key(msg: str, key: str) -> str:
    """Ensure API key never leaks in exception strings or logs."""
    if not key or len(key) < 6:
        return msg
    return msg.replace(key, f"{key[:3]}...{key[-3:]}")


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Embedding provider utilizing the official Google GenAI SDK (client.models.embed_content).
    Default model: gemini-embedding-2 (768 dimensions).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_version: Optional[str] = None,
        dimension: Optional[int] = None,
        client: Optional[Any] = None,
    ):
        self._api_key = (api_key or getattr(settings, "GEMINI_API_KEY", "")).strip()
        default_model = (
            getattr(settings, "GEMINI_EMBEDDING_MODEL", None)
            or getattr(settings, "EMBEDDING_MODEL", None)
            or "gemini-embedding-2"
        )
        self._model = (model or default_model).strip()
        self._api_version = (api_version or getattr(settings, "GOOGLE_GENAI_API_VERSION", "v1beta")).strip()
        self._dimension = dimension or getattr(settings, "EMBEDDING_DIMENSION", 768)
        self._client = client

        if self._client is None and self._api_key:
            try:
                from google import genai
                from google.genai import types

                self._client = genai.Client(
                    api_key=self._api_key,
                    http_options=types.HttpOptions(
                        api_version=self._api_version,
                        retry_options={"attempts": 1},
                    ),
                )
            except Exception as exc:
                logger.warning("Failed to initialize Gemini GenAI client for embeddings: %s", _mask_key(str(exc), self._api_key))
                self._client = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def check_availability(self) -> Tuple[bool, str]:
        if not self._api_key:
            return False, "GEMINI_API_KEY is not configured in environment."
        if self._client is None:
            return False, "Gemini client could not be initialized."
        return True, f"Gemini embedding model '{self._model}' ({self._dimension}-dim) is active."

    def _embed_sync(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
        if not text or not text.strip():
            return [0.0] * self._dimension

        if not self._client:
            raise EmbeddingUnavailableError("Gemini client is not initialized.")

        try:
            from google.genai import types

            config = types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self._dimension,
            )
            response = self._client.models.embed_content(
                model=self._model,
                contents=text,
                config=config,
            )
            if response.embeddings and len(response.embeddings) > 0:
                values = response.embeddings[0].values
                return list(values)
            raise EmbeddingError("Gemini returned empty embedding response.")
        except Exception as exc:
            safe_msg = _mask_key(str(exc), self._api_key)
            lower_err = safe_msg.lower()
            if "auth" in lower_err or "permission" in lower_err or "api_key" in lower_err or "403" in lower_err:
                raise EmbeddingAuthError(f"Gemini authentication failed: {safe_msg}") from exc
            if "connect" in lower_err or "network" in lower_err or "unavailable" in lower_err:
                raise EmbeddingUnavailableError(f"Gemini embedding service is unreachable: {safe_msg}") from exc
            raise EmbeddingError(f"Gemini embedding error: {safe_msg}") from exc

    async def embed_text(self, text: str) -> List[float]:
        """Embed single document text with RETRIEVAL_DOCUMENT task type."""
        return await asyncio.to_thread(self._embed_sync, text, "RETRIEVAL_DOCUMENT")

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed list of document texts concurrently or sequentially."""
        results: List[List[float]] = []
        for text in texts:
            vec = await asyncio.to_thread(self._embed_sync, text, "RETRIEVAL_DOCUMENT")
            results.append(vec)
        return results

    async def embed_query(self, query: str) -> List[float]:
        """Embed search query with RETRIEVAL_QUERY task type."""
        return await asyncio.to_thread(self._embed_sync, query, "RETRIEVAL_QUERY")
