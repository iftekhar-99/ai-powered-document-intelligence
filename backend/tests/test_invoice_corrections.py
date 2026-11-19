"""
Tests for Invoice Manual Corrections, Audit Logging, Dashboard Metrics, and Celery Safety.
"""

from datetime import date
from decimal import Decimal
import io
import os
import tempfile
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.models.chunk import ChunkSourceType, DocumentChunk
from app.models.document import Document, DocumentStatus
from app.models.extraction_run import ExtractionRun, ExtractionRunStatus
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.invoice_correction import InvoiceCorrectionAudit


@pytest.fixture
def sync_session(client: TestClient):
    with client.sync_session_factory() as session:
        yield session


def _seed_test_invoice(sync_session, invoice_number="INV-2026-001", total=Decimal("150.00"), needs_review=False) -> Invoice:
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="sample_invoice.pdf",
        stored_filename=f"stored_{doc_id}.pdf",
        file_path=f"/tmp/stored_{doc_id}.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=1024,
        sha256_hash=f"hash_{doc_id}",
        status=DocumentStatus.COMPLETED.value,
        total_chunks=1,
    )
    run = ExtractionRun(
        id=uuid.uuid4(),
        document_id=doc_id,
        provider="gemini",
        model_name="gemini-flash-lite-latest",
        prompt_version="1.0",
        status=ExtractionRunStatus.COMPLETED.value,
        total_contexts=1,
        successful_contexts=1,
    )
    inv = Invoice(
        id=uuid.uuid4(),
        document_id=doc_id,
        extraction_run_id=run.id,
        invoice_number=invoice_number,
        invoice_date=date(2026, 11, 1),
        supplier_name="Acme Corp",
        customer_name="Global Tech Ltd",
        subtotal=Decimal("130.00"),
        tax=Decimal("20.00"),
        total=total,
        currency="USD",
        needs_manual_review=needs_review,
        is_manually_corrected=False,
    )
    li1 = InvoiceLineItem(
        id=uuid.uuid4(),
        invoice_id=inv.id,
        description="Widget A",
        quantity=Decimal("2.00"),
        unit_price=Decimal("50.00"),
        tax=Decimal("10.00"),
        line_total=Decimal("100.00"),
    )
    li2 = InvoiceLineItem(
        id=uuid.uuid4(),
        invoice_id=inv.id,
        description="Widget B",
        quantity=Decimal("1.00"),
        unit_price=Decimal("30.00"),
        tax=Decimal("10.00"),
        line_total=Decimal("30.00"),
    )
    sync_session.add_all([doc, run, inv, li1, li2])
    sync_session.commit()
    return inv


def test_list_invoices_and_filters(client: TestClient, sync_session) -> None:
    """1. Test listing invoices with pagination, search, and review/corrected filters."""
    inv1 = _seed_test_invoice(sync_session, invoice_number="INV-FILTER-001", needs_review=True)
    inv2 = _seed_test_invoice(sync_session, invoice_number="INV-FILTER-002", needs_review=False)

    # List all
    res = client.get("/api/v1/invoices")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2
    assert any(item["id"] == str(inv1.id) for item in data["items"])

    # Search filter
    res_search = client.get("/api/v1/invoices?search=FILTER-001")
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["invoice_number"] == "INV-FILTER-001"

    # Needs review filter
    res_review = client.get("/api/v1/invoices?needs_review=true")
    assert res_review.status_code == 200
    review_data = res_review.json()
    assert all(item["needs_manual_review"] is True for item in review_data["items"])


