"""
Abstract base class, data transfer models, and exceptions for LLM providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def mask_secret(text: str, secret: Optional[str]) -> str:
    """
    Safely redacts secrets from exception messages and log strings.
    Guarantees no raw API key is ever displayed or logged.
    """
    if not secret or not text:
        return text
    return text.replace(secret, "[REDACTED_API_KEY]")


class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class LLMAuthenticationError(LLMProviderError):
    """Raised on authentication or permission failure (e.g. invalid API key, 401/403)."""
    pass


class LLMRateLimitError(LLMProviderError):
    """Raised when rate limits or quotas are exceeded (HTTP 429 / RESOURCE_EXHAUSTED)."""
    pass


class LLMServiceUnavailableError(LLMProviderError):
    """Raised when the LLM service is temporarily unavailable or overloaded (HTTP 503)."""
    pass


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM generation request times out."""
    pass


class LLMMalformedResponseError(LLMProviderError):
    """Raised when the LLM produces empty, truncated, or unparseable JSON output."""
    pass


class LLMConfigurationError(LLMProviderError):
    """Raised when LLM configuration is missing, invalid, or LLM_ENABLED is false."""
    pass


@dataclass
class LLMUsageMetadata:
    """Token consumption and usage telemetry for an LLM interaction."""
    prompt_tokens: Optional[int] = None
    candidates_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMStructuredResponse:
    """Structured response object containing parsed JSON and operational telemetry."""
    raw_text: str
    parsed_json: Dict[str, Any]
    model: str
    latency_ms: float
    usage: Optional[LLMUsageMetadata] = None


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers supporting structured JSON generation.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider, e.g. 'gemini'."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the configured model."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        json_schema: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> LLMStructuredResponse:
        """
        Asynchronously generates a structured JSON response matching json_schema.
        Must run non-blocking without monopolizing the event loop.
        """
        pass

    @abstractmethod
    def generate_structured_sync(
        self,
        prompt: str,
        json_schema: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> LLMStructuredResponse:
        """
        Synchronously generates a structured JSON response matching json_schema.
        """
        pass
