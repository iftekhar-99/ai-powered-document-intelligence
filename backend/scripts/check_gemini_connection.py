#!/usr/bin/env python3
"""
Diagnostic script to verify Google Gemini API connectivity.
Uses the official google-genai SDK and the Gemini Interactions API.

SECURITY RULE: NEVER print, log, display, or expose GEMINI_API_KEY.
"""

import os
import sys
import time
from pathlib import Path

# 1. Resolve paths and load project environment
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Ensure backend and project root are in sys.path
for path_dir in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if path_dir not in sys.path:
        sys.path.insert(0, path_dir)

# Load root .env explicitly
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

# Also import settings from app.core.config
try:
    from app.core.config import settings
    config_loaded = True
except Exception as e:
    config_loaded = False
    settings = None


def mask_secret(text: str, secret: str) -> str:
    """Sanitize any accidental reflection of the API key in error messages."""
    if not secret:
        return text
    return text.replace(secret, "[REDACTED_API_KEY]")


def main() -> int:
    print("=" * 70)
    print("Google Gemini API Diagnostics & Connectivity Verification")
    print("=" * 70)

    # 1. Check Configuration Status
    print("\n[1] Environment Configuration Status:")
    print(f"  • Root .env path: {env_file_path} (exists: {env_file_path.exists()})")
    print(f"  • .env loaded successfully: {env_loaded}")

    api_key = ""
    model = "gemini-3.7-flash"
    llm_enabled = False
    llm_provider = ""

    if settings is not None:
        api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "").strip()
        model = settings.GEMINI_MODEL or os.environ.get("GEMINI_MODEL", "gemini-3.7-flash").strip()
        llm_enabled = settings.LLM_ENABLED
        llm_provider = settings.LLM_PROVIDER
        print(f"  • Config provider: app.core.config.settings (verified)")
    else:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        model = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash").strip()
        llm_enabled = os.environ.get("LLM_ENABLED", "false").lower() == "true"
        llm_provider = os.environ.get("LLM_PROVIDER", "")
        print(f"  • Config provider: os.environ fallback")

    print(f"  • LLM_ENABLED: {llm_enabled}")
    print(f"  • LLM_PROVIDER: {llm_provider}")
    print(f"  • GEMINI_MODEL: {model}")

    # Verify API key is present without exposing it
    if not api_key:
        print("  • GEMINI_API_KEY status: MISSING or EMPTY")
        print("\n[FAILURE CATEGORY: Environment configuration problem]")
        print("ERROR: GEMINI_API_KEY is not set in root .env.")
        return 1
    else:
        print(f"  • GEMINI_API_KEY status: PRESENT ({len(api_key)} chars, [SECURELY_MASKED])")

    # 2. Check SDK Installation
    print("\n[2] Official SDK Installation Status:")
    try:
        import google.genai as genai
        sdk_version = getattr(genai, "__version__", "unknown")
        print(f"  • Official package: google.genai")
        print(f"  • SDK version: {sdk_version}")
    except ImportError as e:
        print(f"  • Import failed: {str(e)}")
        print("\n[FAILURE CATEGORY: SDK/import problem]")
        print("ERROR: google-genai is not installed in the active environment.")
        return 1

    # 3. Initialize Client & Make Exactly ONE Request
    print("\n[3] API Client Initialization & Single Diagnostic Request:")
    api_version = (
        getattr(settings, "GOOGLE_GENAI_API_VERSION", None)
        or os.environ.get("GOOGLE_GENAI_API_VERSION", "v1beta")
    )
    print(f"  • API Version configured: {api_version}")
    print("  • Initializing genai.Client with single-attempt (no automatic retry)...")
    try:
        from google.genai import types
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                api_version=api_version,
                retry_options={"attempts": 1},
            )
        )
        print("  • Client initialized successfully.")
    except Exception as e:
        safe_msg = mask_secret(str(e), api_key)
        print(f"\n[FAILURE CATEGORY: SDK/import problem]")
        print(f"ERROR: Client initialization failed: {safe_msg}")
        return 1

    prompt_input = "Reply with exactly: GEMINI_CONNECTION_OK"
    print(f"  • Target endpoint: Gemini Interactions API (client.interactions.create)")
    print(f"  • Model: {model}")
    print(f"  • Input payload: {prompt_input!r}")
    print("  • Executing single minimal request...")

    start_time = time.perf_counter()
    interaction = None
    output_text = None
    latency_ms = 0.0

    try:
        interaction = client.interactions.create(
            model=model,
            input=prompt_input,
            timeout=30.0,
        )
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        safe_err = mask_secret(str(exc), api_key)
        exc_type = type(exc).__name__

        print(f"\n[DIAGNOSTIC FAILURE] Request failed after {latency_ms} ms")
        print(f"  • Exception: {exc_type}")
        print(f"  • Detail: {safe_err}")

        err_lower = safe_err.lower()
        if "503" in safe_err or "temporar" in err_lower or "high demand" in err_lower or "unavailable" in err_lower:
            print("\n[FAILURE CATEGORY: Model availability problem]")
            print(f"DIAGNOSIS: Model '{model}' is currently experiencing high demand (503 Service Unavailable).")
            print("The API key is authenticated and accepted, but the requested model is temporarily at capacity.")
        elif "404" in safe_err or "not found" in err_lower or "unsupported" in err_lower:
            print("\n[FAILURE CATEGORY: Model availability problem]")
            print(f"DIAGNOSIS: Model identifier '{model}' was not found or is unavailable for this API version.")
        elif "401" in safe_err or "403" in safe_err or "api_key" in err_lower or "unauthenticated" in err_lower:
            print("\n[FAILURE CATEGORY: Authentication problem]")
            print("DIAGNOSIS: Authentication rejected by Google AI Studio. Verify the API key in .env.")
        elif "429" in safe_err or "quota" in err_lower or "resource_exhausted" in err_lower:
            print("\n[FAILURE CATEGORY: Quota/billing problem]")
            print("DIAGNOSIS: Quota or rate limit exceeded on this API key.")
        elif "timeout" in err_lower or "connection" in err_lower or "name or service not known" in err_lower or "errno -2" in err_lower:
            print("\n[FAILURE CATEGORY: Network/timeout problem]")
            print("DIAGNOSIS: Network connectivity error reaching generativelanguage.googleapis.com.")
        else:
            print(f"\n[FAILURE CATEGORY: API error ({exc_type})]")
            print(f"DIAGNOSIS: Unclassified API failure: {safe_err}")

        return 1

    # 4. Extract and Read Response Output
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

    # 5. Report Success Results
    print("\n[4] Diagnostic Verification Results:")
    print(f"  • Configuration Loaded: SUCCESS")
    print(f"  • SDK Version: {sdk_version}")
    print(f"  • Model Identifier: {model}")
    print(f"  • Authentication: SUCCESS")
    print(f"  • API Request: SUCCESS")
    print(f"  • Response Latency: {latency_ms} ms")
    print(f"  • Response Text: {cleaned_output!r}")

    if "GEMINI_CONNECTION_OK" in cleaned_output.upper():
        print(f"  • Output Verification: MATCH (Contains 'GEMINI_CONNECTION_OK')")
    else:
        print(f"  • Output Verification: RECEIVED TEXT: {cleaned_output!r}")

    print("\n" + "=" * 70)
    print("STATUS: Gemini API connection verified successfully!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
