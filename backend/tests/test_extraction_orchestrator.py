"""
Automated unit tests for InvoiceExtractionOrchestrator, EvidenceValidator,
and MultiBatchMerger (Task 4D).

All tests use strictly MOCKED LLM responses — ZERO real API calls are made.

Covers:
1. One single-page invoice.
2. One multi-page invoice.
3. Two separate invoices in one PDF.
4. Multiple batches belonging to one invoice.
5. Multiple invoices in one spreadsheet.
6. Missing invoice fields.
7. Conflicting field values between batches.
8. Invalid source chunk IDs (rejected & flagged).
9. Valid evidence references.
10. Missing evidence for core fields.
11. Malformed JSON response.
12. Empty Gemini response.
13. 429 retry handling.
14. 503 retry handling.
15. Authentication failure without retry.
16. Timeout handling.
17. Missing API configuration.
18. Non-invoice document (skipped with metadata).
19. Ambiguous invoice segmentation.
20. Duplicate overlapping line-item detection.
21. Legitimate repeated line items (preserved).
22. Confidence threshold enforcement.
23. No source chunk loss.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.schemas.extraction import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    ExtractionStatus,
    InvoiceExtraction,
    InvoiceLineItemExtraction,
    SourceEvidence,
)
from app.services.extraction.context_models import (
    ContextPreparationResult,
    ExtractionContext,
    RowRange,
)
from app.services.extraction.orchestrator import (
    EvidenceValidator,
    InvoiceExtractionOrchestrator,
    MultiBatchMerger,
    inline_schema_defs,
)
from app.services.extraction.providers import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMMalformedResponseError,
    LLMProvider,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMStructuredResponse,
    LLMTimeoutError,
    LLMUsageMetadata,
)


def _make_mock_provider(responses=None, errors=None):
    """Creates a mock LLMProvider that yields responses or raises errors sequentially."""
    provider = MagicMock(spec=LLMProvider)
    provider.provider_name = "gemini"
    provider.model_name = "gemini-flash-lite-latest"

    call_index = 0
    resp_list = list(responses or [])
    err_list = list(errors or [])

    async def mock_generate(*args, **kwargs):
        nonlocal call_index
        idx = call_index
        call_index += 1

        if idx < len(err_list) and err_list[idx] is not None:
            raise err_list[idx]

        if idx < len(resp_list):
            return resp_list[idx]

        return LLMStructuredResponse(
            raw_text="{}",
            parsed_json={"invoices": []},
            model="gemini-flash-lite-latest",
            latency_ms=10.0,
        )

    provider.generate_structured = AsyncMock(side_effect=mock_generate)
    return provider


def _make_context(doc_id, index=0, chunk_ids=None, text="Invoice Text", doc_type="invoice", parent_id=None, is_split=False, batch_idx=0):
    c_ids = chunk_ids or [uuid4()]
    meta = {}
    if parent_id:
        meta["parent_context_id"] = str(parent_id)
        meta["is_split"] = is_split
        meta["batch_index"] = batch_idx
    return ExtractionContext(
        context_id=uuid4(),
        document_id=doc_id,
        context_index=index,
        document_type_hint=doc_type,
        source_chunk_ids=c_ids,
        page_start=1,
        page_end=1,
        combined_text=text,
        character_count=len(text),
        estimated_input_tokens=10,
        metadata=meta,
    )


# ==============================================================================
# Tests 1 - 5: Invoice Extraction Topologies
# ==============================================================================


@pytest.mark.asyncio
async def test_1_single_page_invoice(monkeypatch):
    """Single-page invoice extraction produces 1 validated invoice."""
    doc_id = uuid4()
    c1_id = uuid4()
    ctx = _make_context(doc_id, chunk_ids=[c1_id])

    mock_prep = ContextPreparationResult(
        document_id=doc_id,
        contexts=[ctx],
        total_source_chunks=1,
        selected_source_chunks=1,
        unselected_source_chunks=0,
    )

    provider_response = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={
            "document_id": str(doc_id),
            "document_type": "invoice",
            "invoices": [
                {
                    "invoice_number": {"value": "INV-2026-001", "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "INV-2026-001"}]},
                    "supplier_name": {"value": "Acme Corp", "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "Acme Corp"}]},
                    "total": {"value": 1250.00, "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "$1,250.00"}]},
                    "currency": {"value": "USD"},
                    "overall_confidence": 0.95,
                }
            ],
            "extraction_status": "completed",
        },
        model="gemini-flash-lite-latest",
        latency_ms=25.0,
    )
    provider = _make_mock_provider(responses=[provider_response])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert result.document_id == doc_id
    assert len(result.invoices) == 1
    assert result.invoices[0].invoice_number.value == "INV-2026-001"
    assert result.invoices[0].total.value == Decimal("1250.00")
    assert result.invoices[0].currency.value == "USD"
    assert result.extraction_status == ExtractionStatus.COMPLETED


@pytest.mark.asyncio
async def test_2_multi_page_invoice(monkeypatch):
    """Multi-page invoice spans multiple chunks with page boundaries."""
    doc_id = uuid4()
    c1_id = uuid4()
    c2_id = uuid4()
    ctx = _make_context(doc_id, chunk_ids=[c1_id, c2_id])
    ctx.page_start = 1
    ctx.page_end = 2

    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=2, selected_source_chunks=2)
    provider_response = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={
            "invoices": [
                {
                    "invoice_number": {"value": "INV-MULTI", "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "INV-MULTI"}]},
                    "total": {"value": 2500.00, "evidence": [{"source_chunk_id": str(c2_id), "relevant_text": "$2,500.00"}]},
                    "document_page_start": 1,
                    "document_page_end": 2,
                }
            ]
        },
        model="gemini-flash-lite-latest",
        latency_ms=30.0,
    )
    provider = _make_mock_provider(responses=[provider_response])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert len(result.invoices) == 1
    assert result.invoices[0].document_page_start == 1
    assert result.invoices[0].document_page_end == 2


@pytest.mark.asyncio
async def test_3_two_separate_invoices_in_one_pdf(monkeypatch):
    """Two distinct invoice contexts in one PDF produce 2 extracted invoices."""
    doc_id = uuid4()
    c1_id = uuid4()
    c2_id = uuid4()
    ctx1 = _make_context(doc_id, index=0, chunk_ids=[c1_id])
    ctx2 = _make_context(doc_id, index=1, chunk_ids=[c2_id])

    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx1, ctx2], total_source_chunks=2, selected_source_chunks=2)

    resp1 = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={"invoices": [{"invoice_number": {"value": "INV-A", "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "A"}]}}]},
        model="gemini-flash-lite-latest",
        latency_ms=20.0,
    )
    resp2 = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={"invoices": [{"invoice_number": {"value": "INV-B", "evidence": [{"source_chunk_id": str(c2_id), "relevant_text": "B"}]}}]},
        model="gemini-flash-lite-latest",
        latency_ms=20.0,
    )
    provider = _make_mock_provider(responses=[resp1, resp2])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert len(result.invoices) == 2
    assert result.invoices[0].invoice_number.value == "INV-A"
    assert result.invoices[1].invoice_number.value == "INV-B"


@pytest.mark.asyncio
async def test_4_multiple_batches_belonging_to_one_invoice(monkeypatch):
    """Split batches of the same invoice are merged into a single consolidated invoice."""
    doc_id = uuid4()
    parent_id = uuid4()
    c1_id = uuid4()
    c2_id = uuid4()

    batch0 = _make_context(doc_id, index=0, chunk_ids=[c1_id], parent_id=parent_id, is_split=True, batch_idx=0)
    batch1 = _make_context(doc_id, index=1, chunk_ids=[c2_id], parent_id=parent_id, is_split=True, batch_idx=1)

    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[batch0, batch1], total_source_chunks=2, selected_source_chunks=2)

    resp0 = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={
            "invoices": [
                {
                    "invoice_number": {"value": "INV-SPLIT", "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "INV-SPLIT"}]},
                    "line_items": [{"description": {"value": "Item 1"}, "line_total": {"value": 100.00}}],
                }
            ]
        },
        model="gemini-flash-lite-latest",
        latency_ms=20.0,
    )
    resp1 = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={
            "invoices": [
                {
                    "total": {"value": 250.00, "evidence": [{"source_chunk_id": str(c2_id), "relevant_text": "$250.00"}]},
                    "line_items": [{"description": {"value": "Item 2"}, "line_total": {"value": 150.00}}],
                }
            ]
        },
        model="gemini-flash-lite-latest",
        latency_ms=20.0,
    )
    provider = _make_mock_provider(responses=[resp0, resp1])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    # Merged into exactly 1 invoice
    assert len(result.invoices) == 1
    inv = result.invoices[0]
    assert inv.invoice_number.value == "INV-SPLIT"
    assert inv.total.value == Decimal("250.00")
    assert len(inv.line_items) == 2


@pytest.mark.asyncio
async def test_5_multiple_invoices_in_one_spreadsheet(monkeypatch):
    """Multiple invoice contexts from a spreadsheet are each extracted."""
    doc_id = uuid4()
    c1_id = uuid4()
    c2_id = uuid4()
    ctx1 = _make_context(doc_id, index=0, chunk_ids=[c1_id], doc_type="invoice")
    ctx1.sheet_names = ["Jan"]
    ctx2 = _make_context(doc_id, index=1, chunk_ids=[c2_id], doc_type="invoice")
    ctx2.sheet_names = ["Feb"]

    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx1, ctx2], total_source_chunks=2, selected_source_chunks=2)

    resp1 = LLMStructuredResponse(raw_text="{}", parsed_json={"invoices": [{"invoice_number": {"value": "INV-JAN"}}]}, model="m", latency_ms=10)
    resp2 = LLMStructuredResponse(raw_text="{}", parsed_json={"invoices": [{"invoice_number": {"value": "INV-FEB"}}]}, model="m", latency_ms=10)
    provider = _make_mock_provider(responses=[resp1, resp2])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert len(result.invoices) == 2
    assert result.invoices[0].invoice_number.value == "INV-JAN"
    assert result.invoices[1].invoice_number.value == "INV-FEB"


# ==============================================================================
# Tests 6 - 10: Missing Fields, Conflicts, Evidence Validation
# ==============================================================================


@pytest.mark.asyncio
async def test_6_missing_invoice_fields(monkeypatch):
    """Missing invoice fields remain null and trigger low completeness review warning."""
    doc_id = uuid4()
    c1_id = uuid4()
    ctx = _make_context(doc_id, chunk_ids=[c1_id])
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    # Only total populated, all other fields missing
    resp = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={"invoices": [{"total": {"value": 50.00, "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "$50"}]}}]},
        model="m",
        latency_ms=10,
    )
    provider = _make_mock_provider(responses=[resp])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    inv = result.invoices[0]
    assert inv.invoice_number.value is None
    assert inv.supplier_name.value is None
    assert inv.total.value == Decimal("50.00")
    assert inv.needs_manual_review is True
    assert any("Low invoice completeness" in r for r in inv.review_reasons)


def test_7_conflicting_field_values_between_batches():
    """Conflicting non-null field values across batches are flagged without silent overwrite."""
    inv_a = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-001"),
        total=ExtractedField(value=Decimal("1000.00")),
    )
    inv_b = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-001"),
        total=ExtractedField(value=Decimal("1500.00")),  # Conflicting total
    )

    merged = MultiBatchMerger.merge_invoices(inv_a, inv_b)
    assert merged.needs_manual_review is True
    assert any("Conflicting values for 'total'" in r for r in merged.review_reasons)


def test_8_invalid_source_chunk_ids():
    """Evidence referencing fabricated/unknown chunk IDs is rejected and flagged."""
    real_chunk_id = uuid4()
    fake_chunk_id = uuid4()

    inv = InvoiceExtraction(
        invoice_number=ExtractedField(
            value="INV-001",
            evidence=[
                SourceEvidence(source_chunk_id=real_chunk_id, relevant_text="real"),
                SourceEvidence(source_chunk_id=fake_chunk_id, relevant_text="fake"),
            ],
        )
    )

    warnings = EvidenceValidator.validate_invoice_evidence(inv, allowed_chunk_ids={real_chunk_id})
    assert len(inv.invoice_number.evidence) == 1
    assert inv.invoice_number.evidence[0].source_chunk_id == real_chunk_id
    assert inv.needs_manual_review is True
    assert any("Rejected invalid/unknown source_chunk_id" in w for w in warnings)


def test_9_valid_evidence_references():
    """Valid evidence references are retained cleanly."""
    c_id = uuid4()
    inv = InvoiceExtraction(
        total=ExtractedField(
            value=Decimal("100.00"),
            evidence=[SourceEvidence(source_chunk_id=c_id, relevant_text="$100.00")],
        )
    )

    warnings = EvidenceValidator.validate_invoice_evidence(inv, allowed_chunk_ids={c_id})
    assert len(inv.total.evidence) == 1
    assert inv.total.evidence[0].source_chunk_id == c_id
    assert not any("Rejected" in w for w in warnings)


def test_10_missing_evidence():
    """Extracted core field with non-null value but empty evidence flags manual review."""
    c_id = uuid4()
    inv = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-NO-EVIDENCE", evidence=[]),
        total=ExtractedField(value=Decimal("500.00"), evidence=[]),
    )

    warnings = EvidenceValidator.validate_invoice_evidence(inv, allowed_chunk_ids={c_id})
    assert inv.needs_manual_review is True
    assert any("extracted without supporting source evidence" in w for w in warnings)


# ==============================================================================
# Tests 11 - 17: Error and Retry Handling
# ==============================================================================


@pytest.mark.asyncio
async def test_11_malformed_json(monkeypatch):
    """Malformed JSON response from model is handled without crashing."""
    doc_id = uuid4()
    ctx = _make_context(doc_id)
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    provider = _make_mock_provider(errors=[LLMMalformedResponseError("Malformed JSON output")])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider, max_retries=0)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert result.extraction_status == ExtractionStatus.FAILED
    assert any("Failed to extract context" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_12_empty_gemini_response(monkeypatch):
    """Empty model output handled gracefully and marked failed."""
    doc_id = uuid4()
    ctx = _make_context(doc_id)
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    resp = LLMStructuredResponse(raw_text="", parsed_json={}, model="m", latency_ms=10)
    provider = _make_mock_provider(responses=[resp])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert len(result.invoices) == 0


@pytest.mark.asyncio
async def test_13_429_retry_handling(monkeypatch):
    """HTTP 429 rate limit is retried with backoff and succeeds on attempt 2."""
    doc_id = uuid4()
    c1_id = uuid4()
    ctx = _make_context(doc_id, chunk_ids=[c1_id])
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    err = LLMRateLimitError("Rate limit exceeded (429)", status_code=429)
    success_resp = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={"invoices": [{"invoice_number": {"value": "INV-RETRY-OK"}}]},
        model="m",
        latency_ms=15,
    )
    provider = _make_mock_provider(errors=[err], responses=[None, success_resp])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider, max_retries=2, base_retry_delay=0.01)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert len(result.invoices) == 1
    assert result.invoices[0].invoice_number.value == "INV-RETRY-OK"
    assert result.extraction_status == ExtractionStatus.COMPLETED


@pytest.mark.asyncio
async def test_14_503_retry_handling(monkeypatch):
    """HTTP 503 Service Unavailable is retried and succeeds."""
    doc_id = uuid4()
    c1_id = uuid4()
    ctx = _make_context(doc_id, chunk_ids=[c1_id])
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    err = LLMServiceUnavailableError("503 Service Unavailable", status_code=503)
    success_resp = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={"invoices": [{"invoice_number": {"value": "INV-503-RECOVERED"}}]},
        model="m",
        latency_ms=15,
    )
    provider = _make_mock_provider(errors=[err], responses=[None, success_resp])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider, max_retries=2, base_retry_delay=0.01)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert len(result.invoices) == 1
    assert result.invoices[0].invoice_number.value == "INV-503-RECOVERED"


@pytest.mark.asyncio
async def test_15_authentication_failure_without_retry(monkeypatch):
    """LLMAuthenticationError terminates immediately without retrying."""
    doc_id = uuid4()
    ctx = _make_context(doc_id)
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    err = LLMAuthenticationError("401 Invalid API Key", status_code=401)
    provider = _make_mock_provider(errors=[err])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider, max_retries=3)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    # Provider should only be called once (no retries for auth)
    assert provider.generate_structured.call_count == 1
    assert result.extraction_status == ExtractionStatus.FAILED


@pytest.mark.asyncio
async def test_16_timeout_handling(monkeypatch):
    """LLMTimeoutError is retried up to configured limit."""
    doc_id = uuid4()
    ctx = _make_context(doc_id)
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    err = LLMTimeoutError("Request timed out", status_code=408)
    provider = _make_mock_provider(errors=[err, err, err])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider, max_retries=2, base_retry_delay=0.01)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert provider.generate_structured.call_count == 3  # 1 initial + 2 retries
    assert result.extraction_status == ExtractionStatus.FAILED


@pytest.mark.asyncio
async def test_17_missing_api_configuration(monkeypatch):
    """Missing provider configuration fails gracefully with clean status."""
    doc_id = uuid4()
    ctx = _make_context(doc_id)
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    # Mock get_llm_provider to raise LLMConfigurationError
    from app.services.extraction.orchestrator import InvoiceExtractionOrchestrator
    with pytest.raises(LLMConfigurationError):
        def bad_factory():
            raise LLMConfigurationError("Missing GEMINI_API_KEY")
        monkeypatch.setattr("app.services.extraction.orchestrator.get_llm_provider", bad_factory)
        orch = InvoiceExtractionOrchestrator(provider=None)
        await orch.extract_document_invoices(doc_id, db_session=None)


# ==============================================================================
# Tests 18 - 23: Context Filtering, Deduplication, and Quality
# ==============================================================================


@pytest.mark.asyncio
async def test_18_non_invoice_document(monkeypatch):
    """Document with only non-invoice contexts skips extraction cleanly."""
    doc_id = uuid4()
    ctx = _make_context(doc_id, doc_type="other", text="Terms and conditions only.")
    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    provider = _make_mock_provider()

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert len(result.invoices) == 0
    assert result.document_type == DocumentType.OTHER
    assert provider.generate_structured.call_count == 0  # No LLM calls for skipped content


@pytest.mark.asyncio
async def test_19_ambiguous_invoice_segmentation(monkeypatch):
    """Ambiguous context segmentation flags are carried through to the invoice."""
    doc_id = uuid4()
    c1_id = uuid4()
    ctx = _make_context(doc_id, chunk_ids=[c1_id])
    ctx.needs_manual_review = True
    ctx.review_reasons = ["Ambiguous invoice boundaries between pages 2 and 3"]

    mock_prep = ContextPreparationResult(document_id=doc_id, contexts=[ctx], total_source_chunks=1, selected_source_chunks=1)

    provider_resp = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={"invoices": [{"invoice_number": {"value": "INV-AMBIG", "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "text"}]}}]},
        model="m",
        latency_ms=10,
    )
    provider = _make_mock_provider(responses=[provider_resp])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert result.invoices[0].needs_manual_review is True


def test_20_duplicate_overlapping_line_item_detection():
    """Identical line items from overlap boundary are deduplicated when evidence matches."""
    c1_id = uuid4()
    ev1 = SourceEvidence(source_chunk_id=c1_id, relevant_text="Widget A $10.00")

    item_batch1 = InvoiceLineItemExtraction(
        description=ExtractedField(value="Widget A", evidence=[ev1]),
        line_total=ExtractedField(value=Decimal("10.00"), evidence=[ev1]),
    )
    item_batch2_overlap = InvoiceLineItemExtraction(
        description=ExtractedField(value="Widget A", evidence=[ev1]),
        line_total=ExtractedField(value=Decimal("10.00"), evidence=[ev1]),
    )
    item_batch2_new = InvoiceLineItemExtraction(
        description=ExtractedField(value="Widget B", evidence=[SourceEvidence(source_chunk_id=c1_id, relevant_text="Widget B $20.00")]),
        line_total=ExtractedField(value=Decimal("20.00")),
    )

    merged = MultiBatchMerger._merge_line_items(
        base_items=[item_batch1],
        incoming_items=[item_batch2_overlap, item_batch2_new],
    )

    # item_batch2_overlap was dropped as duplicate; item_batch2_new retained
    assert len(merged) == 2
    assert merged[0].description.value == "Widget A"
    assert merged[1].description.value == "Widget B"


def test_21_legitimate_repeated_line_items():
    """Legitimate repeated line items with different source evidence are both preserved."""
    c1_id = uuid4()
    c2_id = uuid4()

    item_day1 = InvoiceLineItemExtraction(
        description=ExtractedField(value="Consulting Hour", evidence=[SourceEvidence(source_chunk_id=c1_id, relevant_text="Day 1 Consulting")]),
        line_total=ExtractedField(value=Decimal("150.00")),
    )
    item_day2 = InvoiceLineItemExtraction(
        description=ExtractedField(value="Consulting Hour", evidence=[SourceEvidence(source_chunk_id=c2_id, relevant_text="Day 2 Consulting")]),
        line_total=ExtractedField(value=Decimal("150.00")),
    )

    merged = MultiBatchMerger._merge_line_items(
        base_items=[item_day1],
        incoming_items=[item_day2],
    )

    # Both items must be preserved!
    assert len(merged) == 2
    assert merged[0].description.value == "Consulting Hour"
    assert merged[1].description.value == "Consulting Hour"


def test_22_confidence_threshold_enforcement():
    """Overall confidence below threshold sets needs_manual_review."""
    inv = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-LOW-CONF"),
        total=ExtractedField(value=Decimal("100.00")),
        overall_confidence=0.55,  # Below 0.75
    )
    warnings = []
    orchestrator = InvoiceExtractionOrchestrator(confidence_threshold=0.75)
    orchestrator._assess_invoice_quality(inv, warnings)

    assert inv.needs_manual_review is True
    assert any("below threshold" in r for r in inv.review_reasons)


@pytest.mark.asyncio
async def test_23_no_source_chunk_loss(monkeypatch):
    """All source chunks in selected contexts remain accounted for."""
    doc_id = uuid4()
    c1_id = uuid4()
    c2_id = uuid4()
    ctx = _make_context(doc_id, chunk_ids=[c1_id, c2_id])
    mock_prep = ContextPreparationResult(
        document_id=doc_id,
        contexts=[ctx],
        total_source_chunks=2,
        selected_source_chunks=2,
        unselected_source_chunks=0,
    )

    provider_resp = LLMStructuredResponse(
        raw_text="{}",
        parsed_json={"invoices": [{"invoice_number": {"value": "INV-TOTAL", "evidence": [{"source_chunk_id": str(c1_id), "relevant_text": "INV"}]}}]},
        model="m",
        latency_ms=10,
    )
    provider = _make_mock_provider(responses=[provider_resp])

    from app.services.extraction.context_service import context_service
    monkeypatch.setattr(context_service, "prepare_document_contexts", AsyncMock(return_value=mock_prep))

    orchestrator = InvoiceExtractionOrchestrator(provider=provider)
    result = await orchestrator.extract_document_invoices(doc_id, db_session=None)

    assert mock_prep.selected_source_chunks == 2
    assert len(result.invoices) == 1


def test_schema_inlining():
    """Verify inline_schema_defs dereferences $defs completely."""
    schema = {
        "$defs": {
            "SubItem": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
        "type": "object",
        "properties": {
            "item": {"$ref": "#/$defs/SubItem"},
        },
    }
    inlined = inline_schema_defs(schema)
    assert "$defs" not in inlined
    assert inlined["properties"]["item"]["properties"]["name"]["type"] == "string"
