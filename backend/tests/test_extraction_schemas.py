"""
Unit tests for invoice extraction Pydantic v2 schemas.
Covers:
1. Valid invoice extraction schema.
2. Missing invoice fields (defaults to None, no artificial values).
3. Null monetary values (subtotal, tax, total remain null).
4. Decimal parsing (string, currency strings, float, Decimal, invalid strings).
5. Invalid confidence values (< 0.0 or > 1.0).
6. Evidence metadata (SourceEvidence linking).
7. Multiple line items.
8. Multiple invoices within DocumentExtractionResponse.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.extraction import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    ExtractionStatus,
    InvoiceExtraction,
    InvoiceLineItemExtraction,
    SourceEvidence,
)


def test_1_valid_invoice_extraction_schema():
    """Test creating and validating a complete valid InvoiceExtraction."""
    chunk_id = uuid4()
    evidence = SourceEvidence(
        source_chunk_id=chunk_id,
        page_number=1,
        relevant_text="Invoice #INV-2026-001 Date: 2026-01-15 Total: USD 1,500.00",
    )

    line_item = InvoiceLineItemExtraction(
        description=ExtractedField(value="Cloud Architecture Consulting", confidence=0.98),
        quantity=ExtractedField(value=Decimal("10"), confidence=0.99),
        unit_price=ExtractedField(value=Decimal("150.00"), confidence=0.98),
        tax=ExtractedField(value=Decimal("0.00"), confidence=0.95),
        line_total=ExtractedField(value=Decimal("1500.00"), confidence=0.99),
    )

    invoice = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-2026-001", confidence=0.99, evidence=[evidence]),
        invoice_date=ExtractedField(value="2026-01-15", confidence=0.95),
        supplier_name=ExtractedField(value="Acme Cloud Solutions Inc", confidence=0.97),
        customer_name=ExtractedField(value="Global Finance Corp", confidence=0.96),
        subtotal=ExtractedField(value=Decimal("1500.00"), confidence=0.98),
        tax=ExtractedField(value=Decimal("0.00"), confidence=0.95),
        total=ExtractedField(value=Decimal("1500.00"), confidence=0.99),
        currency=ExtractedField(value="USD", confidence=0.99),
        line_items=[line_item],
        overall_confidence=0.97,
        needs_manual_review=False,
        review_reasons=[],
        document_page_start=1,
        document_page_end=1,
    )

    assert invoice.invoice_number.value == "INV-2026-001"
    assert invoice.total.value == Decimal("1500.00")
    assert invoice.currency.value == "USD"
    assert len(invoice.line_items) == 1
    assert invoice.line_items[0].description.value == "Cloud Architecture Consulting"
    assert invoice.line_items[0].line_total.value == Decimal("1500.00")
    assert invoice.overall_confidence == 0.97
    assert invoice.needs_manual_review is False


def test_2_missing_invoice_fields():
    """Missing invoice fields must remain null and not create artificial defaults."""
    invoice = InvoiceExtraction()

    assert invoice.invoice_number.value is None
    assert invoice.invoice_date.value is None
    assert invoice.supplier_name.value is None
    assert invoice.customer_name.value is None
    assert invoice.subtotal.value is None
    assert invoice.tax.value is None
    assert invoice.total.value is None
    assert invoice.currency.value is None
    assert invoice.line_items == []
    assert invoice.overall_confidence is None
    assert invoice.needs_manual_review is False
    assert invoice.review_reasons == []


def test_3_null_monetary_values():
    """Verify that financial fields remain explicitly None when not present."""
    item = InvoiceLineItemExtraction(
        description=ExtractedField(value="Consulting item"),
        unit_price=ExtractedField(value=None),
        line_total=ExtractedField(value=None),
    )
    assert item.unit_price.value is None
    assert item.line_total.value is None
    assert item.quantity.value is None

    invoice = InvoiceExtraction(
        subtotal=ExtractedField(value=None),
        tax=ExtractedField(value=None),
        total=ExtractedField(value=None),
    )
    assert invoice.subtotal.value is None
    assert invoice.tax.value is None
    assert invoice.total.value is None


def test_4_decimal_parsing():
    """Verify robust parsing of numeric, string, currency, and float values into Decimal."""
    # Standard string
    field_str = ExtractedField[Decimal](value="123.45")
    assert field_str.value == Decimal("123.45")

    # Currency formatted string with symbols and commas
    field_currency = ExtractedField[Decimal](value="$1,234.56")
    assert field_currency.value == Decimal("1234.56")

    # Euro symbol
    field_euro = ExtractedField[Decimal](value="€ 999.90")
    assert field_euro.value == Decimal("999.90")

    # Float conversion
    field_float = ExtractedField[Decimal](value=456.78)
    assert field_float.value == Decimal("456.78")

    # Native Decimal
    field_dec = ExtractedField[Decimal](value=Decimal("789.00"))
    assert field_dec.value == Decimal("789.00")

    # Empty string should resolve to None
    field_empty = ExtractedField[Decimal](value="")
    assert field_empty.value is None

    # Invalid string should raise ValidationError
    with pytest.raises(ValidationError):
        ExtractedField[Decimal](value="NOT_A_NUMBER")


def test_5_invalid_confidence_values():
    """Estimated confidence must be between 0.0 and 1.0."""
    # Valid boundaries
    f_zero = ExtractedField[str](value="Test", confidence=0.0)
    assert f_zero.confidence == 0.0

    f_one = ExtractedField[str](value="Test", confidence=1.0)
    assert f_one.confidence == 1.0

    # Over 1.0
    with pytest.raises(ValidationError):
        ExtractedField[str](value="Test", confidence=1.05)

    # Negative confidence
    with pytest.raises(ValidationError):
        ExtractedField[str](value="Test", confidence=-0.1)

    # Overall confidence on invoice validation
    with pytest.raises(ValidationError):
        InvoiceExtraction(overall_confidence=1.5)

    with pytest.raises(ValidationError):
        InvoiceExtraction(overall_confidence=-0.01)


def test_6_evidence_metadata():
    """Verify SourceEvidence metadata fields and linking."""
    chunk_id = uuid4()
    evidence = SourceEvidence(
        source_chunk_id=chunk_id,
        page_number=3,
        sheet_name="Summary",
        row_start=10,
        row_end=12,
        relevant_text="Subtotal: $4,500.00",
    )

    assert evidence.source_chunk_id == chunk_id
    assert evidence.page_number == 3
    assert evidence.sheet_name == "Summary"
    assert evidence.row_start == 10
    assert evidence.row_end == 12
    assert "Subtotal" in evidence.relevant_text

    field = ExtractedField[Decimal](
        value=Decimal("4500.00"),
        raw_value="$4,500.00",
        confidence=0.96,
        evidence=[evidence],
    )
    assert len(field.evidence) == 1
    assert field.evidence[0].source_chunk_id == chunk_id


def test_7_multiple_line_items():
    """Verify extraction and serialization of multiple line items."""
    items = [
        InvoiceLineItemExtraction(
            description=ExtractedField(value=f"Item {i}"),
            quantity=ExtractedField(value=Decimal(str(i))),
            unit_price=ExtractedField(value=Decimal("50.00")),
            line_total=ExtractedField(value=Decimal(str(i * 50))),
        )
        for i in range(1, 5)
    ]

    invoice = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-MULTI-01"),
        line_items=items,
        total=ExtractedField(value=Decimal("500.00")),
    )

    assert len(invoice.line_items) == 4
    assert invoice.line_items[0].description.value == "Item 1"
    assert invoice.line_items[3].line_total.value == Decimal("200")


def test_8_multiple_invoices_in_document():
    """Verify DocumentExtractionResponse supporting multiple invoices in a single document."""
    doc_id = uuid4()
    inv1 = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-PAGE-1"),
        total=ExtractedField(value=Decimal("100.00")),
        document_page_start=1,
        document_page_end=1,
    )
    inv2 = InvoiceExtraction(
        invoice_number=ExtractedField(value="INV-PAGE-2"),
        total=ExtractedField(value=Decimal("200.00")),
        document_page_start=2,
        document_page_end=2,
    )

    response = DocumentExtractionResponse(
        document_id=doc_id,
        document_type=DocumentType.INVOICE,
        invoices=[inv1, inv2],
        warnings=["Multi-invoice document detected"],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    assert response.document_id == doc_id
    assert response.document_type == DocumentType.INVOICE
    assert len(response.invoices) == 2
    assert response.invoices[0].invoice_number.value == "INV-PAGE-1"
    assert response.invoices[1].invoice_number.value == "INV-PAGE-2"
    assert response.extraction_status == ExtractionStatus.COMPLETED
    assert len(response.warnings) == 1
