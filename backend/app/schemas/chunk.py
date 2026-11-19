import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.document import ProcessingEventResponse


class DocumentChunkResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    source_type: str
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_start: Optional[int] = None
    row_end: Optional[int] = None
    content: str
    extraction_method: str
    ocr_confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(
        default_factory=dict, validation_alias="chunk_metadata"
    )
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentChunkListResponse(BaseModel):
    items: List[DocumentChunkResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProcessingSummaryResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    page_count: Optional[int] = None
    sheet_count: Optional[int] = None
    total_chunks: int = 0
    extracted_characters: int = 0
    extraction_method_summary: Optional[str] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    processing_events: List[ProcessingEventResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
