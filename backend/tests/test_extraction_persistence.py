"""
Tests for Invoice Database Models and Persistence Service (Task 4E).

Covers:
Database tests:
1. ExtractionRun creation and default status.
2. One document with multiple invoices (one-to-many relationship).
3. Multiple line items per invoice without deduplication.
4. Foreign-key integrity and constraint enforcement.
5. Cascading deletion (deleting document cascades to runs and invoices).
6. Decimal precision preservation on financial amounts.
7. Nullable fields remain NULL without default fabrication.
8. Extraction history ordering and relations.

Persistence service tests:
9. Successful invoice persistence from DocumentExtractionResponse.
10. Multiple invoice persistence from a single document.
11. Line-item persistence with exact Decimals and evidence.
12. Evidence persistence linked to source chunk IDs.
13. Confidence persistence separated from measured accuracy.
14. Invalid source chunk ID rejection and manual review flagging.
15. Unsupported quotation text rejection and manual review flagging.
16. Missing financial values and ambiguous dates remain NULL with raw evidence.
17. Idempotent retry replacing records for the same run and context.
18. Failed extraction preserves previous successful extraction results.
19. Partial extraction persistence.
20. Safe rollback on database transaction failure.
"""

import datetime
from decimal import Decimal
from typing import AsyncGenerator, Dict, List
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.chunk import ChunkSourceType, DocumentChunk
from app.models.document import Document, DocumentStatus
from app.models.extraction_run import ExtractionRun, ExtractionRunStatus
from app.models.invoice import Invoice, InvoiceLineItem, ValidationIssue
from app.models.processing_event import ProcessingEvent
from app.schemas.extraction import (
    DocumentExtractionResponse,
    DocumentType,
    ExtractedField,
    ExtractionStatus,
    InvoiceExtraction,
    InvoiceLineItemExtraction,
    SourceEvidence,
)
from app.services.extraction.persistence import (
    InvoicePersistenceService,
    invoice_persistence_service,
    normalize_whitespace,
    parse_strict_date,
)


@pytest.fixture
def sync_db():
    engine = create_engine("sqlite:///:memory:")
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest_asyncio.fixture
async def async_db() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ==============================================================================
# PART 1: DATABASE MODEL TESTS (Items 1 - 8)
# ==============================================================================

def test_extraction_run_creation(sync_db: Session) -> None:
    """1. ExtractionRun creation and default status."""
    doc = Document(
        original_filename="doc1.pdf",
        stored_filename="s_doc1.pdf",
        file_path="/tmp/s_doc1.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        sha256_hash="hash_001",
    )
    sync_db.add(doc)
    sync_db.commit()

    run = ExtractionRun(
        document_id=doc.id,
        provider="gemini",
        model_name="gemini-flash-lite-latest",
        prompt_version="v2.0-extraction",
        status=ExtractionRunStatus.QUEUED.value,
    )
    sync_db.add(run)
    sync_db.commit()
    sync_db.refresh(run)

    assert isinstance(run.id, uuid.UUID)
    assert run.document_id == doc.id
    assert run.status == "queued"
    assert run.provider == "gemini"
    assert run.model_name == "gemini-flash-lite-latest"
    assert run.total_contexts == 0
    assert run.created_at is not None


def test_one_document_multiple_invoices(sync_db: Session) -> None:
    """2. One document with multiple invoices (one-to-many relationship)."""
    doc = Document(
        original_filename="multi_invoice.pdf",
        stored_filename="s_multi.pdf",
        file_path="/tmp/s_multi.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=200,
        sha256_hash="hash_002",
    )
    sync_db.add(doc)
    sync_db.commit()

    inv1 = Invoice(
        document_id=doc.id,
        invoice_number="INV-001",
        total=Decimal("150.00"),
    )
    inv2 = Invoice(
        document_id=doc.id,
        invoice_number="INV-002",
        total=Decimal("300.00"),
    )
    sync_db.add_all([inv1, inv2])
    sync_db.commit()

    # Query invoices via document relation
    sync_db.refresh(doc)
    assert len(doc.invoices) == 2
    invoice_numbers = {i.invoice_number for i in doc.invoices}
    assert invoice_numbers == {"INV-001", "INV-002"}
    # Backwards compatibility accessor
    assert doc.invoice is not None
    assert doc.invoice.invoice_number in ("INV-001", "INV-002")


