"""
Pydantic schemas for the financial validation engine, duplicate invoice detection, and issue resolution.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.schemas.extraction_api import ValidationIssueDetailResponse


class IssueResolveRequest(BaseModel):
    """Payload for an operator manually resolving a validation issue."""
    resolved_by: Optional[str] = Field(
        default=None, description="Operator or auditor identity resolving the discrepancy"
    )
    resolution_notes: Optional[str] = Field(
        default=None, description="Explanation describing why this issue was resolved or verified"
    )


class IssueReopenRequest(BaseModel):
    """Payload for reopening a previously resolved issue."""
    reopened_by: Optional[str] = Field(
        default=None, description="Operator or auditor identity reopening the discrepancy"
    )
    reopen_notes: Optional[str] = Field(
        default=None, description="Explanation describing why this issue was reopened"
    )


class DuplicateMatchDetail(BaseModel):
    """Detailed evidence supporting a duplicate invoice match."""
    invoice_id: UUID
    document_id: UUID
    invoice_number: Optional[str] = None
    supplier_name: Optional[str] = None
    invoice_date: Optional[date] = None
    total: Optional[Decimal] = None
    currency: Optional[str] = None
    match_type: str = Field(..., description="'exact_duplicate' or 'likely_duplicate'")
    match_reasons: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ValidationSummaryResponse(BaseModel):
    """Comprehensive summary of validation execution on an invoice."""
    invoice_id: UUID
    total_issues: int
    unresolved_errors: int
    unresolved_warnings: int
    unresolved_info: int
    resolved_issues: int
    needs_manual_review: bool
    is_valid: bool
    issues: List[ValidationIssueDetailResponse]
    duplicates_detected: List[DuplicateMatchDetail] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ValidationIssueListResponse(BaseModel):
    """Paginated collection of validation issues across the system."""
    total: int
    skip: int
    limit: int
    items: List[ValidationIssueDetailResponse]

    model_config = ConfigDict(from_attributes=True)
