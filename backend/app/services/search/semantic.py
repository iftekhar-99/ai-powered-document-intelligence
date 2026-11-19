"""
Semantic search engine executing vector similarity matching using cosine distance across chunk embeddings.
"""

from datetime import date
from decimal import Decimal
import time
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chunk import DocumentChunk
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document import Document
from app.models.invoice import Invoice
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.search.embeddings import (
    EmbeddingProvider,
    EmbeddingUnavailableError,
    cosine_similarity,
    get_embedding_provider,
)
from app.services.search.keyword import clean_query_tokens, generate_highlighted_snippet


class SemanticSearchEngine:
    """
    Ranks document chunks by cosine similarity between query embeddings and stored chunk vectors.
    """

    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self._provider = provider

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider or get_embedding_provider()

    async def search(
        self,
        db: AsyncSession,
        query: str,
        page: int = 1,
        page_size: int = 20,
        document_id: Optional[UUID] = None,
        file_type: Optional[str] = None,
        supplier_name: Optional[str] = None,
        currency: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        amount_min: Optional[Decimal] = None,
        amount_max: Optional[Decimal] = None,
        needs_review: Optional[bool] = None,
    ) -> SearchResponse:
        start_time = time.perf_counter()
        provider = self.provider

        is_avail, reason = provider.check_availability()
        if not is_avail:
            raise EmbeddingUnavailableError(
                f"Semantic search is unavailable: {reason}"
            )

        # Generate query vector
        query_vec = await provider.embed_query(query)

        # Query all active chunk embeddings matching the active model, provider, and dimensionality
        stmt = (
            select(ChunkEmbedding)
            .join(DocumentChunk, ChunkEmbedding.chunk_id == DocumentChunk.id)
            .join(Document, ChunkEmbedding.document_id == Document.id)
            .where(
                and_(
                    ChunkEmbedding.status == "completed",
                    ChunkEmbedding.provider == provider.provider_name,
                    ChunkEmbedding.model_name == provider.model_name,
                    ChunkEmbedding.dimension == provider.dimension,
                )
            )
            .options(
                selectinload(ChunkEmbedding.chunk),
                selectinload(ChunkEmbedding.document).selectinload(Document.invoices),
            )
        )

        conditions = []
        if document_id:
            conditions.append(ChunkEmbedding.document_id == document_id)
        if file_type:
            conditions.append(Document.file_type == file_type.lower().strip())

        if supplier_name or currency or date_from or date_to or amount_min is not None or amount_max is not None or needs_review is not None:
            inv_sub = select(Invoice.document_id).distinct()
            if supplier_name:
                inv_sub = inv_sub.where(Invoice.supplier_name.ilike(f"%{supplier_name.strip()}%"))
            if currency:
                inv_sub = inv_sub.where(Invoice.currency.ilike(currency.strip()))
            if date_from:
                inv_sub = inv_sub.where(Invoice.invoice_date >= date_from)
            if date_to:
                inv_sub = inv_sub.where(Invoice.invoice_date <= date_to)
            if amount_min is not None:
                inv_sub = inv_sub.where(Invoice.total >= amount_min)
            if amount_max is not None:
                inv_sub = inv_sub.where(Invoice.total <= amount_max)
            if needs_review is not None:
                inv_sub = inv_sub.where(Invoice.needs_manual_review == needs_review)
            conditions.append(ChunkEmbedding.document_id.in_(inv_sub))

        if conditions:
            stmt = stmt.where(and_(*conditions))

        records = (await db.execute(stmt)).scalars().all()

        scored: List[Tuple[float, ChunkEmbedding]] = []
        for rec in records:
            sim = cosine_similarity(query_vec, rec.embedding)
            # Only consider positive similarity
            scored.append((sim, rec))

        # Sort descending by similarity
        scored.sort(key=lambda x: x[0], reverse=True)

        tokens = clean_query_tokens(query)
        total = len(scored)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged = scored[start_idx:end_idx]

        items: List[SearchResultItem] = []
        for rank, (sim, rec) in enumerate(paged, start=start_idx + 1):
            chunk = rec.chunk
            doc = rec.document
            inv = doc.invoices[0] if doc and doc.invoices else None

            snippet = generate_highlighted_snippet(chunk.content, tokens)

            items.append(
                SearchResultItem(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_filename=doc.original_filename if doc else "unknown",
                    file_type=doc.file_type if doc else "unknown",
                    chunk_index=chunk.chunk_index,
                    source_type=chunk.source_type,
                    page_number=chunk.page_number,
                    sheet_name=chunk.sheet_name,
                    row_start=chunk.row_start,
                    row_end=chunk.row_end,
                    content=chunk.content,
                    highlighted_snippet=snippet,
                    score=round(float(sim), 4),
                    match_type="semantic",
                    semantic_rank=rank,
                    invoice_id=inv.id if inv else None,
                    invoice_number=inv.invoice_number if inv else None,
                    supplier_name=inv.supplier_name if inv else None,
                    invoice_total=inv.total if inv else None,
                    currency=inv.currency if inv else None,
                    invoice_date=inv.invoice_date if inv else None,
                    needs_manual_review=inv.needs_manual_review if inv else None,
                )
            )

        exec_time = int((time.perf_counter() - start_time) * 1000)
        return SearchResponse(
            query=query,
            mode="semantic",
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
            fallback_mode=False,
            fallback_reason=None,
            execution_time_ms=exec_time,
        )


semantic_search_engine = SemanticSearchEngine()