def test_multiple_line_items_per_invoice(sync_db: Session) -> None:
    """3. Multiple line items per invoice without deduplication of legitimate repeats."""
    doc = Document(
        original_filename="items.pdf",
        stored_filename="s_items.pdf",
        file_path="/tmp/s_items.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        sha256_hash="hash_003",
    )
    sync_db.add(doc)
    sync_db.commit()

    inv = Invoice(
        document_id=doc.id,
        invoice_number="INV-ITEMS",
        total=Decimal("20.00"),
    )
    sync_db.add(inv)
    sync_db.commit()

    # Two identical legitimate items
    li1 = InvoiceLineItem(
        invoice_id=inv.id,
        description="Standard Widget",
        quantity=Decimal("1.00"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("10.00"),
    )
    li2 = InvoiceLineItem(
        invoice_id=inv.id,
        description="Standard Widget",
        quantity=Decimal("1.00"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("10.00"),
    )
    sync_db.add_all([li1, li2])
    sync_db.commit()

    sync_db.refresh(inv)
    assert len(inv.line_items) == 2
    assert inv.line_items[0].description == "Standard Widget"
    assert inv.line_items[1].description == "Standard Widget"


def test_foreign_key_integrity_and_cascade(sync_db: Session) -> None:
    """4 & 5. Foreign-key integrity and cascading deletion."""
    doc = Document(
        original_filename="cascade.pdf",
        stored_filename="s_casc.pdf",
        file_path="/tmp/s_casc.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        sha256_hash="hash_004",
    )
    sync_db.add(doc)
    sync_db.commit()

    run = ExtractionRun(
        document_id=doc.id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="completed",
    )
    sync_db.add(run)
    sync_db.commit()

    inv = Invoice(
        document_id=doc.id,
        extraction_run_id=run.id,
        invoice_number="INV-CASC",
        total=Decimal("50.00"),
    )
    sync_db.add(inv)
    sync_db.commit()

    item = InvoiceLineItem(
        invoice_id=inv.id,
        description="Item",
        line_total=Decimal("50.00"),
    )
    issue = ValidationIssue(
        invoice_id=inv.id,
        field_name="total",
        issue_type="warning",
        description="test",
    )
    sync_db.add_all([item, issue])
    sync_db.commit()

    doc_id = doc.id
    run_id = run.id
    inv_id = inv.id

    # Delete Document -> cascades to runs, invoices, items, and issues
    sync_db.delete(doc)
    sync_db.commit()

    assert sync_db.scalar(select(Document).where(Document.id == doc_id)) is None
    assert sync_db.scalar(select(ExtractionRun).where(ExtractionRun.id == run_id)) is None
    assert sync_db.scalar(select(Invoice).where(Invoice.id == inv_id)) is None
    assert sync_db.scalar(select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == inv_id)) is None
    assert sync_db.scalar(select(ValidationIssue).where(ValidationIssue.invoice_id == inv_id)) is None


def test_decimal_precision_and_nullable_fields(sync_db: Session) -> None:
    """6 & 7. Decimal precision preservation and nullable fields remaining NULL."""
    doc = Document(
        original_filename="decimal.pdf",
        stored_filename="s_dec.pdf",
        file_path="/tmp/s_dec.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        sha256_hash="hash_005",
    )
    sync_db.add(doc)
    sync_db.commit()

    inv = Invoice(
        document_id=doc.id,
        invoice_number=None,  # Nullable
        invoice_date=None,    # Nullable
        subtotal=Decimal("1234567.89"),
        tax=None,             # Nullable
        total=Decimal("1234567.89"),
    )
    sync_db.add(inv)
    sync_db.commit()
    sync_db.refresh(inv)

    assert inv.invoice_number is None
    assert inv.invoice_date is None
    assert inv.tax is None
    assert inv.subtotal == Decimal("1234567.89")
    assert inv.total == Decimal("1234567.89")


def test_extraction_history_ordering(sync_db: Session) -> None:
    """8. Extraction history ordered newest first."""
    doc = Document(
        original_filename="history.pdf",
        stored_filename="s_hist.pdf",
        file_path="/tmp/s_hist.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=100,
        sha256_hash="hash_006",
    )
    sync_db.add(doc)
    sync_db.commit()

    t1 = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    t2 = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    t3 = datetime.datetime.now(datetime.timezone.utc)

    run1 = ExtractionRun(document_id=doc.id, provider="gemini", model_name="m1", prompt_version="v1", status="failed", created_at=t1)
    run2 = ExtractionRun(document_id=doc.id, provider="gemini", model_name="m1", prompt_version="v1", status="completed", created_at=t2)
    run3 = ExtractionRun(document_id=doc.id, provider="gemini", model_name="m2", prompt_version="v2", status="completed", created_at=t3)
    sync_db.add_all([run1, run2, run3])
    sync_db.commit()

    runs = sync_db.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.document_id == doc.id)
        .order_by(ExtractionRun.created_at.desc())
    ).all()

    assert len(runs) == 3
    assert runs[0].model_name == "m2"
    assert runs[1].model_name == "m1"
    assert runs[2].model_name == "m1"
    assert runs[0].created_at >= runs[1].created_at >= runs[2].created_at


