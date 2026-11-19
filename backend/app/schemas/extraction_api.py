"""
Pydantic API schemas for invoice database persistence and extraction REST endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExtractionInitiationResponse(BaseModel):
    """Response returned when an invoice extraction job is accepted."""
    extraction_run_id: UUID = Field(..., description="UUID of the newly created ExtractionRun")
    document_id: UUID = Field(..., description="UUID of the document being extracted")
    status: str = Field(..., description="Initial status of the run, e.g. 'queued'")
    processing_mode: str = Field(..., description="'inline' or 'celery'")
    message: str = Field(..., description="Human-readable acknowledgement message")

    model_config = ConfigDict(from_attributes=True)


class ExtractionRunResponse(BaseModel):
    """Full detail of an ExtractionRun record."""
    id: UUID
    document_id: UUID
    provider: str
    model_name: str
    prompt_version: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None
    input_token_count: Optional[int] = None
    output_token_count: Optional[int] = None
    total_contexts: int = 0
    successful_contexts: int = 0
    skipped_contexts: int = 0
    failed_contexts: int = 0
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExtractionHistoryResponse(BaseModel):
    """List of extraction runs for a document ordered newest first."""
    document_id: UUID
    total_runs: int
    runs: List[ExtractionRunResponse]

    model_config = ConfigDict(from_attributes=True)


class InvoiceLineItemDetailResponse(BaseModel):
    """Itemized invoice line item with evidence and confidence metadata."""
    id: UUID
    invoice_id: UUID
    description: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    field_evidence: Optional[Dict[str, Any]] = None
    field_confidence: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidationIssueDetailResponse(BaseModel):
    """Validation issue or audit discrepancy associated with an invoice."""
    id: UUID
    invoice_id: UUID
    line_item_id: Optional[UUID] = None
    field_name: str
    issue_type: str
    severity: str
    description: str
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None
    related_invoice_id: Optional[UUID] = None
    related_document_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceDetailResponse(BaseModel):
    """Detailed invoice model including header, financial totals, line items, evidence, and review flags."""
    id: UUID
    document_id: UUID
    extraction_run_id: Optional[UUID] = None
    source_context_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    supplier_name: Optional[str] = None
    customer_name: Optional[str] = None
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total: Optional[Decimal] = None
    currency: Optional[str] = None
    extraction_method: Optional[str] = None
    field_evidence: Optional[Dict[str, Any]] = None
    field_confidence: Optional[Dict[str, Any]] = None
    extraction_metadata: Optional[Dict[str, Any]] = None
    needs_manual_review: bool = False
    is_manually_corrected: bool = False
    document_page_start: Optional[int] = None
    document_page_end: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    line_items: List[InvoiceLineItemDetailResponse] = Field(default_factory=list)
    validation_issues: List[ValidationIssueDetailResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DocumentInvoicesResponse(BaseModel):
    """List of extracted invoices for a document, with extraction run reference."""
    document_id: UUID
    extraction_run_id: Optional[UUID] = None
    total_invoices: int
    invoices: List[InvoiceDetailResponse]

    model_config = ConfigDict(from_attributes=True)
