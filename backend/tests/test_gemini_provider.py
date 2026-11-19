"""
Unit tests for Gemini Provider Adapter, Error Handling, and Factory.
All tests use strictly MOCKED responses — zero real API calls are performed.

Covers:
9.  Invalid JSON response handling (LLMMalformedResponseError).
10. Missing provider configuration (LLMConfigurationError).
11. Disabled LLM configuration (LLMConfigurationError).
12. Mocked Gemini successful structured response (async & sync).
13. Mocked Gemini 429 response (LLMRateLimitError).
14. Mocked Gemini 503 response (LLMServiceUnavailableError).
15. Mocked authentication failure (LLMAuthenticationError).
16. Mocked timeout (LLMTimeoutError).
17. Empty response handling (LLMMalformedResponseError).
18. Credential masking (no API key leakage).
"""

from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services.extraction.providers import (
    GeminiProvider,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMMalformedResponseError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
    get_llm_provider,
    mask_secret,
)


@pytest.fixture
def mock_client():
    """Returns a mock google-genai Client with mocked interactions."""
    client = MagicMock()
    client.interactions = MagicMock()
    return client


def test_9_invalid_json_handling(mock_client):
    """Verify that malformed JSON response raises LLMMalformedResponseError."""
    mock_interaction = MagicMock()
    mock_interaction.output_text = "THIS IS NOT JSON CONTENT"
    mock_client.interactions.create.return_value = mock_interaction

    provider = GeminiProvider(api_key="mock_key", client=mock_client)
    schema = {"type": "object", "properties": {"invoice_number": {"type": "string"}}}

    with pytest.raises(LLMMalformedResponseError) as exc_info:
        provider.generate_structured_sync(prompt="Extract data", json_schema=schema)

    assert "Failed to parse Gemini output as JSON" in str(exc_info.value)


