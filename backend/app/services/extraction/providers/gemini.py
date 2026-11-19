"""
Gemini provider adapter implementing structured JSON extraction using the
official google-genai SDK (v1beta Interactions API).
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from app.services.extraction.providers.base import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMMalformedResponseError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMStructuredResponse,
    LLMTimeoutError,
    LLMUsageMetadata,
    mask_secret,
)

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    Adapter for Google Gemini using the official google-genai SDK and
    the Gemini Interactions API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout: Optional[float] = None,
        client: Optional[Any] = None,
    ):
        """
        Initialize the Gemini provider.

        Args:
            api_key: Google AI Studio API key. Defaults to settings.GEMINI_API_KEY.
            model: Gemini model identifier. Defaults to settings.GEMINI_MODEL.
            api_version: Developer API version ('v1beta'). Defaults to settings.GOOGLE_GENAI_API_VERSION.
            timeout: Default request timeout in seconds. Defaults to settings.LLM_TIMEOUT_SECONDS.
            client: Pre-instantiated genai.Client instance (primarily for mocking/testing).
        """
        self._api_key = (api_key or getattr(settings, "GEMINI_API_KEY", "")).strip()
        self._model = (model or getattr(settings, "GEMINI_MODEL", "gemini-flash-lite-latest")).strip()
        self._api_version = (
            api_version or getattr(settings, "GOOGLE_GENAI_API_VERSION", "v1beta")
        ).strip()
        self._default_timeout = float(timeout or getattr(settings, "LLM_TIMEOUT_SECONDS", 120.0))

        if client is not None:
            self._client = client
        else:
            if not self._api_key:
                raise LLMConfigurationError(
                    "GEMINI_API_KEY is missing or empty. Please configure GEMINI_API_KEY in the root .env file."
                )

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
                safe_err = mask_secret(str(exc), self._api_key)
                raise LLMConfigurationError(
                    f"Failed to initialize google-genai client: {safe_err}"
                ) from exc

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def generate_structured_sync(
        self,
        prompt: str,
        json_schema: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> LLMStructuredResponse:
        """
        Synchronously generates a structured JSON output conforming to json_schema
        using the Gemini Interactions API.
        """
        effective_timeout = float(timeout) if timeout is not None else self._default_timeout
        start_time = time.perf_counter()

        logger.debug(
            "Invoking Gemini Interactions API: model=%s, api_version=%s, timeout=%ss",
            self._model,
            self._api_version,
            effective_timeout,
        )

        try:
            interaction = self._client.interactions.create(
                model=self._model,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": json_schema,
                },
                timeout=effective_timeout,
            )
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self._handle_gemini_exception(exc, effective_timeout, latency_ms)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return self._process_interaction_response(interaction, latency_ms)

    async def generate_structured(
        self,
        prompt: str,
        json_schema: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> LLMStructuredResponse:
        """
        Asynchronously generates structured JSON output via thread pool offloading,
        ensuring strict non-blocking execution while preserving the exact proven
        Interactions API invocation signature.
        """
        return await asyncio.to_thread(
            self.generate_structured_sync,
            prompt,
            json_schema,
            timeout,
        )

    def _process_interaction_response(
        self,
        interaction: Any,
        latency_ms: float,
    ) -> LLMStructuredResponse:
        """Extracts text, parses JSON, and builds the structured response payload."""
        output_text = None

        if hasattr(interaction, "output_text") and interaction.output_text:
            output_text = interaction.output_text
        elif hasattr(interaction, "steps") and interaction.steps:
            for step in interaction.steps:
                contents = getattr(step, "content", []) or []
                for item in contents:
                    if getattr(item, "type", None) == "text":
                        output_text = getattr(item, "text", "")
                        if output_text:
                            break
                if output_text:
                    break

        if output_text is None and isinstance(interaction, str):
            output_text = interaction

        if output_text is None or not str(output_text).strip():
            raise LLMMalformedResponseError(
                f"Received empty response from Gemini model '{self._model}'",
                details={"model": self._model, "latency_ms": latency_ms},
            )

        cleaned_text = str(output_text).strip()

        # Strip accidental markdown code blocks (e.g. ```json ... ```)
        if cleaned_text.startswith("```"):
            lines = cleaned_text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_text = "\n".join(lines).strip()

        try:
            parsed_json = json.loads(cleaned_text)
        except json.JSONDecodeError as jde:
            safe_err = mask_secret(str(jde), self._api_key)
            raise LLMMalformedResponseError(
                f"Failed to parse Gemini output as JSON: {safe_err}",
                details={
                    "raw_text": cleaned_text[:500],
                    "model": self._model,
                    "latency_ms": latency_ms,
                },
            ) from jde

        # Extract usage metadata where available
        usage_meta: Optional[LLMUsageMetadata] = None
        if hasattr(interaction, "usage") and interaction.usage:
            u = interaction.usage
            prompt_tokens = (
                getattr(u, "input_tokens", None)
                or getattr(u, "total_input_tokens", None)
            )
            cand_tokens = (
                getattr(u, "output_tokens", None)
                or getattr(u, "total_output_tokens", None)
            )
            total_tokens = getattr(u, "total_tokens", None)
            usage_meta = LLMUsageMetadata(
                prompt_tokens=prompt_tokens,
                candidates_tokens=cand_tokens,
                total_tokens=total_tokens,
            )

        return LLMStructuredResponse(
            raw_text=cleaned_text,
            parsed_json=parsed_json,
            model=self._model,
            latency_ms=latency_ms,
            usage=usage_meta,
        )

    def _handle_gemini_exception(
        self,
        exc: Exception,
        effective_timeout: float,
        latency_ms: float,
    ) -> None:
        """
        Categorizes exceptions from the google-genai SDK into domain-specific exceptions.
        Guarantees API credentials are never logged or exposed.
        """
        status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        err_str = mask_secret(str(exc), self._api_key)
        err_lower = err_str.lower()
        exc_type = type(exc).__name__

        # 1. Rate Limit / Quota Exceeded (429)
        if (
            status_code == 429
            or "429" in err_str
            or "resource_exhausted" in err_lower
            or "quota" in err_lower
        ):
            raise LLMRateLimitError(
                f"Gemini quota / rate limit exceeded (429): {err_str}",
                status_code=429,
                details={"model": self._model, "latency_ms": latency_ms},
            ) from exc

        # 2. Service Unavailable / Capacity Overload (503)
        if (
            status_code == 503
            or "503" in err_str
            or "service_unavailable" in err_lower
            or "high demand" in err_lower
        ):
            raise LLMServiceUnavailableError(
                f"Gemini service temporarily unavailable (503): {err_str}",
                status_code=503,
                details={"model": self._model, "latency_ms": latency_ms},
            ) from exc

        # 3. Authentication & Permission Errors (401, 403)
        if (
            status_code in (401, 403)
            or "401" in err_str
            or "403" in err_str
            or "unauthenticated" in err_lower
            or "invalid_api_key" in err_lower
            or "permission_denied" in err_lower
        ):
            raise LLMAuthenticationError(
                f"Gemini authentication or permission failure: {err_str}",
                status_code=status_code or 401,
                details={"model": self._model, "latency_ms": latency_ms},
            ) from exc

        # 4. Request Timeout
        if (
            isinstance(exc, (TimeoutError, asyncio.TimeoutError))
            or "timeout" in err_lower
            or "timed out" in err_lower
            or "timeouterror" in exc_type.lower()
        ):
            raise LLMTimeoutError(
                f"Gemini request timed out after {effective_timeout}s: {err_str}",
                status_code=408,
                details={
                    "model": self._model,
                    "timeout": effective_timeout,
                    "latency_ms": latency_ms,
                },
            ) from exc

        # 5. Generic / Unclassified Provider Failure
        raise LLMProviderError(
            f"Gemini API request failed ({exc_type}): {err_str}",
            status_code=status_code,
            details={"model": self._model, "latency_ms": latency_ms},
        ) from exc
