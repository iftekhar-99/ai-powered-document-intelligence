"""
Central context preparation service for document intelligence.

Orchestrates:
- Retrieving DocumentChunks from the database.
- Sorting chunks by spatial and sequence positions.
- Detecting invoice candidate sections.
- Segmenting PDF pages or spreadsheet worksheets.
- Applying input size and token budgets.
- Producing ContextPreparationResult with full provenance.
"""

import time
from typing import List, Optional, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chunk import ChunkSourceType, DocumentChunk
from app.models.document import Document
from app.services.extraction.context_models import (
    ContextPreparationResult,
    ExtractionContext,
)
from app.services.extraction.segmenter import DocumentSegmenter


class ContextPreparationService:
    """
    Coordinates context preparation and segmentation for documents.
    """

    def __init__(self, max_input_chars: Optional[int] = None):
        self.max_input_chars = max_input_chars or getattr(
            settings, "LLM_MAX_INPUT_CHARS", 30000
        )
        self.segmenter = DocumentSegmenter(max_input_chars=self.max_input_chars)

    async def prepare_document_contexts(
        self,
        document_id: UUID,
        db: AsyncSession,
    ) -> ContextPreparationResult:
        """
        Retrieves chunks for a document, segments them into structured contexts,
        enforces token budgets, and returns a ContextPreparationResult.

        Raises:
            ValueError: If the document does not exist in the database.
        """
        start_time = time.perf_counter()

        # 1. Retrieve document metadata
        doc = await db.scalar(select(Document).where(Document.id == document_id))
        if not doc:
            raise ValueError(f"Document with ID '{document_id}' not found.")

        # 2. Retrieve all DocumentChunks ordered by chunk_index
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
        result = await db.scalars(stmt)
        chunks: List[DocumentChunk] = list(result.all())

        warnings: List[str] = []

        if not chunks:
            warnings.append("Document has no extracted chunks.")
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return ContextPreparationResult(
                document_id=document_id,
                contexts=[],
                total_source_chunks=0,
                selected_source_chunks=0,
                unselected_source_chunks=0,
                warnings=warnings,
                processing_time_ms=elapsed_ms,
            )

        # 3. Determine segmentation strategy based on chunk source types
        spreadsheet_sources = {
            ChunkSourceType.SPREADSHEET_SHEET.value,
            ChunkSourceType.CSV.value,
            "SPREADSHEET_SHEET",
            "CSV",
        }
        is_spreadsheet = any(c.source_type in spreadsheet_sources for c in chunks)

        contexts: List[ExtractionContext] = []
        if is_spreadsheet:
            contexts = self.segmenter.segment_spreadsheet_chunks(document_id, chunks)
        else:
            contexts = self.segmenter.segment_pdf_chunks(document_id, chunks)

        # 4. Compute selection metrics
        selected_chunk_ids: Set[UUID] = set()
        for ctx in contexts:
            selected_chunk_ids.update(ctx.source_chunk_ids)

        total_chunks = len(chunks)
        selected_count = len(selected_chunk_ids)
        unselected_count = max(0, total_chunks - selected_count)

        if unselected_count > 0:
            warnings.append(
                f"{unselected_count} source chunk(s) were not selected into active extraction contexts."
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return ContextPreparationResult(
            document_id=document_id,
            contexts=contexts,
            total_source_chunks=total_chunks,
            selected_source_chunks=selected_count,
            unselected_source_chunks=unselected_count,
            warnings=warnings,
            processing_time_ms=elapsed_ms,
        )


# Global singleton instance
context_service = ContextPreparationService()