# ==============================================================================
# PART 2: PERSISTENCE SERVICE TESTS (Items 9 - 20)
# ==============================================================================

@pytest.mark.asyncio
async def test_successful_single_invoice_persistence(async_db: AsyncSession) -> None:
    """9, 11, 12, 13. Successful invoice, line items, evidence, and confidence persistence."""
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    run_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="invoice_success.pdf",
        stored_filename="s_inv.pdf",
        file_path="/tmp/s_inv.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_009",
    )
    chunk = DocumentChunk(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=0,
        source_type=ChunkSourceType.PDF_PAGE.value,
        page_number=1,
        content="Invoice INV-999 Date 2026-11-10 Total 115.00 Widget 50.00",
        extraction_method="DIGITAL_TEXT",
    )
    run = ExtractionRun(
        id=run_id,
        document_id=doc_id,
        provider="gemini",
        model_name="gemini-flash-lite-latest",
        prompt_version="v1",
        status=ExtractionRunStatus.PROCESSING.value,
    )
    async_db.add_all([doc, chunk, run])
    await async_db.commit()

    # Build DocumentExtractionResponse
    ev = SourceEvidence(source_chunk_id=chunk_id, page_number=1, relevant_text="INV-999")
    inv_ext = InvoiceExtraction(
        invoice_number=ExtractedField[str](value="INV-999", confidence=0.98, evidence=[ev]),
        invoice_date=ExtractedField[str](value="2026-11-10", confidence=0.95),
        supplier_name=ExtractedField[str](value="Supplier Inc", confidence=0.90),
        subtotal=ExtractedField[Decimal](value=Decimal("100.00")),
        tax=ExtractedField[Decimal](value=Decimal("15.00")),
        total=ExtractedField[Decimal](value=Decimal("115.00")),
        currency=ExtractedField[str](value="USD"),
        line_items=[
            InvoiceLineItemExtraction(
                description=ExtractedField[str](value="Widget"),
                quantity=ExtractedField[Decimal](value=Decimal("2")),
                unit_price=ExtractedField[Decimal](value=Decimal("50.00")),
                line_total=ExtractedField[Decimal](value=Decimal("100.00")),
            )
        ],
        overall_confidence=0.96,
        document_page_start=1,
        document_page_end=1,
    )
    extraction_response = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv_ext],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    persisted = await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=extraction_response,
    )

    assert len(persisted) == 1
    p_inv = persisted[0]
    assert p_inv.invoice_number == "INV-999"
    assert p_inv.invoice_date == datetime.date(2026, 11, 10)
    assert p_inv.total == Decimal("115.00")
    assert p_inv.extraction_run_id == run_id
    assert p_inv.field_confidence["invoice_number"] == 0.98
    assert p_inv.field_evidence["invoice_number"][0]["verified"] is True
    assert p_inv.extraction_metadata["overall_confidence"] == 0.96
    assert p_inv.needs_manual_review is False

    # Check line items in DB
    items_query = select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == p_inv.id)
    items = (await async_db.execute(items_query)).scalars().all()
    assert len(items) == 1
    assert items[0].description == "Widget"
    assert items[0].quantity == Decimal("2")
    assert items[0].unit_price == Decimal("50.00")

    # Check audit event
    event_query = select(ProcessingEvent).where(
        ProcessingEvent.document_id == doc_id,
        ProcessingEvent.event_type == "invoice_extraction_persisted",
    )
    event_row = (await async_db.execute(event_query)).scalar_one_or_none()
    assert event_row is not None


