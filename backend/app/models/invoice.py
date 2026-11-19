import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.extraction_run import ExtractionRun
    from app.models.invoice_correction import InvoiceCorrectionAudit


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint(
            "extraction_run_id",
            "source_context_id",
            name="uq_invoice_run_context",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=False,
        nullable=False,
        index=True,
    )
    extraction_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("extraction_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_context_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )
    invoice_number: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )
    customer_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    subtotal: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    tax: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    extraction_method: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    field_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    field_confidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    extraction_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    needs_manual_review: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_manually_corrected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    document_page_start: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    document_page_end: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document", back_populates="invoices"
    )
    extraction_run: Mapped[Optional["ExtractionRun"]] = relationship(
        "ExtractionRun", back_populates="invoices"
    )
    line_items: Mapped[List["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    validation_issues: Mapped[List["ValidationIssue"]] = relationship(
        "ValidationIssue",
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[ValidationIssue.invoice_id]",
    )
    corrections: Mapped[List["InvoiceCorrectionAudit"]] = relationship(
        "InvoiceCorrectionAudit",
        back_populates="invoice",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="desc(InvoiceCorrectionAudit.corrected_at)",
    )

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} number={self.invoice_number} total={self.total}>"


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    unit_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    tax: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    line_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    field_evidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    field_confidence: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationship
    invoice: Mapped["Invoice"] = relationship(
        "Invoice", back_populates="line_items"
    )

    def __repr__(self) -> str:
        return f"<InvoiceLineItem id={self.id} desc={self.description[:20]}>"


class ValidationIssue(Base):
    __tablename__ = "validation_issues"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoice_line_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32), default="warning", nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    observed_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    related_invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    related_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship(
        "Invoice",
        back_populates="validation_issues",
        foreign_keys=[invoice_id],
    )
    related_invoice: Mapped[Optional["Invoice"]] = relationship(
        "Invoice",
        foreign_keys=[related_invoice_id],
    )
    related_document: Mapped[Optional["Document"]] = relationship(
        "Document",
        foreign_keys=[related_document_id],
    )
    line_item: Mapped[Optional["InvoiceLineItem"]] = relationship(
        "InvoiceLineItem",
        foreign_keys=[line_item_id],
    )

    def __repr__(self) -> str:
        return f"<ValidationIssue id={self.id} field={self.field_name} severity={self.severity}>"
