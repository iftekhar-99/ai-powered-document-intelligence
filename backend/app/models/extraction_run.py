import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.invoice import Invoice


class ExtractionRunStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=ExtractionRunStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    input_token_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    output_token_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    total_contexts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    successful_contexts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    skipped_contexts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    failed_contexts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document", back_populates="extraction_runs"
    )
    invoices: Mapped[List["Invoice"]] = relationship(
        "Invoice",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<ExtractionRun id={self.id} doc_id={self.document_id} status={self.status}>"