def test_update_invoice_header_and_totals(client: TestClient, sync_session) -> None:
    """2. PATCH /api/v1/invoices/{id} updates fields, sets is_manually_corrected, and logs audit."""
    inv = _seed_test_invoice(sync_session, invoice_number="INV-ORIG-100")

    payload = {
        "invoice_number": "INV-CORRECTED-100",
        "supplier_name": "Acme Global Solutions",
        "total": 199.99,
        "reason": "Corrected legal supplier name and added missing shipping fee",
        "corrected_by": "alice_auditor",
    }
    res = client.patch(f"/api/v1/invoices/{inv.id}", json=payload)
    assert res.status_code == 200
    updated = res.json()
    assert updated["invoice_number"] == "INV-CORRECTED-100"
    assert updated["supplier_name"] == "Acme Global Solutions"
    assert float(updated["total"]) == 199.99
    assert updated["is_manually_corrected"] is True

    # Verify audit entry exists
    audits_res = client.get(f"/api/v1/invoices/{inv.id}/corrections")
    assert audits_res.status_code == 200
    audits = audits_res.json()
    assert len(audits) == 1
    audit = audits[0]
    assert audit["correction_type"] == "HEADER_UPDATE"
    assert "invoice_number" in audit["changed_fields"]
    assert audit["previous_values"]["invoice_number"] == "INV-ORIG-100"
    assert audit["new_values"]["invoice_number"] == "INV-CORRECTED-100"
    assert audit["reason"] == "Corrected legal supplier name and added missing shipping fee"
    assert audit["corrected_by"] == "alice_auditor"


def test_update_invoice_validation_failures(client: TestClient, sync_session) -> None:
    """3. Verify rejection of blank reason and negative amounts."""
    inv = _seed_test_invoice(sync_session)

    # Empty reason
    res_empty_reason = client.patch(
        f"/api/v1/invoices/{inv.id}",
        json={"total": 120.00, "reason": "   "},
    )
    assert res_empty_reason.status_code == 422

    # Negative total
    res_neg = client.patch(
        f"/api/v1/invoices/{inv.id}",
        json={"total": -50.00, "reason": "Negative discount applied"},
    )
    assert res_neg.status_code == 422


