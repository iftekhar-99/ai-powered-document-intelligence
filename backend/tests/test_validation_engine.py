"""
Comprehensive tests for the Financial Data Validation Engine and Duplicate Invoice Detection (Task 4G).
"""

from datetime import date
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.models.document import Document, DocumentStatus
from app.models.extraction_run import ExtractionRun, ExtractionRunStatus
from app.models.invoice import Invoice, InvoiceLineItem, ValidationIssue
from app.services.validation.rules import ValidationRuleEngine
from app.services.validation.duplicate_detector import (
    DuplicateInvoiceDetector,
    normalize_invoice_number,
    normalize_party_name,
)


@pytest.fixture
def sync_session(client: TestClient):
    with client.sync_session_factory() as session:
        yield session


def _create_doc(sync_session, filename="doc.pdf") -> Document:
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        original_filename=filename,
        stored_filename=f"stored_{doc_id}.pdf",
        file_path=f"/tmp/stored_{doc_id}.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=2048,
        sha256_hash=f"hash_{doc_id}",
        status=DocumentStatus.COMPLETED.value,
        total_chunks=1,
    )
    sync_session.add(doc)
    sync_session.commit()
    return doc


def _create_invoice(
    sync_session,
    doc_id: uuid.UUID,
    invoice_number="INV-2026-001",
    supplier="Acme Corp",
    customer="Global Tech",
    subtotal=Decimal("100.00"),
    tax=Decimal("10.00"),
    total=Decimal("110.00"),
    currency="USD",
    invoice_date=date(2026, 11, 1),
    line_items=None,
) -> Invoice:
    inv = Invoice(
        id=uuid.uuid4(),
        document_id=doc_id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        supplier_name=supplier,
        customer_name=customer,
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency=currency,
        needs_manual_review=False,
        is_manually_corrected=False,
    )
    sync_session.add(inv)
    sync_session.commit()

    if line_items:
        for li in line_items:
            li.invoice_id = inv.id
            sync_session.add(li)
        sync_session.commit()

    sync_session.refresh(inv)
    return inv


def test_normalization_functions():
    """Verify invoice number and supplier normalization utilities."""
    assert normalize_invoice_number("INV-2026-001") == "2026001" or normalize_invoice_number("INV-2026-001") == "INV2026001"
    assert normalize_invoice_number("  inv # 456 / A ") == "INV456A"
    assert normalize_invoice_number("") == ""
    assert normalize_invoice_number(None) == ""

    assert normalize_party_name("Acme Corporation, Inc.") == "acme"
    assert normalize_party_name("Global Supplies LLC") == "global supplies"
    assert normalize_party_name("Siemens GMBH") == "siemens"
    assert normalize_party_name("Stark Industries Co.") == "stark industries"


def test_required_fields_validation():
    """Test required field rules for missing mandatory headers."""
    engine = ValidationRuleEngine()

    # Incomplete invoice missing number, total, supplier, date, currency
    inv = Invoice(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        invoice_number=None,
        total=None,
        supplier_name="   ",
        invoice_date=None,
        currency=None,
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
    )

    issues = engine.validate_required_fields(inv)
    issue_types = {i.issue_type: i for i in issues}

    assert "missing_invoice_number" in issue_types
    assert issue_types["missing_invoice_number"].severity == "error"

    assert "missing_total_amount" in issue_types
    assert issue_types["missing_total_amount"].severity == "error"

    assert "missing_supplier_name" in issue_types
    assert issue_types["missing_supplier_name"].severity == "warning"

    assert "missing_invoice_date" in issue_types
    assert issue_types["missing_invoice_date"].severity == "warning"

    assert "missing_currency" in issue_types
    assert issue_types["missing_currency"].severity == "warning"


def test_financial_arithmetic_tolerance():
    """Test arithmetic checks: exact match, within tolerance, warning, and error."""
    engine = ValidationRuleEngine(rounding_tolerance=Decimal("0.01"))

    # Case 1: Exact arithmetic match (100.00 + 10.00 == 110.00)
    inv_clean = Invoice(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal("110.00"),
    )
    issues_clean = engine.validate_financial_arithmetic(inv_clean)
    assert len(issues_clean) == 0

    # Case 2: Rounding discrepancy of 0.01 (within tolerance) -> passes!
    inv_tol = Invoice(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal("110.01"),
    )
    issues_tol = engine.validate_financial_arithmetic(inv_tol)
    assert len(issues_tol) == 0

    # Case 3: Minor discrepancy of 0.05 (diff <= 1.00) -> warning
    inv_minor = Invoice(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal("110.05"),
    )
    issues_minor = engine.validate_financial_arithmetic(inv_minor)
    assert len(issues_minor) == 1
    assert issues_minor[0].issue_type == "subtotal_tax_total_mismatch"
    assert issues_minor[0].severity == "warning"

    # Case 4: Large discrepancy of 25.00 -> error
    inv_major = Invoice(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal("135.00"),
    )
    issues_major = engine.validate_financial_arithmetic(inv_major)
    assert len(issues_major) == 1
    assert issues_major[0].issue_type == "subtotal_tax_total_mismatch"
    assert issues_major[0].severity == "error"

    # Case 5: Negative total amount -> error
    inv_neg = Invoice(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        total=Decimal("-50.00"),
    )
    issues_neg = engine.validate_financial_arithmetic(inv_neg)
    assert any(i.issue_type == "negative_total_amount" for i in issues_neg)


