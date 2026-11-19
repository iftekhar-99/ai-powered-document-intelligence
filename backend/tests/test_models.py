import datetime
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.base import Base
from app.models import (
    Document,
    DocumentStatus,
    Invoice,
    InvoiceLineItem,
    ProcessingEvent,
    ValidationIssue,
)


def test_database_model_creation() -> None:
    """Verify that all required models can be created with their required columns."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        doc = Document(
            original_filename="sample_invoice.pdf",
            stored_filename="uuid-sample.pdf",
            file_path="/var/uploads/uuid-sample.pdf",
            file_type="pdf",
            mime_type="application/pdf",
            file_size=10240,
            sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            status=DocumentStatus.UPLOADED.value,
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        assert isinstance(doc.id, uuid.UUID)
        assert doc.original_filename == "sample_invoice.pdf"
        assert doc.status == "uploaded"
        assert doc.uploaded_at is not None
        assert doc.processed_at is None
        assert doc.page_count is None

        # Create Invoice associated with document
        inv = Invoice(
            document_id=doc.id,
            invoice_number="INV-2026-999",
            invoice_date=datetime.date(2026, 11, 15),
            supplier_name="Acme Corp",
            customer_name="Global Tech",
            subtotal=Decimal("1000.00"),
            tax=Decimal("200.00"),
            total=Decimal("1200.00"),
            currency="USD",
            extraction_method="test",
        )
        session.add(inv)
        session.commit()
        session.refresh(inv)

        assert isinstance(inv.id, uuid.UUID)
        assert inv.document_id == doc.id
        assert inv.total == Decimal("1200.00")

        # Create Line Item
        item = InvoiceLineItem(
            invoice_id=inv.id,
            description="Cloud Architecture Consulting",
            quantity=Decimal("10.0000"),
            unit_price=Decimal("100.00"),
            tax=Decimal("20.00"),
            line_total=Decimal("1200.00"),
        )
        session.add(item)

        # Create Validation Issue
        issue = ValidationIssue(
            invoice_id=inv.id,
            field_name="total",
            issue_type="calculation_warning",
            severity="warning",
            description="Subtotal + Tax matches total perfectly",
            resolved=False,
        )
        session.add(issue)

        # Create Processing Event
        event = ProcessingEvent(
            document_id=doc.id,
            event_type="upload_completed",
            message="Uploaded in test environment",
        )
        session.add(event)
        session.commit()

        # Query and assert presence
        persisted_item = session.scalar(select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == inv.id))
        assert persisted_item is not None
        assert persisted_item.line_total == Decimal("1200.00")

        persisted_issue = session.scalar(select(ValidationIssue).where(ValidationIssue.invoice_id == inv.id))
        assert persisted_issue is not None
        assert persisted_issue.field_name == "total"

        persisted_event = session.scalar(select(ProcessingEvent).where(ProcessingEvent.document_id == doc.id))
        assert persisted_event is not None
        assert persisted_event.event_type == "upload_completed"


def test_database_relationships_and_cascades() -> None:
    """Verify bidirectional relationships and cascade deletion."""
    engine = create_engine("sqlite:///:memory:")
    # Enable foreign keys for SQLite in memory
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        doc = Document(
            original_filename="cascade_test.pdf",
            stored_filename="cascade.pdf",
            file_path="/tmp/cascade.pdf",
            file_type="pdf",
            mime_type="application/pdf",
            file_size=512,
            sha256_hash="hash123456789",
            status="uploaded",
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        inv = Invoice(
            document_id=doc.id,
            invoice_number="INV-CASCADE",
            total=Decimal("500.00"),
        )
        session.add(inv)
        session.commit()
        session.refresh(inv)

        item = InvoiceLineItem(
            invoice_id=inv.id,
            description="Item to be cascaded",
            line_total=Decimal("500.00"),
        )
        issue = ValidationIssue(
            invoice_id=inv.id,
            field_name="tax",
            issue_type="missing_tax",
            severity="info",
            description="No tax charged",
        )
        event = ProcessingEvent(
            document_id=doc.id,
            event_type="info",
            message="Event attached to document",
        )
        session.add_all([item, issue, event])
        session.commit()

        # Verify relationships navigation
        session.refresh(doc)
        assert doc.invoice is not None
        assert doc.invoice.invoice_number == "INV-CASCADE"
        assert len(doc.processing_events) == 1
        assert len(doc.invoice.line_items) == 1
        assert len(doc.invoice.validation_issues) == 1

        # Delete document - should cascade to invoice, items, issues, events
        session.delete(doc)
        session.commit()

        assert session.scalar(select(Document).where(Document.id == doc.id)) is None
        assert session.scalar(select(Invoice).where(Invoice.id == inv.id)) is None
        assert session.scalar(select(InvoiceLineItem).where(InvoiceLineItem.id == item.id)) is None
        assert session.scalar(select(ValidationIssue).where(ValidationIssue.id == issue.id)) is None
        assert session.scalar(select(ProcessingEvent).where(ProcessingEvent.id == event.id)) is None