def test_10_missing_provider_configuration(monkeypatch):
    """Instantiating GeminiProvider without an API key raises LLMConfigurationError."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    with pytest.raises(LLMConfigurationError) as exc_info:
        GeminiProvider(api_key="")

    assert "GEMINI_API_KEY is missing or empty" in str(exc_info.value)


def test_11_disabled_llm_configuration(monkeypatch):
    """get_llm_provider raises LLMConfigurationError when LLM_ENABLED is False."""
    monkeypatch.setattr(settings, "LLM_ENABLED", False)

    with pytest.raises(LLMConfigurationError) as exc_info:
        get_llm_provider()

    assert "AI invoice extraction is disabled in configuration" in str(exc_info.value)


def test_12_mocked_gemini_successful_response(mock_client):
    """Verify structured response parsing, latency, model, and token usage."""
    mock_interaction = MagicMock()
    mock_interaction.output_text = (
        '{"invoice_number": "INV-2026-TEST", "total": 1250.50, "currency": "USD"}'
    )
    mock_interaction.usage = MagicMock(
        input_tokens=150,
        output_tokens=45,
        total_tokens=195,
    )
    mock_client.interactions.create.return_value = mock_interaction

    provider = GeminiProvider(
        api_key="mock_key",
        model="gemini-flash-lite-latest",
        client=mock_client,
    )
    schema = {
        "type": "object",
        "properties": {
            "invoice_number": {"type": "string"},
            "total": {"type": "number"},
            "currency": {"type": "string"},
        },
    }

    response = provider.generate_structured_sync(
        prompt="Extract invoice",
        json_schema=schema,
        timeout=15.0,
    )

    assert response.model == "gemini-flash-lite-latest"
    assert response.parsed_json["invoice_number"] == "INV-2026-TEST"
    assert response.parsed_json["total"] == 1250.50
    assert response.parsed_json["currency"] == "USD"
    assert response.latency_ms > 0
    assert response.usage is not None
    assert response.usage.prompt_tokens == 150
    assert response.usage.candidates_tokens == 45
    assert response.usage.total_tokens == 195

    # Verify call signature passed to interactions.create
    mock_client.interactions.create.assert_called_once_with(
        model="gemini-flash-lite-latest",
        input="Extract invoice",
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
        timeout=15.0,
    )


@pytest.mark.asyncio
async def test_12_mocked_gemini_successful_response_async(mock_client):
    """Verify asynchronous invocation of generate_structured."""
    mock_interaction = MagicMock()
    mock_interaction.output_text = '{"status": "ok"}'
    mock_interaction.usage = None
    mock_client.interactions.create.return_value = mock_interaction

    provider = GeminiProvider(api_key="mock_key", client=mock_client)
    res = await provider.generate_structured("test", {"type": "object"})
    assert res.parsed_json == {"status": "ok"}


def test_13_mocked_gemini_429_response(mock_client):
    """Verify HTTP 429 / RESOURCE_EXHAUSTED maps to LLMRateLimitError."""
    mock_err = Exception("429 Resource has been exhausted (e.g. check quota)")
    mock_err.code = 429
    mock_client.interactions.create.side_effect = mock_err

    provider = GeminiProvider(api_key="mock_key", client=mock_client)

    with pytest.raises(LLMRateLimitError) as exc_info:
        provider.generate_structured_sync("prompt", {})

    assert exc_info.value.status_code == 429
    assert "quota / rate limit exceeded" in str(exc_info.value)


def test_14_mocked_gemini_503_response(mock_client):
    """Verify HTTP 503 / Service Unavailable maps to LLMServiceUnavailableError."""
    mock_err = Exception("503 The model is overloaded. Please try again later.")
    mock_err.code = 503
    mock_client.interactions.create.side_effect = mock_err

    provider = GeminiProvider(api_key="mock_key", client=mock_client)

    with pytest.raises(LLMServiceUnavailableError) as exc_info:
        provider.generate_structured_sync("prompt", {})

    assert exc_info.value.status_code == 503
    assert "temporarily unavailable" in str(exc_info.value)


def test_15_mocked_authentication_failure(mock_client):
    """Verify HTTP 401/403 or invalid API key maps to LLMAuthenticationError."""
    mock_err = Exception("401 API_KEY_INVALID: User not authorized")
    mock_err.code = 401
    mock_client.interactions.create.side_effect = mock_err

    provider = GeminiProvider(api_key="mock_key", client=mock_client)

    with pytest.raises(LLMAuthenticationError) as exc_info:
        provider.generate_structured_sync("prompt", {})

    assert exc_info.value.status_code == 401
    assert "authentication or permission failure" in str(exc_info.value)


def test_16_mocked_timeout(mock_client):
    """Verify timeout exception maps to LLMTimeoutError."""
    mock_client.interactions.create.side_effect = TimeoutError("Client request timed out")

    provider = GeminiProvider(api_key="mock_key", client=mock_client)

    with pytest.raises(LLMTimeoutError) as exc_info:
        provider.generate_structured_sync("prompt", {}, timeout=5.0)

    assert exc_info.value.status_code == 408
    assert "timed out after 5.0s" in str(exc_info.value)


def test_17_empty_response_handling(mock_client):
    """Empty response raises LLMMalformedResponseError."""
    mock_interaction = MagicMock()
    mock_interaction.output_text = ""
    mock_interaction.steps = []
    mock_client.interactions.create.return_value = mock_interaction

    provider = GeminiProvider(api_key="mock_key", client=mock_client)

    with pytest.raises(LLMMalformedResponseError) as exc_info:
        provider.generate_structured_sync("prompt", {})

    assert "Received empty response" in str(exc_info.value)


def test_18_credential_masking():
    """Verify that credentials are never reflected in error messages or logs."""
    fake_secret = "AIzaSyFakeSecretKey9988776655"
    raw_error_message = f"Error connecting with key {fake_secret}: Unauthorized"

    masked = mask_secret(raw_error_message, fake_secret)
    assert fake_secret not in masked
    assert "[REDACTED_API_KEY]" in masked

    # Provider should sanitize exception containing secret
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = Exception(
        f"403 Invalid key: {fake_secret}"
    )

    provider = GeminiProvider(api_key=fake_secret, client=mock_client)
    with pytest.raises(LLMAuthenticationError) as exc_info:
        provider.generate_structured_sync("prompt", {})

    err_str = str(exc_info.value)
    assert fake_secret not in err_str
    assert "[REDACTED_API_KEY]" in err_str


def test_factory_unsupported_provider(monkeypatch):
    """Factory raises LLMConfigurationError for unknown providers."""
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    with pytest.raises(LLMConfigurationError) as exc_info:
        get_llm_provider(provider_name="unsupported_provider")

    assert "Unsupported LLM provider 'unsupported_provider'" in str(exc_info.value)