@pytest.mark.asyncio
async def test_multiple_invoices_persistence(async_db: AsyncSession) -> None:
    """10. Multiple invoice persistence from a single multi-page document."""
    doc_id = uuid.uuid4()
    run_id = uuid.uuid4()
    ctx1 = uuid.uuid4()
    ctx2 = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="multi.pdf",
        stored_filename="s_multi_pers.pdf",
        file_path="/tmp/s_multi_pers.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_010",
    )
    run = ExtractionRun(
        id=run_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="processing",
    )
    async_db.add_all([doc, run])
    await async_db.commit()

    inv1 = InvoiceExtraction(
        source_context_id=ctx1,
        invoice_number=ExtractedField[str](value="INV-PAGE-1"),
        total=ExtractedField[Decimal](value=Decimal("50.00")),
        document_page_start=1,
        document_page_end=1,
    )
    inv2 = InvoiceExtraction(
        source_context_id=ctx2,
        invoice_number=ExtractedField[str](value="INV-PAGE-2"),
        total=ExtractedField[Decimal](value=Decimal("75.00")),
        document_page_start=2,
        document_page_end=2,
    )
    resp = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv1, inv2],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    persisted = await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=resp,
    )

    assert len(persisted) == 2
    inv_nums = {i.invoice_number for i in persisted}
    assert inv_nums == {"INV-PAGE-1", "INV-PAGE-2"}


@pytest.mark.asyncio
async def test_invalid_source_chunk_rejection(async_db: AsyncSession) -> None:
    """14. Invalid source evidence chunk ID rejection and review flagging."""
    doc_id = uuid.uuid4()
    run_id = uuid.uuid4()
    fake_chunk_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="fake_chunk.pdf",
        stored_filename="s_fake.pdf",
        file_path="/tmp/s_fake.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_014",
    )
    run = ExtractionRun(
        id=run_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="processing",
    )
    async_db.add_all([doc, run])
    await async_db.commit()

    # Evidence points to fake_chunk_id which is NOT in DB
    ev = SourceEvidence(source_chunk_id=fake_chunk_id, relevant_text="FAKE-INV")
    inv_ext = InvoiceExtraction(
        invoice_number=ExtractedField[str](value="FAKE-INV", evidence=[ev]),
        total=ExtractedField[Decimal](value=Decimal("100.00")),
    )
    resp = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv_ext],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    persisted = await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=resp,
    )

    inv = persisted[0]
    assert inv.needs_manual_review is True
    # Fake evidence is rejected and NOT placed in verified field_evidence
    assert "invoice_number" not in (inv.field_evidence or {})
    # Stored under rejected evidence in metadata
    assert "invoice_number" in inv.extraction_metadata["rejected_evidence"]

    # ValidationIssue record created
    issues = (await async_db.execute(
        select(ValidationIssue).where(ValidationIssue.invoice_id == inv.id)
    )).scalars().all()
    assert any("nonexistent chunk" in iss.description for iss in issues)


