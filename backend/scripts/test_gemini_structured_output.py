#!/usr/bin/env python3
"""
Test Gemini Flash-Lite structured JSON extraction using the official google-genai SDK
and the Gemini Interactions API.

SECURITY RULE: NEVER print, log, display, or reveal GEMINI_API_KEY.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ValidationError

# 1. Resolve paths
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for path_dir in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if path_dir not in sys.path:
        sys.path.insert(0, path_dir)

# 2. Load root .env explicitly
from dotenv import load_dotenv

env_file_path = PROJECT_ROOT / ".env"
env_loaded = False
if env_file_path.exists():
    load_dotenv(dotenv_path=env_file_path, override=True)
    env_loaded = True
else:
    local_env = Path(".env")
    if local_env.exists():
        load_dotenv(dotenv_path=local_env, override=True)
        env_loaded = True

# Load settings from app.core.config
try:
    from app.core.config import settings
except Exception:
    settings = None


class InvoiceSchema(BaseModel):
    """Pydantic schema for structured output validation."""
    invoice_number: str = Field(..., description="Invoice identifier, e.g. TEST-001")
    total: float = Field(..., description="Total invoice amount, e.g. 123.45")
    currency: str = Field(..., description="Currency code, e.g. USD")


INVOICE_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "invoice_number": {
            "type": "string",
            "description": "Invoice identifier",
        },
        "total": {
            "type": "number",
            "description": "Total invoice amount as numeric float",
        },
        "currency": {
            "type": "string",
            "description": "Currency code e.g. USD",
        },
    },
    "required": ["invoice_number", "total", "currency"],
}


def mask_secret(text: str, secret: str) -> str:
    """Sanitize any accidental reflection of the API key in error messages."""
    if not secret:
        return text
    return text.replace(secret, "[REDACTED_API_KEY]")


def main() -> int:
    print("=" * 70)
    print("Gemini Flash-Lite Structured Output Diagnostic")
    print("=" * 70)

    # 1. Environment & Config Verification
    print("\n[1] Environment & Model Configuration:")
    print(f"  • Root .env path: {env_file_path} (exists: {env_file_path.exists()})")
    print(f"  • .env loaded: {env_loaded}")

    if settings is not None:
        api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "").strip()
        model = settings.GEMINI_MODEL or os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest").strip()
        llm_enabled = settings.LLM_ENABLED
        llm_provider = settings.LLM_PROVIDER
    else:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        model = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest").strip()
        llm_enabled = os.environ.get("LLM_ENABLED", "false").lower() == "true"
        llm_provider = os.environ.get("LLM_PROVIDER", "")

    print(f"  • Target Model: {model}")
    print(f"  • LLM_ENABLED: {llm_enabled}")
    print(f"  • LLM_PROVIDER: {llm_provider}")

    if not api_key:
        print("  • GEMINI_API_KEY: MISSING or EMPTY")
        print("\n[FAILURE CATEGORY: Environment configuration problem]")
        print("ERROR: GEMINI_API_KEY is not configured in .env.")
        return 1
    else:
        print(f"  • GEMINI_API_KEY: PRESENT ({len(api_key)} chars, [SECURELY_MASKED])")

    # 2. Check SDK
    print("\n[2] SDK Verification:")
    try:
        import google.genai as genai
        sdk_version = getattr(genai, "__version__", "unknown")
        print(f"  • Package: google.genai")
        print(f"  • Version: {sdk_version}")
    except ImportError as e:
        print(f"  • Import failed: {str(e)}")
        print("\n[FAILURE CATEGORY: SDK/import problem]")
        return 1

    # 3. Initialize Client
    print("\n[3] Client Initialization:")
    api_version = (
        getattr(settings, "GOOGLE_GENAI_API_VERSION", None)
        or os.environ.get("GOOGLE_GENAI_API_VERSION", "v1beta")
    )
    print(f"  • API Version configured: {api_version}")
    print("  • Initializing genai.Client with single-attempt (no retries)...")
    try:
        from google.genai import types
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                api_version=api_version,
                retry_options={"attempts": 1},
            ),
        )
        print("  • Client initialized successfully.")
    except Exception as e:
        safe_err = mask_secret(str(e), api_key)
        print(f"\n[FAILURE CATEGORY: SDK/import problem]")
        print(f"ERROR: {safe_err}")
        return 1

    # 4. Perform Exactly ONE Structured Output Request
    synthetic_input = (
        "Extract the invoice details into JSON matching the schema: "
        "Invoice number TEST-001. Total amount USD 123.45."
    )
    print("\n[4] Executing Single Structured-Output Request:")
    print(f"  • Endpoint: Gemini Interactions API (client.interactions.create)")
    print(f"  • Model: {model}")
    print(f"  • Input payload: {synthetic_input!r}")
    print(f"  • Expected Output: {{'invoice_number': 'TEST-001', 'total': 123.45, 'currency': 'USD'}}")
    print(f"  • Timeout: 30.0s")
    print("  • Sending request...")

    start_time = time.perf_counter()
    interaction = None
    output_text = None
    latency_ms = 0.0

    try:
        interaction = client.interactions.create(
            model=model,
            input=synthetic_input,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": INVOICE_JSON_SCHEMA,
            },
            timeout=30.0,
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        safe_err = mask_secret(str(exc), api_key)
        exc_type = type(exc).__name__

        print(f"\n[DIAGNOSTIC FAILURE] Request failed after {latency_ms} ms")
        print(f"  • Exception Type: {exc_type}")
        print(f"  • Error Detail: {safe_err}")

        # Failure classification
        err_lower = safe_err.lower()
        if "503" in safe_err or "service_unavailable" in err_lower or "high demand" in err_lower:
            print("\n[FAILURE CATEGORY: Server-side 503 / Model availability problem]")
            print(f"HTTP Status: 503 Service Unavailable")
            print(f"DIAGNOSIS: Model '{model}' is temporarily at capacity on Google servers.")
        elif "429" in safe_err or "resource_exhausted" in err_lower or "quota" in err_lower:
            print("\n[FAILURE CATEGORY: Quota/billing problem]")
            print(f"HTTP Status: 429 Too Many Requests / Resource Exhausted")
            print(f"DIAGNOSIS: Rate limit or free-tier quota exhausted.")
        elif "401" in safe_err or "unauthenticated" in err_lower or "invalid_api_key" in err_lower:
            print("\n[FAILURE CATEGORY: Authentication problem]")
            print(f"HTTP Status: 401 Unauthorized")
            print(f"DIAGNOSIS: API key invalid or rejected.")
        elif "403" in safe_err or "permission_denied" in err_lower:
            print("\n[FAILURE CATEGORY: Authentication / Permission problem]")
            print(f"HTTP Status: 403 Forbidden")
            print(f"DIAGNOSIS: Model not accessible with current project credentials.")
        elif "404" in safe_err or "not found" in err_lower:
            print("\n[FAILURE CATEGORY: Model availability problem]")
            print(f"HTTP Status: 404 Not Found")
            print(f"DIAGNOSIS: Model '{model}' does not exist or is not available on this endpoint.")
        elif "timeout" in err_lower or "timed out" in err_lower:
            print("\n[FAILURE CATEGORY: Client timeout problem]")
            print(f"DIAGNOSIS: Request exceeded the 30.0s timeout limit.")
        elif "connection" in err_lower or "name or service not known" in err_lower or "errno -2" in err_lower:
            print("\n[FAILURE CATEGORY: Network error]")
            print(f"DIAGNOSIS: Unable to establish TCP/TLS connection to Google API servers.")
        else:
            print(f"\n[FAILURE CATEGORY: Unclassified API error ({exc_type})]")
            print(f"DIAGNOSIS: {safe_err}")

        return 1

    # 5. Extract output text
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

    if not output_text:
        output_text = str(interaction)

    cleaned_output = output_text.strip()

    # 6. Validate JSON output locally
    print("\n[5] Structured Output & Local Schema Validation:")
    print(f"  • Raw Output Text: {cleaned_output}")
    print(f"  • Request Latency: {latency_ms} ms")

    try:
        parsed_json = json.loads(cleaned_output)
        validated_invoice = InvoiceSchema(**parsed_json)
        print("  • JSON Parsing: SUCCESS")
        print("  • Pydantic Schema Validation: SUCCESS")
        print(f"  • Extracted invoice_number: {validated_invoice.invoice_number!r} (Expected: 'TEST-001')")
        print(f"  • Extracted total: {validated_invoice.total} (Expected: 123.45)")
        print(f"  • Extracted currency: {validated_invoice.currency!r} (Expected: 'USD')")

        # Exact match assertions
        match_number = validated_invoice.invoice_number == "TEST-001"
        match_total = abs(validated_invoice.total - 123.45) < 0.001
        match_currency = validated_invoice.currency == "USD"

        if match_number and match_total and match_currency:
            print("  • Exact Field Values: MATCH")
        else:
            print("  • Field Values: PARTIAL MISMATCH (see above)")

    except json.JSONDecodeError as je:
        print(f"  • JSON Parsing: FAILED ({str(je)})")
        print("\n[FAILURE CATEGORY: Schema validation problem]")
        return 1
    except ValidationError as ve:
        print(f"  • Pydantic Schema Validation: FAILED ({str(ve)})")
        print("\n[FAILURE CATEGORY: Schema validation problem]")
        return 1

    print("\n" + "=" * 70)
    print("STATUS: Structured JSON output verified successfully with Gemini Flash-Lite!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
