"""
Pydantic schemas for Keyword, Semantic, Hybrid, and Structured Invoice search.
"""

from datetime import date, datetime
from decimal import Decimal
import enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchMode(str, enum.Enum):
    HYBRID = "hybrid"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    INVOICE = "invoice"


class SearchResultItem(BaseModel):
    """Unified search hit representing a chunk or document excerpt."""
    chunk_id: Optional[UUID] = None
    document_id: UUID
    document_filename: str
    file_type: str
    chunk_index: Optional[int] = None
    source_type: Optional[str] = None
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_start: Optional[int] = None
    row_end: Optional[int] = None
    content: str
    highlighted_snippet: str
    score: float = Field(..., description="Normalized or fused ranking score")
    match_type: str = Field(..., description="'keyword', 'semantic', 'hybrid', or 'invoice'")
    keyword_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    # Associated invoice details if linked
    invoice_id: Optional[UUID] = None
    invoice_number: Optional[str] = None
    supplier_name: Optional[str] = None
    invoice_total: Optional[Decimal] = None
    currency: Optional[str] = None
    invoice_date: Optional[date] = None
    needs_manual_review: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """Response payload for document text and chunk search."""
    query: str
    mode: str
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[SearchResultItem]
    fallback_mode: bool = False
    fallback_reason: Optional[str] = None
    execution_time_ms: int

    model_config = ConfigDict(from_attributes=True)


class InvoiceSearchResultItem(BaseModel):
    """Detailed hit for structured invoice search."""
    invoice_id: UUID
    document_id: UUID
    document_filename: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    supplier_name: Optional[str] = None
    customer_name: Optional[str] = None
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total: Optional[Decimal] = None
    currency: Optional[str] = None
    needs_manual_review: bool = False
    is_manually_corrected: bool = False
    is_valid: bool = True
    has_duplicates: bool = False
    unresolved_issue_count: int = 0
    line_items_count: int = 0
    matched_fields: List[str] = Field(default_factory=list)
    highlighted_snippet: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceSearchResponse(BaseModel):
    """Response payload for structured invoice record search."""
    query: Optional[str] = None
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[InvoiceSearchResultItem]
    execution_time_ms: int

    model_config = ConfigDict(from_attributes=True)


class SearchCapabilitiesResponse(BaseModel):
    """System capability status revealing which search modes are genuinely active."""
    keyword_search_available: bool = True
    semantic_search_available: bool = False
    hybrid_search_available: bool = False
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    total_chunks: int = 0
    embedded_chunks: int = 0
    unembedded_chunks: int = 0
    status_message: str

    model_config = ConfigDict(from_attributes=True)


class EmbeddingBackfillResponse(BaseModel):
    """Summary of chunk embedding backfill execution."""
    total_chunks_processed: int
    embedded_count: int
    skipped_count: int
    failed_count: int
    status: str
    message: str

    model_config = ConfigDict(from_attributes=True)
