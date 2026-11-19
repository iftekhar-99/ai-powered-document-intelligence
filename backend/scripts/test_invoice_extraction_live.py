#!/usr/bin/env python3
"""
End-to-End Live Gemini Invoice Extraction Test.

Exercises the complete context-to-Gemini-to-Pydantic-validation workflow:
1. Creates temporary in-memory database fixtures (Document, DocumentChunk).
2. Runs ContextPreparationService to segment and budget extraction contexts.
3. Builds hardened, versioned extraction prompt.
4. Invokes Google Gemini Interactions API (gemini-flash-lite-latest, v1beta) exactly ONCE.
5. Performs strict Pydantic v2 schema validation.
6. Validates SourceEvidence against source chunk allowlist.
7. Evaluates field completeness and confidence thresholds.

SECURITY RULES:
- Only runs when RUN_LLM_INTEGRATION_TESTS=true.
- Uses synthetic invoice data ONLY (never real business documents).
- NEVER prints, logs, displays, or exposes GEMINI_API_KEY.
- Makes exactly ONE generation request (automatic retries disabled).
- Temporary in-memory database: NO permanent invoice records are stored.
"""

import asyncio
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# 1. Resolve paths
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for path_dir in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if path_dir not in sys.path:
        sys.path.insert(0, path_dir)

# 2. Load root .env
from dotenv import load_dotenv

env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(dotenv_path=env_file, override=True)


SYNTHETIC_INVOICE_TEXT = (
    "TAX INVOICE\n"
    "Invoice Number: TEST-LIVE-001\n"
    "Invoice Date: 2026-11-10\n"
    "Supplier: ABC Supplies Ltd.\n"
    "Customer: XYZ Corporation\n"
    "\n"
    "LINE ITEMS:\n"
    "- Description: Office supplies\n"
    "  Quantity: 2\n"
    "  Unit Price: USD 50.00\n"
    "  Tax: USD 15.00\n"
    "  Line Total: USD 115.00\n"
    "\n"
    "Subtotal: USD 100.00\n"
    "Tax: USD 15.00\n"
    "Total: USD 115.00\n"
)


