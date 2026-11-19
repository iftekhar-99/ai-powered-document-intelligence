"""
Tests for Invoice Database Persistence REST APIs (Task 4E).

Covers:
21. Start extraction returns HTTP 202 Accepted.
22. Missing document returns 404.
23. LLM disabled / unconfigured handling returns 503.
24. Document invoices endpoint returns extracted invoices.
25. Historical run retrieval using extraction_run_id query parameter.
26. Individual invoice retrieval (GET /api/v1/invoices/{id}).
27. Extraction history (GET /api/v1/documents/{id}/extraction-history).
28. Extraction run status (GET /api/v1/extraction-runs/{id}).
29. Re-extraction creates a new run without deleting previous records.
"""

from decimal import Decimal
import io
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.models.chunk import ChunkSourceType, DocumentChunk
from app.models.document import Document, DocumentStatus
from app.models.extraction_run import ExtractionRun, ExtractionRunStatus
from app.models.invoice import Invoice, InvoiceLineItem, ValidationIssue


@pytest.fixture
def sync_session(client: TestClient):
    with client.sync_session_factory() as session:
        yield session


def _create_sample_doc_with_chunk(sync_session) -> str:
    """Helper to seed a document with chunks in the test database."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="invoice_api_test.pdf",
        stored_filename=f"s_{doc_id}.pdf",
        file_path=f"/tmp/s_{doc_id}.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=1024,
        sha256_hash=f"hash_{doc_id}",
        status=DocumentStatus.COMPLETED.value,
        total_chunks=1,
    )
    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        chunk_index=0,
        source_type=ChunkSourceType.PDF_PAGE.value,
        page_number=1,
        content="TAX INVOICE\nInvoice: INV-TEST-001\nTotal: $100.00",
        extraction_method="DIGITAL_TEXT",
    )
    sync_session.add_all([doc, chunk])
    sync_session.commit()
    return str(doc_id)


def test_start_extraction_success(client: TestClient, sync_session, monkeypatch) -> None:
    """21. POST /api/v1/documents/{id}/extract-invoices returns HTTP 202 Accepted."""
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test_key_abc_123")
    monkeypatch.setattr(
        "app.api.v1.endpoints.documents.dispatch_invoice_extraction",
        lambda doc_id, run_id, bg: "inline",
    )

    doc_id = _create_sample_doc_with_chunk(sync_session)

    res = client.post(f"/api/v1/documents/{doc_id}/extract-invoices")
    assert res.status_code == 202
    data = res.json()
    assert "extraction_run_id" in data
    assert data["document_id"] == doc_id
    assert data["status"] == "queued"
    assert data["processing_mode"] in ("inline", "celery")


def test_start_extraction_missing_document(client: TestClient) -> None:
    """22. Missing document returns 404."""
    random_id = uuid.uuid4()
    res = client.post(f"/api/v1/documents/{random_id}/extract-invoices")
    assert res.status_code == 404


def test_start_extraction_llm_disabled(client: TestClient, sync_session, monkeypatch) -> None:
    """23. LLM disabled handling returns 503."""
    monkeypatch.setattr(settings, "LLM_ENABLED", False)

    doc_id = _create_sample_doc_with_chunk(sync_session)

    res = client.post(f"/api/v1/documents/{doc_id}/extract-invoices")
    assert res.status_code == 503
    assert "disabled or unconfigured" in res.json()["detail"]


def test_start_extraction_unprocessed_document(client: TestClient, sync_session, monkeypatch) -> None:
    """Document with 0 chunks returns 400."""
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test_key")

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="unprocessed.pdf",
        stored_filename=f"s_{doc_id}.pdf",
        file_path=f"/tmp/s_{doc_id}.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=1024,
        sha256_hash=f"hash_{doc_id}",
        status=DocumentStatus.UPLOADED.value,
        total_chunks=0,
    )
    sync_session.add(doc)
    sync_session.commit()

    res = client.post(f"/api/v1/documents/{doc_id}/extract-invoices")
    assert res.status_code == 400
    assert "no extracted chunks" in res.json()["detail"].lower()


def test_get_document_invoices_and_historical_run(client: TestClient, sync_session) -> None:
    """24 & 25. Document invoices retrieval and historical run filtering."""
    doc_id = uuid.UUID(_create_sample_doc_with_chunk(sync_session))

    # Seed Run 1 with 1 invoice
    run1 = ExtractionRun(
        document_id=doc_id,
        provider="gemini",
        model_name="flash-1",
        prompt_version="v1",
        status="completed",
    )
    sync_session.add(run1)
    sync_session.commit()

    inv1 = Invoice(
        document_id=doc_id,
        extraction_run_id=run1.id,
        invoice_number="INV-RUN-1",
        total=Decimal("100.00"),
        currency="USD",
    )
    sync_session.add(inv1)
    sync_session.commit()

    # Seed Run 2 with a re-extracted invoice
    run2 = ExtractionRun(
        document_id=doc_id,
        provider="gemini",
        model_name="flash-2",
        prompt_version="v2",
        status="completed",
    )
    sync_session.add(run2)
    sync_session.commit()

    inv2 = Invoice(
        document_id=doc_id,
        extraction_run_id=run2.id,
        invoice_number="INV-RUN-2",
        total=Decimal("200.00"),
        currency="USD",
    )
    sync_session.add(inv2)
    sync_session.commit()

    # 1. Default request returns latest successful run (run2)
    res_latest = client.get(f"/api/v1/documents/{doc_id}/invoices")
    assert res_latest.status_code == 200
    data_latest = res_latest.json()
    assert data_latest["extraction_run_id"] == str(run2.id)
    assert data_latest["total_invoices"] == 1
    assert data_latest["invoices"][0]["invoice_number"] == "INV-RUN-2"

    # 2. Querying specific historical run1 via query parameter
    res_hist = client.get(f"/api/v1/documents/{doc_id}/invoices?extraction_run_id={run1.id}")
    assert res_hist.status_code == 200
    data_hist = res_hist.json()
    assert data_hist["extraction_run_id"] == str(run1.id)
    assert data_hist["total_invoices"] == 1
    assert data_hist["invoices"][0]["invoice_number"] == "INV-RUN-1"


def test_get_individual_invoice(client: TestClient, sync_session) -> None:
    """26. GET /api/v1/invoices/{id} returns full invoice details and line items."""
    doc_id = uuid.UUID(_create_sample_doc_with_chunk(sync_session))

    inv = Invoice(
        document_id=doc_id,
        invoice_number="INV-INDIVIDUAL-001",
        supplier_name="Alpha Supplies",
        customer_name="Beta Retail",
        subtotal=Decimal("80.00"),
        tax=Decimal("20.00"),
        total=Decimal("100.00"),
        currency="USD",
        needs_manual_review=False,
    )
    sync_session.add(inv)
    sync_session.commit()

    item = InvoiceLineItem(
        invoice_id=inv.id,
        description="Office paper",
        quantity=Decimal("4.0000"),
        unit_price=Decimal("20.00"),
        line_total=Decimal("80.00"),
    )
    issue = ValidationIssue(
        invoice_id=inv.id,
        field_name="general",
        issue_type="audit",
        description="Test review note",
    )
    sync_session.add_all([item, issue])
    sync_session.commit()

    res = client.get(f"/api/v1/invoices/{inv.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(inv.id)
    assert data["invoice_number"] == "INV-INDIVIDUAL-001"
    assert data["supplier_name"] == "Alpha Supplies"
    assert float(data["total"]) == 100.00
    assert len(data["line_items"]) == 1
    assert data["line_items"][0]["description"] == "Office paper"
    assert len(data["validation_issues"]) == 1

    # Nonexistent invoice returns 404
    assert client.get(f"/api/v1/invoices/{uuid.uuid4()}").status_code == 404


def test_extraction_history_endpoint(client: TestClient, sync_session) -> None:
    """27. GET /api/v1/documents/{id}/extraction-history."""
    doc_id = uuid.UUID(_create_sample_doc_with_chunk(sync_session))

    run1 = ExtractionRun(
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="completed",
        processing_time_ms=1200,
    )
    run2 = ExtractionRun(
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v2",
        status="failed",
        error_message="Rate limited",
    )
    sync_session.add_all([run1, run2])
    sync_session.commit()

    res = client.get(f"/api/v1/documents/{doc_id}/extraction-history")
    assert res.status_code == 200
    data = res.json()
    assert data["document_id"] == str(doc_id)
    assert data["total_runs"] == 2
    assert len(data["runs"]) == 2
    assert data["runs"][0]["prompt_version"] == "v2"
    assert data["runs"][1]["prompt_version"] == "v1"

    # Nonexistent document returns 404
    assert client.get(f"/api/v1/documents/{uuid.uuid4()}/extraction-history").status_code == 404


def test_extraction_run_status_endpoint(client: TestClient, sync_session) -> None:
    """28. GET /api/v1/extraction-runs/{id}."""
    doc_id = uuid.UUID(_create_sample_doc_with_chunk(sync_session))

    run = ExtractionRun(
        document_id=doc_id,
        provider="gemini",
        model_name="gemini-flash-lite-latest",
        prompt_version="v2",
        status="completed",
        processing_time_ms=1500,
        input_token_count=850,
        output_token_count=210,
        total_contexts=1,
        successful_contexts=1,
    )
    sync_session.add(run)
    sync_session.commit()

    res = client.get(f"/api/v1/extraction-runs/{run.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(run.id)
    assert data["status"] == "completed"
    assert data["processing_time_ms"] == 1500
    assert data["input_token_count"] == 850
    assert data["output_token_count"] == 210

    # Nonexistent run returns 404
    assert client.get(f"/api/v1/extraction-runs/{uuid.uuid4()}").status_code == 404


def test_reextraction_creates_new_run_preserving_previous(client: TestClient, sync_session, monkeypatch) -> None:
    """29. Re-extraction creates a new run without deleting previous run or records."""
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test_key")
    monkeypatch.setattr(
        "app.api.v1.endpoints.documents.dispatch_invoice_extraction",
        lambda doc_id, run_id, bg: "inline",
    )

    doc_id = _create_sample_doc_with_chunk(sync_session)

    # Trigger extraction 1
    res1 = client.post(f"/api/v1/documents/{doc_id}/extract-invoices")
    assert res1.status_code == 202
    run1_id = res1.json()["extraction_run_id"]

    # Trigger extraction 2 (re-extraction)
    res2 = client.post(f"/api/v1/documents/{doc_id}/extract-invoices")
    assert res2.status_code == 202
    run2_id = res2.json()["extraction_run_id"]

    assert run1_id != run2_id

    # Check history: both runs exist!
    hist_res = client.get(f"/api/v1/documents/{doc_id}/extraction-history")
    assert hist_res.status_code == 200
    runs = hist_res.json()["runs"]
    run_ids = {r["id"] for r in runs}
    assert run1_id in run_ids
    assert run2_id in run_ids


@pytest.mark.asyncio
async def test_extraction_service_execution_flow() -> None:
    """Verifies complete ExtractionService lifecycle and metrics persistence with mocked orchestrator."""
    from unittest.mock import AsyncMock
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db.base import Base
    from app.schemas.extraction import (
        DocumentExtractionResponse,
        DocumentType,
        ExtractedField,
        ExtractionStatus,
        InvoiceExtraction,
    )
    from app.services.extraction.service import extraction_service

    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    doc_id = uuid.uuid4()
    run_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    async with session_maker() as session:
        doc = Document(
            id=doc_id,
            original_filename="service_test.pdf",
            stored_filename=f"s_{doc_id}.pdf",
            file_path=f"/tmp/s_{doc_id}.pdf",
            file_type="pdf",
            mime_type="application/pdf",
            file_size=500,
            sha256_hash="hash_srv",
            status=DocumentStatus.COMPLETED.value,
            total_chunks=1,
        )
        chunk = DocumentChunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            source_type=ChunkSourceType.PDF_PAGE.value,
            page_number=1,
            content="TAX INVOICE INV-SERVICE Total $500.00",
            extraction_method="DIGITAL_TEXT",
        )
        run = ExtractionRun(
            id=run_id,
            document_id=doc_id,
            provider="gemini",
            model_name="gemini-flash-lite-latest",
            prompt_version="v2.0",
            status=ExtractionRunStatus.QUEUED.value,
        )
        session.add_all([doc, chunk, run])
        await session.commit()

    # Mock orchestrator
    mock_orch = AsyncMock()
    mock_orch.extract_document_invoices.return_value = DocumentExtractionResponse(
        document_id=doc_id,
        document_type=DocumentType.INVOICE,
        invoices=[
            InvoiceExtraction(
                invoice_number=ExtractedField[str](value="INV-SERVICE"),
                total=ExtractedField[Decimal](value=Decimal("500.00")),
                document_page_start=1,
                document_page_end=1,
            )
        ],
        warnings=[],
        extraction_status=ExtractionStatus.COMPLETED,
        metadata={
            "token_usage": {"prompt_tokens": 120, "candidates_tokens": 45, "total_tokens": 165},
            "contexts_total": 1,
            "contexts_processed": 1,
            "contexts_skipped": 0,
        },
    )

    # Execute service run
    updated_run = await extraction_service.execute_extraction_run(
        document_id=doc_id,
        extraction_run_id=run_id,
        orchestrator=mock_orch,
        session_maker=session_maker,
    )

    assert updated_run.status == "completed"
    assert updated_run.processing_time_ms is not None
    assert updated_run.input_token_count == 120
    assert updated_run.output_token_count == 45
    assert updated_run.successful_contexts == 1

    # Verify invoice was persisted in DB
    async with session_maker() as session:
        invs = (await session.execute(
            select(Invoice).where(Invoice.extraction_run_id == run_id)
        )).scalars().all()
        assert len(invs) == 1
        assert invs[0].invoice_number == "INV-SERVICE"
        assert invs[0].total == Decimal("500.00")

    await test_engine.dispose()