def test_update_line_item(client: TestClient, sync_session) -> None:
    """4. PATCH /api/v1/invoices/{id}/line-items/{li_id} updates line item and audits."""
    inv = _seed_test_invoice(sync_session)
    li = inv.line_items[0]

    payload = {
        "description": "Premium Heavy Duty Widget A",
        "unit_price": 55.00,
        "line_total": 110.00,
        "reason": "Updated specification description per packing slip",
        "corrected_by": "bob_reviewer",
    }
    res = client.patch(f"/api/v1/invoices/{inv.id}/line-items/{li.id}", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["description"] == "Premium Heavy Duty Widget A"
    assert float(data["unit_price"]) == 55.00
    assert float(data["line_total"]) == 110.00

    # Verify audit
    audits_res = client.get(f"/api/v1/invoices/{inv.id}/corrections")
    assert audits_res.status_code == 200
    audits = audits_res.json()
    assert len(audits) >= 1
    assert audits[0]["correction_type"] == "LINE_ITEM_UPDATE"


def test_update_line_item_cross_invoice_mismatch(client: TestClient, sync_session) -> None:
    """5. Attempting to update a line item belonging to another invoice returns 400 Bad Request."""
    inv1 = _seed_test_invoice(sync_session, invoice_number="INV-A")
    inv2 = _seed_test_invoice(sync_session, invoice_number="INV-B")
    li_of_inv2 = inv2.line_items[0]

    res = client.patch(
        f"/api/v1/invoices/{inv1.id}/line-items/{li_of_inv2.id}",
        json={"description": "Hacked item", "reason": "Unauthorized mismatch"},
    )
    assert res.status_code == 400
    assert "does not belong" in res.json()["detail"]


def test_create_and_delete_line_item(client: TestClient, sync_session) -> None:
    """6. Add new line item then delete it, verifying audits for each action."""
    inv = _seed_test_invoice(sync_session)

    # 1. Add line item
    add_payload = {
        "description": "Consulting & Installation Service",
        "quantity": 1.0,
        "unit_price": 75.0,
        "tax": 0.0,
        "line_total": 75.0,
        "reason": "Added service fee row omitted by OCR",
        "corrected_by": "carol_auditor",
    }
    res_add = client.post(f"/api/v1/invoices/{inv.id}/line-items", json=add_payload)
    assert res_add.status_code == 201
    created_item = res_add.json()
    created_id = created_item["id"]
    assert created_item["description"] == "Consulting & Installation Service"

    # Verify ADD audit
    audits1 = client.get(f"/api/v1/invoices/{inv.id}/corrections").json()
    assert any(a["correction_type"] == "LINE_ITEM_ADD" for a in audits1)

    # 2. Delete line item
    res_del = client.delete(
        f"/api/v1/invoices/{inv.id}/line-items/{created_id}?reason=Duplicate%20service%20entry&corrected_by=carol_auditor"
    )
    assert res_del.status_code == 200

    # Verify DELETE audit
    audits2 = client.get(f"/api/v1/invoices/{inv.id}/corrections").json()
    delete_audit = next(a for a in audits2 if a["correction_type"] == "LINE_ITEM_DELETE")
    assert delete_audit["previous_values"]["description"] == "Consulting & Installation Service"
    assert delete_audit["reason"] == "Duplicate service entry"


def test_dashboard_metrics_endpoint(client: TestClient, sync_session) -> None:
    """7. GET /api/v1/dashboard/metrics returns KPI counts, recent runs, and recent corrections."""
    inv = _seed_test_invoice(sync_session, invoice_number="INV-METRIC-1")

    # Add a correction
    client.patch(
        f"/api/v1/invoices/{inv.id}",
        json={"total": 250.00, "reason": "Metric test adjustment"},
    )

    res = client.get("/api/v1/dashboard/metrics")
    assert res.status_code == 200
    metrics = res.json()

    assert "total_documents" in metrics
    assert "processed_documents" in metrics
    assert "total_invoices" in metrics
    assert "needs_review_invoices" in metrics
    assert "manually_corrected_invoices" in metrics
    assert "recent_extraction_runs" in metrics
    assert "recent_corrections" in metrics

    assert metrics["total_invoices"] >= 1
    assert metrics["manually_corrected_invoices"] >= 1
    assert len(metrics["recent_corrections"]) >= 1


def test_document_file_endpoint(client: TestClient, sync_session) -> None:
    """8. GET /api/v1/documents/{id}/file serves file or returns 404."""
    # Create temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 sample pdf content")
        temp_path = f.name

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="sample_view.pdf",
        stored_filename=f"stored_{doc_id}.pdf",
        file_path=temp_path,
        file_type="pdf",
        mime_type="application/pdf",
        file_size=25,
        sha256_hash="dummy_hash",
        status=DocumentStatus.COMPLETED.value,
        total_chunks=1,
    )
    sync_session.add(doc)
    sync_session.commit()

    try:
        res = client.get(f"/api/v1/documents/{doc_id}/file")
        assert res.status_code == 200
        assert res.content == b"%PDF-1.4 sample pdf content"
        assert res.headers["content-type"] == "application/pdf"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_celery_dispatch_failure_handling(client: TestClient, sync_session, monkeypatch) -> None:
    """9. When PROCESSING_MODE=celery and dispatch raises, returns HTTP 503 and marks run failed."""
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test_key_123")
    monkeypatch.setattr(settings, "PROCESSING_MODE", "celery")

    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename="celery_fail.pdf",
        stored_filename=f"stored_{doc_id}.pdf",
        file_path=f"/tmp/stored_{doc_id}.pdf",
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
        content="Invoice: CELERY-FAIL-01",
        extraction_method="DIGITAL_TEXT",
    )
    sync_session.add_all([doc, chunk])
    sync_session.commit()

    def _mock_failing_dispatch(document_id, extraction_run_id, background_tasks=None):
        raise RuntimeError("Redis connection refused on port 6379")

    monkeypatch.setattr(
        "app.api.v1.endpoints.documents.dispatch_invoice_extraction",
        _mock_failing_dispatch,
    )

    res = client.post(f"/api/v1/documents/{doc_id}/extract-invoices")
    assert res.status_code == 503
    assert "Unable to dispatch extraction worker" in res.json()["detail"]

    # Verify run status is failed in database
    run = sync_session.scalar(
        select(ExtractionRun).where(ExtractionRun.document_id == doc_id)
    )
    assert run is not None
    assert run.status == ExtractionRunStatus.FAILED.value
    assert "Redis connection refused" in run.error_message
