"""
Invoice and financial document extraction schemas.

Provides strict, reusable Pydantic v2 models for:
- SourceEvidence (provenance and ground truth linking)
- ExtractedField (generic wrapper for values, confidence, and provenance)
- InvoiceLineItemExtraction (individual invoice item rows)
- InvoiceExtraction (header, totals, items, validation flags)
- DocumentExtractionResponse (top-level extraction payload for documents)
"""

import re
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")


class DocumentType(str, Enum):
    """Recognized document classifications."""
    INVOICE = "invoice"
    RECEIPT = "receipt"
    OTHER = "other"
    UNKNOWN = "unknown"


class ExtractionStatus(str, Enum):
    """Lifecycle status of document extraction."""
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    PENDING = "pending"


class SourceEvidence(BaseModel):
    """
    Provenance evidence pointing to the source text chunk or table location
    from which a field value was extracted.
    """
    source_chunk_id: UUID = Field(
        ...,
        description="UUID of the DocumentChunk supporting this extraction",
    )
    page_number: Optional[int] = Field(
        default=None,
        ge=0,
        description="Page number (0-based or 1-based) where evidence was found",
    )
    sheet_name: Optional[str] = Field(
        default=None,
        description="Worksheet name if evidence originates from a spreadsheet",
    )
    row_start: Optional[int] = Field(
        default=None,
        ge=0,
        description="Starting row index if evidence originates from a tabular format",
    )
    row_end: Optional[int] = Field(
        default=None,
        ge=0,
        description="Ending row index if evidence originates from a tabular format",
    )
    relevant_text: str = Field(
        ...,
        description="Exact supporting text snippet extracted from the source chunk",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ExtractedField(BaseModel, Generic[T]):
    """
    Generic wrapper for an extracted field value.

    Maintains:
    - value: Typed parsed representation or None if not found in document.
    - raw_value: Exact unparsed text string extracted from the document.
    - confidence: Estimated extraction confidence (0.0 to 1.0), NOT measured accuracy.
    - evidence: List of SourceEvidence chunks linking back to source provenance.
    """
    value: Optional[T] = Field(
        default=None,
        description="Typed parsed value, or None if the field could not be found or extracted",
    )
    raw_value: Optional[str] = Field(
        default=None,
        description="Original unparsed string representation directly from the document",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Estimated extraction confidence between 0.0 and 1.0 (estimated confidence, not measured accuracy)",
    )
    evidence: List[SourceEvidence] = Field(
        default_factory=list,
        description="List of SourceEvidence records establishing provenance",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def wrap_scalar(cls, data: Any) -> Any:
        """Allow scalar values or None to automatically populate 'value'."""
        if not isinstance(data, (dict, ExtractedField)):
            return {"value": data}
        return data

    @field_validator("value", mode="before")
    @classmethod
    def parse_generic_value(cls, v: Any) -> Any:
        """
        Specialized validation for Decimal financial values:
        strips currency symbols and commas, converting numeric strings or floats to Decimal.
        Preserves None without creating artificial defaults.
        """
        if v is None:
            return None

        # Inspect generic type argument for Decimal
        meta = getattr(cls, "__pydantic_generic_metadata__", {})
        args = meta.get("args", ())
        if args and args[0] is Decimal:
            if isinstance(v, Decimal):
                return v
            if isinstance(v, (int, float)):
                return Decimal(str(v))
            if isinstance(v, str):
                cleaned = v.strip()
                if not cleaned:
                    return None
                # Strip currency symbols and commas
                cleaned = re.sub(r"[\$€£¥₹\s]", "", cleaned).replace(",", "")
                try:
                    return Decimal(cleaned)
                except InvalidOperation:
                    raise ValueError(f"Cannot parse {v!r} as Decimal")
        return v

    @classmethod
    def from_value(
        cls,
        value: Optional[T] = None,
        raw_value: Optional[str] = None,
        confidence: Optional[float] = None,
        evidence: Optional[List[SourceEvidence]] = None,
    ) -> "ExtractedField[T]":
        """Convenience constructor for programmatically creating an ExtractedField."""
        return cls(
            value=value,
            raw_value=raw_value,
            confidence=confidence,
            evidence=evidence or [],
        )

    @classmethod
    def empty(cls) -> "ExtractedField[T]":
        """Convenience constructor for an empty, unextracted field."""
        return cls(value=None, raw_value=None, confidence=None, evidence=[])


class InvoiceLineItemExtraction(BaseModel):
    """Structured extraction of an individual invoice line item row."""
    description: ExtractedField[str] = Field(
        default_factory=ExtractedField,
        description="Item description or service details",
    )
    quantity: ExtractedField[Decimal] = Field(
        default_factory=ExtractedField,
        description="Number of units or hours billed",
    )
    unit_price: ExtractedField[Decimal] = Field(
        default_factory=ExtractedField,
        description="Price per individual unit",
    )
    tax: ExtractedField[Decimal] = Field(
        default_factory=ExtractedField,
        description="Tax or VAT applied directly to this line item",
    )
    line_total: ExtractedField[Decimal] = Field(
        default_factory=ExtractedField,
        description="Extended line total (typically quantity * unit_price)",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class InvoiceExtraction(BaseModel):
    """
    Extracted invoice document model containing headers, parties, totals,
    line items, confidence metrics, and manual review flags.
    """
    invoice_number: ExtractedField[str] = Field(
        default_factory=ExtractedField,
        description="Identifier / invoice number",
    )
    invoice_date: ExtractedField[str] = Field(
        default_factory=ExtractedField,
        description="Billing / invoice issue date",
    )
    supplier_name: ExtractedField[str] = Field(
        default_factory=ExtractedField,
        description="Vendor / supplier company or person name",
    )
    customer_name: ExtractedField[str] = Field(
        default_factory=ExtractedField,
        description="Customer / client / bill-to name",
    )
    subtotal: ExtractedField[Decimal] = Field(
        default_factory=ExtractedField,
        description="Pre-tax subtotal amount",
    )
    tax: ExtractedField[Decimal] = Field(
        default_factory=ExtractedField,
        description="Total tax amount",
    )
    total: ExtractedField[Decimal] = Field(
        default_factory=ExtractedField,
        description="Final invoice balance / total amount due",
    )
    currency: ExtractedField[str] = Field(
        default_factory=ExtractedField,
        description="Currency code e.g. USD, EUR, GBP",
    )
    line_items: List[InvoiceLineItemExtraction] = Field(
        default_factory=list,
        description="List of extracted individual itemized line items",
    )
    overall_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Aggregate extraction confidence score across the invoice",
    )
    needs_manual_review: bool = Field(
        default=False,
        description="Flag indicating if the invoice requires human review or verification",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable reasons why manual review is recommended",
    )
    document_page_start: Optional[int] = Field(
        default=None,
        ge=0,
        description="Starting page number of this invoice within the multi-page document",
    )
    document_page_end: Optional[int] = Field(
        default=None,
        ge=0,
        description="Ending page number of this invoice within the multi-page document",
    )
    source_context_id: Optional[UUID] = Field(
        default=None,
        description="UUID of the ExtractionContext this invoice was extracted from",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentExtractionResponse(BaseModel):
    """
    Top-level response payload for a processed document extraction.
    Supports single or multiple invoices extracted from a single document.
    """
    document_id: UUID = Field(
        ...,
        description="UUID of the processed document",
    )
    document_type: DocumentType = Field(
        default=DocumentType.INVOICE,
        description="Classified document type (invoice, receipt, other, unknown)",
    )
    invoices: List[InvoiceExtraction] = Field(
        default_factory=list,
        description="List of extracted invoices (supports multi-invoice documents)",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Extraction warnings or non-fatal discrepancies encountered",
    )
    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.COMPLETED,
        description="Processing status: completed, partial, failed, pending",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Execution and orchestration metadata (tokens, latency, provider, etc.)",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