@pytest.mark.asyncio
async def test_unsupported_evidence_quotation_rejection(async_db: AsyncSession) -> None:
    """15. Unsupported quotation text rejection (quotation hallucinated)."""
    doc_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    run_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="fake_quote.pdf",
        stored_filename="s_fake_q.pdf",
        file_path="/tmp/s_fake_q.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_015",
    )
    chunk = DocumentChunk(
        id=chunk_id,
        document_id=doc_id,
        chunk_index=0,
        source_type=ChunkSourceType.PDF_PAGE.value,
        content="Invoice total is USD 500.00 for consulting services.",
        extraction_method="DIGITAL_TEXT",
    )
    run = ExtractionRun(
        id=run_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="processing",
    )
    async_db.add_all([doc, chunk, run])
    await async_db.commit()

    # Model hallucinates a supplier quotation not in chunk
    ev = SourceEvidence(
        source_chunk_id=chunk_id,
        relevant_text="Fabricated Supplier Co LLC 999",
    )
    inv_ext = InvoiceExtraction(
        supplier_name=ExtractedField[str](value="Fabricated Supplier", evidence=[ev]),
        total=ExtractedField[Decimal](value=Decimal("500.00")),
    )
    resp = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv_ext],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    persisted = await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=resp,
    )

    inv = persisted[0]
    assert inv.needs_manual_review is True
    assert "supplier_name" not in (inv.field_evidence or {})
    assert "supplier_name" in inv.extraction_metadata["rejected_evidence"]


@pytest.mark.asyncio
async def test_missing_values_and_ambiguous_dates(async_db: AsyncSession) -> None:
    """16. Missing financial values and ambiguous dates remain NULL with raw evidence."""
    doc_id = uuid.uuid4()
    run_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="dates.pdf",
        stored_filename="s_dates.pdf",
        file_path="/tmp/s_dates.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_016",
    )
    run = ExtractionRun(
        id=run_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="processing",
    )
    async_db.add_all([doc, run])
    await async_db.commit()

    inv_ext = InvoiceExtraction(
        invoice_date=ExtractedField[str](value="Q3 2026"),  # Ambiguous
        subtotal=ExtractedField[Decimal](value=None),      # Missing
        tax=ExtractedField[Decimal](value=None),           # Missing
        total=ExtractedField[Decimal](value=Decimal("200.00")),
    )
    resp = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv_ext],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    persisted = await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=resp,
    )

    inv = persisted[0]
    assert inv.invoice_date is None  # Kept NULL, not guessed!
    assert inv.subtotal is None
    assert inv.tax is None
    assert inv.needs_manual_review is True
    assert inv.extraction_metadata["raw_invoice_date"] == "Q3 2026"


@pytest.mark.asyncio
async def test_idempotent_retry_persistence(async_db: AsyncSession) -> None:
    """17. Idempotent retry safely replaces invoices for the same run and context."""
    doc_id = uuid.uuid4()
    run_id = uuid.uuid4()
    ctx_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="retry.pdf",
        stored_filename="s_retry.pdf",
        file_path="/tmp/s_retry.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_017",
    )
    run = ExtractionRun(
        id=run_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="processing",
    )
    async_db.add_all([doc, run])
    await async_db.commit()

    inv1 = InvoiceExtraction(
        source_context_id=ctx_id,
        invoice_number=ExtractedField[str](value="INV-ATTEMPT-1"),
        total=ExtractedField[Decimal](value=Decimal("100.00")),
    )
    resp1 = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv1],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    # First attempt persists
    await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=resp1,
    )

    # Retry of the SAME run and context with updated result
    inv2 = InvoiceExtraction(
        source_context_id=ctx_id,
        invoice_number=ExtractedField[str](value="INV-ATTEMPT-2-RETRY"),
        total=ExtractedField[Decimal](value=Decimal("100.00")),
    )
    resp2 = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv2],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=resp2,
    )

    # Query invoices for this run: should be exactly 1 invoice, with the updated number
    invoices = (await async_db.execute(
        select(Invoice).where(
            Invoice.document_id == doc_id,
            Invoice.extraction_run_id == run_id,
        )
    )).scalars().all()

    assert len(invoices) == 1
    assert invoices[0].invoice_number == "INV-ATTEMPT-2-RETRY"


