import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentBase(BaseModel):
    original_filename: str
    file_type: str
    mime_type: str
    file_size: int
    status: str


class DocumentResponse(DocumentBase):
    id: uuid.UUID
    stored_filename: str
    sha256_hash: str
    page_count: Optional[int] = None
    sheet_count: Optional[int] = None
    total_chunks: Optional[int] = 0
    extracted_characters: Optional[int] = 0
    extraction_method_summary: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RejectedDocumentResponse(BaseModel):
    filename: str
    error: str
    reason: str


class UploadBatchResponse(BaseModel):
    accepted: List[DocumentResponse]
    rejected: List[RejectedDocumentResponse]
    total_accepted: int
    total_rejected: int


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProcessingEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidationIssueResponse(BaseModel):
    id: uuid.UUID
    field_name: str
    issue_type: str
    severity: str
    description: str
    resolved: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceLineItemResponse(BaseModel):
    id: uuid.UUID
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    tax: Optional[float] = None
    line_total: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    supplier_name: Optional[str] = None
    customer_name: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    currency: Optional[str] = None
    extraction_method: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    line_items: List[InvoiceLineItemResponse] = Field(default_factory=list)
    validation_issues: List[ValidationIssueResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentResponse):
    processing_events: List[ProcessingEventResponse] = Field(default_factory=list)
    invoices: List[InvoiceResponse] = Field(default_factory=list)
    invoice: Optional[InvoiceResponse] = None

    model_config = ConfigDict(from_attributes=True)
