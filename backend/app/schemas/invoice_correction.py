"""
Pydantic schemas for invoice manual corrections, audit tracking, and dashboard metrics.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.extraction_api import ExtractionRunResponse, InvoiceDetailResponse


class InvoiceUpdateRequest(BaseModel):
    """Payload for manually updating an invoice header or financial totals."""
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    supplier_name: Optional[str] = None
    customer_name: Optional[str] = None
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total: Optional[Decimal] = None
    currency: Optional[str] = None
    needs_manual_review: Optional[bool] = None
    reason: str = Field(
        ...,
        min_length=1,
        description="Required explanation describing the justification for this manual correction",
    )
    corrected_by: Optional[str] = Field(
        default=None,
        description="Optional identity or username of the user making the correction",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Correction reason cannot be blank or whitespace-only.")
        return cleaned

    @field_validator("subtotal", "tax", "total", mode="before")
    @classmethod
    def validate_decimal_format(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        try:
            val_str = str(v).strip().replace(",", "")
            dec = Decimal(val_str)
            if dec < 0:
                raise ValueError("Financial totals cannot be negative.")
            return dec
        except Exception as e:
            raise ValueError(f"Invalid decimal amount: {v}. {e}")


class LineItemUpdateRequest(BaseModel):
    """Payload for editing an individual invoice line item."""
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    reason: str = Field(
        ...,
        min_length=1,
        description="Required explanation describing the justification for modifying this line item",
    )
    corrected_by: Optional[str] = Field(
        default=None,
        description="Optional identity or username of the user making the correction",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Correction reason cannot be blank or whitespace-only.")
        return cleaned

    @field_validator("quantity", "unit_price", "tax", "line_total", mode="before")
    @classmethod
    def validate_decimal_format(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        try:
            val_str = str(v).strip().replace(",", "")
            dec = Decimal(val_str)
            if dec < 0:
                raise ValueError("Line item values cannot be negative.")
            return dec
        except Exception as e:
            raise ValueError(f"Invalid decimal amount: {v}. {e}")


class LineItemCreateRequest(BaseModel):
    """Payload for adding a new line item to an invoice."""
    description: str = Field(..., min_length=1, description="Description of the service or product")
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    reason: str = Field(
        ...,
        min_length=1,
        description="Required explanation describing the justification for adding this line item",
    )
    corrected_by: Optional[str] = Field(
        default=None,
        description="Optional identity or username of the user adding the line item",
    )

    @field_validator("description", "reason")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be blank or whitespace-only.")
        return cleaned

    @field_validator("quantity", "unit_price", "tax", "line_total", mode="before")
    @classmethod
    def validate_decimal_format(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        try:
            val_str = str(v).strip().replace(",", "")
            dec = Decimal(val_str)
            if dec < 0:
                raise ValueError("Line item values cannot be negative.")
            return dec
        except Exception as e:
            raise ValueError(f"Invalid decimal amount: {v}. {e}")


class InvoiceCorrectionAuditResponse(BaseModel):
    """Audit trail record for a single manual correction action."""
    id: UUID
    invoice_id: UUID
    correction_type: str
    changed_fields: List[str]
    previous_values: Dict[str, Any]
    new_values: Dict[str, Any]
    reason: Optional[str] = None
    corrected_by: Optional[str] = None
    corrected_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceListResponse(BaseModel):
    """Paginated list of invoices with total count."""
    total: int
    skip: int
    limit: int
    items: List[InvoiceDetailResponse]

    model_config = ConfigDict(from_attributes=True)


class DashboardMetricsResponse(BaseModel):
    """High-level system metrics and recent operational activities."""
    total_documents: int
    processed_documents: int
    processing_documents: int
    failed_documents: int
    total_invoices: int
    needs_review_invoices: int
    manually_corrected_invoices: int
    recent_extraction_runs: List[ExtractionRunResponse]
    recent_corrections: List[InvoiceCorrectionAuditResponse]

    model_config = ConfigDict(from_attributes=True)