@pytest.mark.asyncio
async def test_failed_extraction_preserves_previous_success(async_db: AsyncSession) -> None:
    """18. Failed extraction run does not destroy previous successful results."""
    doc_id = uuid.uuid4()
    run1_id = uuid.uuid4()
    run2_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="preserve.pdf",
        stored_filename="s_pres.pdf",
        file_path="/tmp/s_pres.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_018",
    )
    run1 = ExtractionRun(
        id=run1_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="completed",
    )
    run2 = ExtractionRun(
        id=run2_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="failed",
    )
    async_db.add_all([doc, run1, run2])
    await async_db.commit()

    # Run 1: success
    inv1 = InvoiceExtraction(
        invoice_number=ExtractedField[str](value="SAVED-SAFE"),
        total=ExtractedField[Decimal](value=Decimal("150.00")),
    )
    await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run1_id,
        extraction_response=DocumentExtractionResponse(
            document_id=doc_id,
            invoices=[inv1],
            extraction_status=ExtractionStatus.COMPLETED,
        ),
    )

    # Run 2: failed run with no invoices
    failed_resp = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[],
        extraction_status=ExtractionStatus.FAILED,
        warnings=["LLM failure"],
    )
    await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run2_id,
        extraction_response=failed_resp,
    )

    # Verify that Run 1 invoices are still present and intact
    saved = (await async_db.execute(
        select(Invoice).where(Invoice.document_id == doc_id)
    )).scalars().all()

    assert len(saved) == 1
    assert saved[0].invoice_number == "SAVED-SAFE"
    assert saved[0].extraction_run_id == run1_id


@pytest.mark.asyncio
async def test_partial_extraction_persistence(async_db: AsyncSession) -> None:
    """19. Partial extraction persistence when some contexts succeed."""
    doc_id = uuid.uuid4()
    run_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="partial.pdf",
        stored_filename="s_part.pdf",
        file_path="/tmp/s_part.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_019",
    )
    run = ExtractionRun(
        id=run_id,
        document_id=doc_id,
        provider="gemini",
        model_name="flash",
        prompt_version="v1",
        status="processing",
    )
    async_db.add_all([doc, run])
    await async_db.commit()

    inv1 = InvoiceExtraction(
        invoice_number=ExtractedField[str](value="PARTIAL-001"),
        total=ExtractedField[Decimal](value=Decimal("300.00")),
    )
    resp = DocumentExtractionResponse(
        document_id=doc_id,
        invoices=[inv1],
        extraction_status=ExtractionStatus.PARTIAL,
        warnings=["Context 2 failed after max retries"],
    )

    persisted = await invoice_persistence_service.persist_extraction_results(
        db=async_db,
        document_id=doc_id,
        extraction_run_id=run_id,
        extraction_response=resp,
    )

    assert len(persisted) == 1
    assert persisted[0].invoice_number == "PARTIAL-001"
    assert "Context 2 failed" in persisted[0].extraction_metadata["warnings"][0]


@pytest.mark.asyncio
async def test_database_rollback_on_failure(async_db: AsyncSession) -> None:
    """20. Database failure triggers complete rollback without partial dirty state."""
    doc_id = uuid.uuid4()
    run_id = uuid.uuid4()

    doc = Document(
        id=doc_id,
        original_filename="rollback.pdf",
        stored_filename="s_roll.pdf",
        file_path="/tmp/s_roll.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=500,
        sha256_hash="hash_020",
    )
    async_db.add(doc)
    await async_db.commit()

    # Pass an invalid document ID that violates foreign key
    nonexistent_doc_id = uuid.uuid4()
    inv1 = InvoiceExtraction(
        invoice_number=ExtractedField[str](value="WILL-ROLLBACK"),
        total=ExtractedField[Decimal](value=Decimal("50.00")),
    )
    resp = DocumentExtractionResponse(
        document_id=nonexistent_doc_id,
        invoices=[inv1],
        extraction_status=ExtractionStatus.COMPLETED,
    )

    with pytest.raises(Exception):
        await invoice_persistence_service.persist_extraction_results(
            db=async_db,
            document_id=nonexistent_doc_id,
            extraction_run_id=run_id,
            extraction_response=resp,
        )

    # Verify no invoices were saved
    invoices = (await async_db.execute(select(Invoice))).scalars().all()
    assert len(invoices) == 0
