import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.chunk_embedding import ChunkEmbedding
    from app.models.document import Document


class ChunkSourceType(str, enum.Enum):
    PDF_PAGE = "PDF_PAGE"
    IMAGE = "IMAGE"
    TIFF_PAGE = "TIFF_PAGE"
    SPREADSHEET_SHEET = "SPREADSHEET_SHEET"
    CSV = "CSV"


class ExtractionMethod(str, enum.Enum):
    DIGITAL_TEXT = "DIGITAL_TEXT"
    OCR = "OCR"
    TABULAR_PARSER = "TABULAR_PARSER"
    FALLBACK = "FALLBACK"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    row_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    row_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), nullable=False)
    ocr_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    # Named "metadata" in database, attribute is chunk_metadata to avoid collision with Base.metadata
    chunk_metadata: Mapped[Dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
    embedding_record: Mapped[Optional["ChunkEmbedding"]] = relationship(
        "ChunkEmbedding",
        back_populates="chunk",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def meta(self) -> Dict[str, Any]:
        return self.chunk_metadata

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk id={self.id} doc_id={self.document_id} "
            f"idx={self.chunk_index} type={self.source_type}>"
        )