async def main() -> int:
    print("=" * 70)
    print("End-to-End Live Gemini Invoice Extraction Test (Task 4D.1)")
    print("=" * 70)

    # 1. Check feature flag
    flag = os.environ.get("RUN_LLM_INTEGRATION_TESTS", "").strip().lower()
    if flag != "true":
        print("\nSKIPPED: Live LLM integration tests are disabled by default.")
        print("To enable this test, run:")
        print("  RUN_LLM_INTEGRATION_TESTS=true backend/.venv/bin/python backend/scripts/test_invoice_extraction_live.py")
        return 0

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

    from app.core.config import settings
    from app.db.base import Base
    from app.models.chunk import ChunkSourceType, DocumentChunk
    from app.models.document import Document, DocumentStatus
    from app.schemas.extraction import DocumentExtractionResponse, ExtractionStatus
    from app.services.extraction.orchestrator import InvoiceExtractionOrchestrator
    from app.services.extraction.providers import get_llm_provider, mask_secret

    api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "").strip()
    model = settings.GEMINI_MODEL or os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
    api_version = settings.GOOGLE_GENAI_API_VERSION or "v1beta"

    print("\n[1] Configuration & Safety Pre-Checks:")
    print(f"  • Provider: {settings.LLM_PROVIDER}")
    print(f"  • Model: {model}")
    print(f"  • API Version: {api_version}")
    print(f"  • API Key Present: {bool(api_key)} ({len(api_key)} chars, [SECURELY_MASKED])")
    print("  • Automatic Retries: DISABLED (max_retries=0, exactly 1 live request)")
    print("  • Database Storage: IN-MEMORY TEMPORARY (no permanent records persisted)")

    if not api_key:
        print("\nERROR: GEMINI_API_KEY is not configured in .env.")
        return 1

    # 2. Set up temporary in-memory database fixtures
    print("\n[2] Setting Up Temporary In-Memory Database Fixtures:")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    doc_id = uuid4()
    chunk_id = uuid4()

    async with session_factory() as session:
        doc = Document(
            id=doc_id,
            original_filename="synthetic_invoice_live.pdf",
            stored_filename=f"synthetic_{doc_id}.pdf",
            file_path=f"/tmp/synthetic_{doc_id}.pdf",
            file_type="pdf",
            mime_type="application/pdf",
            file_size=len(SYNTHETIC_INVOICE_TEXT.encode("utf-8")),
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            status=DocumentStatus.PROCESSING.value,
        )
        session.add(doc)

        chunk = DocumentChunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            source_type=ChunkSourceType.PDF_PAGE.value,
            page_number=1,
            content=SYNTHETIC_INVOICE_TEXT,
            extraction_method="DIGITAL_TEXT",
        )
        session.add(chunk)
        await session.commit()

        print(f"  • Created temporary Document: {doc_id}")
        print(f"  • Created temporary DocumentChunk: {chunk_id} (Page 1)")

        # 3. Instantiate Provider & Orchestrator with retries disabled
        provider = get_llm_provider(
            provider_name="gemini",
            api_key=api_key,
            model=model,
            api_version=api_version,
            timeout=30.0,
        )
        orchestrator = InvoiceExtractionOrchestrator(
            provider=provider,
            max_retries=0,  # Strict: exactly 1 request
            confidence_threshold=0.75,
        )

        print("\n[3] Executing Live Extraction via InvoiceExtractionOrchestrator:")
        print("  • Triggering extract_document_invoices (ContextPreparation -> Gemini -> Pydantic)...")
        print("  • Sending request to Google Gemini API...")

        start_time = time.perf_counter()
        raw_error: str = ""
        response: DocumentExtractionResponse = None

        try:
            response = await orchestrator.extract_document_invoices(
                document_id=doc_id,
                db=session,
            )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            raw_error = mask_secret(str(exc), api_key)
            print(f"\n[FAILURE] Extraction request failed after {latency_ms} ms")
            print(f"  • Error: {raw_error}")
            return 1

    # 4. Report results
    print(f"\n[4] Execution Outcome (Latency: {latency_ms} ms):")
    print(f"  • API Request Succeeded: {response is not None and response.extraction_status != ExtractionStatus.FAILED}")
    print(f"  • Extraction Status: {response.extraction_status}")
    print(f"  • Document Type: {response.document_type}")
    print(f"  • Invoices Extracted: {len(response.invoices)}")
    print(f"  • Warnings Recorded: {response.warnings}")

    if not response.invoices:
        print("\nERROR: No invoices were extracted from the synthetic document context.")
        return 1

    inv = response.invoices[0]

    # 5. Field Matching Verification
    print("\n[5] Field Verification Against Synthetic Input:")
    checks = [
        ("1. Invoice Number", inv.invoice_number.value, "TEST-LIVE-001"),
        ("2. Invoice Date", inv.invoice_date.value, "2026-11-10"),
        ("3. Supplier Name", inv.supplier_name.value, "ABC Supplies Ltd."),
        ("4. Customer Name", inv.customer_name.value, "XYZ Corporation"),
        ("5. Subtotal", float(inv.subtotal.value) if inv.subtotal.value else None, 100.00),
        ("6. Tax", float(inv.tax.value) if inv.tax.value else None, 15.00),
        ("7. Total", float(inv.total.value) if inv.total.value else None, 115.00),
        ("8. Currency", inv.currency.value, "USD"),
    ]

    has_line_item = len(inv.line_items) > 0
    li = inv.line_items[0] if has_line_item else None

    if li:
        checks.extend([
            ("9. Line Item Description", li.description.value, "Office supplies"),
            ("10. Line Item Quantity", float(li.quantity.value) if li.quantity.value else None, 2.0),
            ("11. Line Item Unit Price", float(li.unit_price.value) if li.unit_price.value else None, 50.00),
            ("12. Line Item Tax", float(li.tax.value) if li.tax.value else None, 15.00),
            ("13. Line Item Total", float(li.line_total.value) if li.line_total.value else None, 115.00),
        ])

    all_matched = True
    mismatches = []

    for name, actual, expected in checks:
        matched = False
        if actual is not None and expected is not None:
            if isinstance(expected, float):
                matched = abs(float(actual) - expected) < 0.01
            elif isinstance(expected, str):
                matched = actual.strip().lower() == expected.strip().lower()
            else:
                matched = actual == expected

        status_str = "MATCH" if matched else "MISMATCH"
        if not matched:
            all_matched = False
            mismatches.append((name, actual, expected))

        print(f"  • {name:<26}: Actual={actual!r:<24} Expected={expected!r:<20} [{status_str}]")

    # 6. Source Evidence Verification
    print("\n[6] Source Evidence Verification:")
    evidence_valid = True
    for fname in ["invoice_number", "total", "supplier_name", "subtotal"]:
        f = getattr(inv, fname)
        ev_count = len(f.evidence)
        chunk_match = any(e.source_chunk_id == chunk_id for e in f.evidence) if ev_count else False
        if not chunk_match:
            evidence_valid = False
        print(f"  • {fname:<18}: {ev_count} evidence record(s), links to synthetic chunk: {chunk_match}")

    print(f"  • Overall Evidence Validity: {'VALID (Linked to actual chunk)' if evidence_valid else 'PARTIAL'}")

    # 7. Quality & Pydantic Validation
    print("\n[7] Quality Metrics & Review Status:")
    print(f"  • Overall Confidence Score: {inv.overall_confidence} (estimated confidence, not measured accuracy)")
    print(f"  • Needs Manual Review: {inv.needs_manual_review}")
    print(f"  • Review Reasons: {inv.review_reasons}")

    # 8. Full Formatted JSON Representation
    print("\n[8] Complete Validated Model JSON Representation:")
    dumped = response.model_dump(mode="json")
    print(json.dumps(dumped, indent=2))

    print("\n" + "=" * 70)
    if all_matched:
        print("SUMMARY: 100% of synthetic invoice fields extracted and verified!")
    else:
        print(f"SUMMARY: Partial match. Mismatches on {len(mismatches)} field(s): {mismatches}")
    print("=" * 70)

    return 0 if (response.extraction_status == ExtractionStatus.COMPLETED and len(response.invoices) > 0) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