def test_line_items_validation():
    """Test itemized line items: missing description, negative values, line total math, and duplicates."""
    engine = ValidationRuleEngine(rounding_tolerance=Decimal("0.01"))

    li_clean = InvoiceLineItem(
        id=uuid.uuid4(),
        description="Widget Alpha",
        quantity=Decimal("2.00"),
        unit_price=Decimal("25.00"),
        line_total=Decimal("50.00"),
    )

    li_math_error = InvoiceLineItem(
        id=uuid.uuid4(),
        description="Widget Beta",
        quantity=Decimal("3.00"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("40.00"),  # Expected 30.00
    )

    li_missing_desc = InvoiceLineItem(
        id=uuid.uuid4(),
        description="   ",
        quantity=Decimal("1.00"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("10.00"),
    )

    li_neg_qty = InvoiceLineItem(
        id=uuid.uuid4(),
        description="Discount row",
        quantity=Decimal("-1.00"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("-10.00"),
    )

    li_dup_1 = InvoiceLineItem(
        id=uuid.uuid4(),
        description="Consulting Hour",
        quantity=Decimal("1.00"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )

    li_dup_2 = InvoiceLineItem(
        id=uuid.uuid4(),
        description="Consulting Hour",
        quantity=Decimal("1.00"),
        unit_price=Decimal("100.00"),
        line_total=Decimal("100.00"),
    )

    inv = Invoice(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        subtotal=Decimal("290.00"),
        line_items=[li_clean, li_math_error, li_missing_desc, li_neg_qty, li_dup_1, li_dup_2],
    )

    issues = engine.validate_line_items(inv)
    issue_types = {i.issue_type for i in issues}

    assert "line_item_math_mismatch" in issue_types
    assert "missing_line_description" in issue_types
    assert "negative_line_quantity" in issue_types
    assert "duplicate_line_item" in issue_types


def test_duplicate_detection_distinguishes_different_suppliers(client: TestClient, sync_session):
    """
    CRITICAL: Invoices sharing the same invoice number (e.g. INV-001) but from DIFFERENT suppliers
    MUST NOT be flagged as duplicates.
    """
    doc1 = _create_doc(sync_session, filename="acme_bill.pdf")
    doc2 = _create_doc(sync_session, filename="stark_bill.pdf")

    inv1 = _create_invoice(
        sync_session,
        doc_id=doc1.id,
        invoice_number="INV-2026-777",
        supplier="Acme Corporation Ltd",
        total=Decimal("500.00"),
    )

    inv2 = _create_invoice(
        sync_session,
        doc_id=doc2.id,
        invoice_number="INV-2026-777",
        supplier="Stark Industries Co",
        total=Decimal("500.00"),
    )

    # Trigger duplicate scan on inv1 via API
    res = client.get(f"/api/v1/invoices/{inv1.id}/duplicates")
    assert res.status_code == 200
    dups = res.json()
    assert len(dups) == 0, "Distinct suppliers sharing an invoice number must NOT be flagged as duplicates"


def test_exact_duplicate_invoice_detection(client: TestClient, sync_session):
    """Verify that identical invoices across different documents are detected as exact duplicates."""
    doc1 = _create_doc(sync_session, filename="original_invoice.pdf")
    doc2 = _create_doc(sync_session, filename="reuploaded_invoice.pdf")

    inv1 = _create_invoice(
        sync_session,
        doc_id=doc1.id,
        invoice_number="INV-DUP-100",
        supplier="Apex Supplies LLC",
        total=Decimal("1250.00"),
        currency="USD",
        invoice_date=date(2026, 11, 5),
    )

    inv2 = _create_invoice(
        sync_session,
        doc_id=doc2.id,
        invoice_number="inv # dup-100",
        supplier="Apex Supplies",
        total=Decimal("1250.00"),
        currency="USD",
        invoice_date=date(2026, 11, 5),
    )

    # Validate inv2 via API
    res = client.post(f"/api/v1/invoices/{inv2.id}/validate")
    assert res.status_code == 200
    summary = res.json()

    assert len(summary["duplicates_detected"]) == 1
    dup_match = summary["duplicates_detected"][0]
    assert dup_match["match_type"] == "exact_duplicate"
    assert dup_match["invoice_id"] == str(inv1.id)

    # Check that an error-severity duplicate issue was recorded
    exact_issues = [i for i in summary["issues"] if i["issue_type"] == "duplicate_invoice_exact"]
    assert len(exact_issues) == 1
    assert exact_issues[0]["severity"] == "error"
    assert summary["needs_manual_review"] is True


def test_idempotent_validation_and_lifecycle(client: TestClient, sync_session):
    """
    Verify validation idempotence and resolution lifecycle:
    1. Repeated validations do not duplicate issue records.
    2. When discrepancy is fixed, issue is automatically marked resolved=True, resolved_by='system_validation'.
    """
    doc = _create_doc(sync_session, filename="bad_invoice.pdf")
    inv = _create_invoice(
        sync_session,
        doc_id=doc.id,
        invoice_number=None,  # Missing number
        total=Decimal("100.00"),
    )

    # Run 1
    res1 = client.post(f"/api/v1/invoices/{inv.id}/validate")
    assert res1.status_code == 200
    s1 = res1.json()
    assert s1["unresolved_errors"] >= 1
    issues_first_run = s1["issues"]

    # Run 2 (without changes)
    res2 = client.post(f"/api/v1/invoices/{inv.id}/validate")
    assert res2.status_code == 200
    s2 = res2.json()
    assert len(s2["issues"]) == len(issues_first_run), "Repeated validation must not create duplicate issue records"

    # Now fix the missing invoice_number via manual header correction
    patch_res = client.patch(
        f"/api/v1/invoices/{inv.id}",
        json={
            "invoice_number": "INV-RESOLVED-001",
            "reason": "Populated missing invoice number from header inspection",
        },
    )
    assert patch_res.status_code == 200

    # Inspect validation issues after fix
    issues_res = client.get(f"/api/v1/invoices/{inv.id}/validation-issues")
    assert issues_res.status_code == 200
    issues_after_fix = issues_res.json()

    num_issue = next(i for i in issues_after_fix if i["issue_type"] == "missing_invoice_number")
    assert num_issue["resolved"] is True
    assert num_issue["resolved_by"] == "system_validation"
    assert "no longer detected" in num_issue["resolution_notes"]


def test_manual_issue_resolution_and_reopen_api(client: TestClient, sync_session):
    """Verify operator manual resolution and reopening of validation issues via REST API."""
    doc = _create_doc(sync_session, filename="tax_audit.pdf")
    inv = _create_invoice(
        sync_session,
        doc_id=doc.id,
        invoice_number="INV-TAX-001",
        subtotal=Decimal("100.00"),
        tax=Decimal("10.00"),
        total=Decimal("110.50"),  # 0.50 mismatch -> warning
    )

    # Trigger validation
    val_res = client.post(f"/api/v1/invoices/{inv.id}/validate")
    assert val_res.status_code == 200
    summary = val_res.json()
    assert summary["unresolved_warnings"] == 1
    tax_issue = next(i for i in summary["issues"] if i["issue_type"] == "subtotal_tax_total_mismatch")

    # Operator resolves issue
    resolve_res = client.patch(
        f"/api/v1/validation-issues/{tax_issue['id']}/resolve",
        json={
            "resolved_by": "auditor_elena",
            "resolution_notes": "Verified $0.50 discrepancy corresponds to local environmental fee",
        },
    )
    assert resolve_res.status_code == 200
    resolved_data = resolve_res.json()
    assert resolved_data["resolved"] is True
    assert resolved_data["resolved_by"] == "auditor_elena"
    assert "environmental fee" in resolved_data["resolution_notes"]

    # Verify invoice needs_manual_review is cleared
    inv_res = client.get(f"/api/v1/invoices/{inv.id}")
    assert inv_res.json()["needs_manual_review"] is False

    # Operator reopens issue
    reopen_res = client.patch(
        f"/api/v1/validation-issues/{tax_issue['id']}/reopen",
        json={
            "reopened_by": "supervisor_mark",
            "reopen_notes": "Environmental fee requires itemized line entry rather than variance acceptance",
        },
    )
    assert reopen_res.status_code == 200
    reopened_data = reopen_res.json()
    assert reopened_data["resolved"] is False

    # Verify invoice needs_manual_review is set back to True
    inv_res2 = client.get(f"/api/v1/invoices/{inv.id}")
    assert inv_res2.json()["needs_manual_review"] is True


def test_system_wide_validation_issues_query(client: TestClient, sync_session):
    """Verify system-wide validation issues listing endpoint with filtering."""
    doc = _create_doc(sync_session, filename="system_wide.pdf")
    inv = _create_invoice(
        sync_session,
        doc_id=doc.id,
        invoice_number="INV-SYS-001",
        total=Decimal("-10.00"),  # Negative total -> error
    )
    client.post(f"/api/v1/invoices/{inv.id}/validate")

    # Query all errors
    res = client.get("/api/v1/validation-issues?severity=error")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert all(i["severity"] == "error" for i in data["items"])
