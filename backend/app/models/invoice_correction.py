import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class InvoiceCorrectionAudit(Base):
    __tablename__ = "invoice_correction_audits"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    correction_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # e.g., HEADER_UPDATE, LINE_ITEM_UPDATE, LINE_ITEM_ADD, LINE_ITEM_DELETE
    changed_fields: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    previous_values: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    new_values: Mapped[Dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    corrected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship(
        "Invoice", back_populates="corrections"
    )

    def __repr__(self) -> str:
        return (
            f"<InvoiceCorrectionAudit id={self.id} invoice_id={self.invoice_id} "
            f"type={self.correction_type} at={self.corrected_at}>"
        )
