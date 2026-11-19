"""
Extraction context models for document intelligence.

Defines Pydantic v2 data models for:
- RowRange: Precise row boundaries within a spreadsheet worksheet.
- ExtractionContext: Structured context container representing an invoice or financial candidate.
- ContextPreparationResult: Top-level outcome of document context preparation.
- ExtractionContextSummary: Lightweight view for paginated API list responses.
- ExtractionContextListResponse: Paginated API response for extraction contexts.
"""

import math
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RowRange(BaseModel):
    """Row boundaries within a specific worksheet."""
    sheet_name: str = Field(..., description="Name of the worksheet")
    row_start: Optional[int] = Field(default=None, ge=0, description="1-based or 0-based start row index")
    row_end: Optional[int] = Field(default=None, ge=0, description="1-based or 0-based end row index")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ExtractionContext(BaseModel):
    """
    Structured extraction context grouping related document chunks
    (e.g., a single-page invoice, multi-page invoice, or worksheet section).
    """
    context_id: UUID = Field(default_factory=uuid4, description="Unique identifier for this extraction context")
    document_id: UUID = Field(..., description="UUID of parent Document")
    context_index: int = Field(..., ge=0, description="Zero-based ordering index among document contexts")
    document_type_hint: str = Field(
        default="invoice",
        description="Class hint: 'invoice', 'receipt', 'financial_statement', 'mixed', 'unknown'",
    )
    source_chunk_ids: List[UUID] = Field(
        default_factory=list,
        description="Exact UUIDs of original DocumentChunks grouped in this context",
    )
    page_start: Optional[int] = Field(default=None, ge=0, description="First page number included in this context")
    page_end: Optional[int] = Field(default=None, ge=0, description="Last page number included in this context")
    sheet_names: List[str] = Field(default_factory=list, description="Worksheet names included in this context")
    row_ranges: List[RowRange] = Field(
        default_factory=list,
        description="List of sheet row ranges contributing to this context",
    )
    combined_text: str = Field(..., description="Aggregated text from source chunks ready for LLM consumption")
    character_count: int = Field(..., ge=0, description="Character count of combined_text")
    estimated_input_tokens: int = Field(..., ge=0, description="Estimated token count for prompt budgeting")
    segmentation_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Heuristic confidence in the boundary grouping (0.0 to 1.0)",
    )
    needs_manual_review: bool = Field(
        default=False,
        description="True if boundary, invoice numbers, or content segmentation are ambiguous",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Human-readable explanations for why manual review is flagged",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Auxiliary context metadata (detected invoice numbers, batching, etc.)",
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        Conservative token count estimation.
        Using ~3.5 characters per token with minimum 1 token for non-empty text.
        """
        if not text:
            return 0
        return max(1, math.ceil(len(text) / 3.5))


class ContextPreparationResult(BaseModel):
    """
    Summary outcome of preparing extraction contexts for a document.
    """
    document_id: UUID = Field(..., description="UUID of the processed document")
    contexts: List[ExtractionContext] = Field(
        default_factory=list,
        description="List of prepared extraction contexts",
    )
    total_source_chunks: int = Field(0, ge=0, description="Total number of chunks retrieved for document")
    selected_source_chunks: int = Field(0, ge=0, description="Number of unique chunks included in contexts")
    unselected_source_chunks: int = Field(0, ge=0, description="Number of chunks excluded or marked unselected")
    warnings: List[str] = Field(default_factory=list, description="Operational warnings or notes")
    processing_time_ms: float = Field(0.0, ge=0.0, description="Context preparation execution time in milliseconds")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ExtractionContextSummary(BaseModel):
    """
    Lightweight summary view of an ExtractionContext, omitting full combined_text
    to preserve bandwidth and API responsiveness.
    """
    context_id: UUID
    document_id: UUID
    context_index: int
    document_type_hint: str
    source_chunk_ids: List[UUID]
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    sheet_names: List[str] = Field(default_factory=list)
    character_count: int
    estimated_input_tokens: int
    segmentation_confidence: Optional[float] = None
    needs_manual_review: bool = False
    review_reasons: List[str] = Field(default_factory=list)
    text_preview: str = Field("", description="First ~150 characters of combined text")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_context(cls, ctx: ExtractionContext, preview_len: int = 150) -> "ExtractionContextSummary":
        preview = ctx.combined_text[:preview_len].strip()
        if len(ctx.combined_text) > preview_len:
            preview += "..."
        return cls(
            context_id=ctx.context_id,
            document_id=ctx.document_id,
            context_index=ctx.context_index,
            document_type_hint=ctx.document_type_hint,
            source_chunk_ids=ctx.source_chunk_ids,
            page_start=ctx.page_start,
            page_end=ctx.page_end,
            sheet_names=ctx.sheet_names,
            character_count=ctx.character_count,
            estimated_input_tokens=ctx.estimated_input_tokens,
            segmentation_confidence=ctx.segmentation_confidence,
            needs_manual_review=ctx.needs_manual_review,
            review_reasons=ctx.review_reasons,
            text_preview=preview,
            metadata=ctx.metadata,
        )


class ExtractionContextListResponse(BaseModel):
    """
    Paginated API response containing extraction context summaries.
    """
    document_id: UUID
    items: List[ExtractionContextSummary]
    total: int
    page: int
    page_size: int
    total_pages: int
    total_source_chunks: int
    selected_source_chunks: int
    warnings: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
