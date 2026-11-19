"""
Lifecycle service for managing chunk vector embeddings, duplicate prevention, and backfilling.
"""

from datetime import datetime, timezone
import hashlib
import logging
from typing import List, Optional, Tuple
import uuid
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.chunk import DocumentChunk
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document import Document
from app.schemas.search import EmbeddingBackfillResponse, SearchCapabilitiesResponse
from app.services.search.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    get_embedding_provider,
)

logger = logging.getLogger("doc_intel.search.embeddings.service")


def compute_chunk_hash(content: str) -> str:
    """Compute deterministic SHA-256 hash of chunk text."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class EmbeddingService:
    """
    Manages generation, storage, and backfill of chunk embeddings.
    """

    def __init__(self, provider: Optional[EmbeddingProvider] = None):
        self._provider = provider

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider or get_embedding_provider()

    async def embed_chunk(
        self,
        db: AsyncSession,
        chunk: DocumentChunk,
    ) -> Optional[ChunkEmbedding]:
        """
        Embed an individual chunk idempotently.
        If an embedding with matching hash and model already exists, returns existing without re-embedding.
        """
        if not chunk.content or not chunk.content.strip():
            return None

        provider = self.provider
        is_avail, reason = provider.check_availability()
        if not is_avail:
            logger.warning("Embedding provider '%s' unavailable: %s", provider.provider_name, reason)
            return None

        chunk_hash = compute_chunk_hash(chunk.content)

        # Check existing record
        existing = await db.scalar(
            select(ChunkEmbedding).where(ChunkEmbedding.chunk_id == chunk.id)
        )

        if existing:
            # If already embedded with same content, matching provider, model, and dimension, skip
            if (
                existing.chunk_hash == chunk_hash
                and existing.model_name == provider.model_name
                and existing.provider == provider.provider_name
                and existing.dimension == provider.dimension
                and existing.status == "completed"
            ):
                return existing

        try:
            vectors = await provider.embed_texts([chunk.content])
            vector = vectors[0]

            if existing:
                existing.provider = provider.provider_name
                existing.model_name = provider.model_name
                existing.dimension = len(vector)
                existing.embedding = vector
                existing.chunk_hash = chunk_hash
                existing.status = "completed"
                existing.error_message = None
                existing.updated_at = datetime.now(timezone.utc)
                rec = existing
            else:
                rec = ChunkEmbedding(
                    id=uuid.uuid4(),
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    provider=provider.provider_name,
                    model_name=provider.model_name,
                    dimension=len(vector),
                    embedding=vector,
                    chunk_hash=chunk_hash,
                    status="completed",
                )
                db.add(rec)

            await db.commit()
            await db.refresh(rec)
            return rec

        except Exception as exc:
            logger.warning("Failed to embed chunk %s: %s", chunk.id, exc)
            if existing:
                existing.status = "failed"
                existing.error_message = str(exc)
                await db.commit()
            return None

    async def embed_document_chunks(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> int:
        """
        Generate embeddings for all chunks of a document.
        Does not fail the document if embedding generation fails.
        """
        provider = self.provider
        is_avail, _ = provider.check_availability()
        if not is_avail:
            return 0

        chunks = (
            await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            )
        ).scalars().all()

        success_count = 0
        for chunk in chunks:
            res = await self.embed_chunk(db, chunk)
            if res is not None:
                success_count += 1

        return success_count

    async def backfill_all_embeddings(
        self,
        db: AsyncSession,
        batch_size: int = 50,
    ) -> EmbeddingBackfillResponse:
        """
        Backfill embeddings across all documents and chunks that lack current embeddings.
        """
        provider = self.provider
        is_avail, reason = provider.check_availability()
        if not is_avail:
            return EmbeddingBackfillResponse(
                total_chunks_processed=0,
                embedded_count=0,
                skipped_count=0,
                failed_count=0,
                status="unavailable",
                message=f"Embedding provider unavailable: {reason}",
            )

        # Retrieve all chunks
        stmt = (
            select(DocumentChunk)
            .options(selectinload(DocumentChunk.embedding_record))
            .order_by(DocumentChunk.created_at.asc())
        )
        chunks = (await db.execute(stmt)).scalars().all()

        total = len(chunks)
        embedded_count = 0
        skipped_count = 0
        failed_count = 0

        for chunk in chunks:
            h = compute_chunk_hash(chunk.content)
            rec = chunk.embedding_record
            if (
                rec
                and rec.chunk_hash == h
                and rec.model_name == provider.model_name
                and rec.provider == provider.provider_name
                and rec.dimension == provider.dimension
                and rec.status == "completed"
            ):
                skipped_count += 1
                continue

            res = await self.embed_chunk(db, chunk)
            if res and res.status == "completed":
                embedded_count += 1
            else:
                failed_count += 1

        return EmbeddingBackfillResponse(
            total_chunks_processed=total,
            embedded_count=embedded_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            status="completed" if failed_count == 0 else "partial",
            message=f"Processed {total} chunk(s): {embedded_count} newly embedded, {skipped_count} skipped, {failed_count} failed.",
        )

    async def mark_stale_embeddings(self, db: AsyncSession) -> int:
        """
        Marks any completed embeddings that do not match the active provider, model, or dimension as 'stale'.
        """
        provider = self.provider
        stale_stmt = (
            select(ChunkEmbedding)
            .where(
                and_(
                    ChunkEmbedding.status == "completed",
                    or_(
                        ChunkEmbedding.model_name != provider.model_name,
                        ChunkEmbedding.provider != provider.provider_name,
                        ChunkEmbedding.dimension != provider.dimension,
                    ),
                )
            )
        )
        stale_records = (await db.execute(stale_stmt)).scalars().all()
        for rec in stale_records:
            rec.status = "stale"
            rec.error_message = (
                f"Stale embedding generated by {rec.provider}/{rec.model_name} "
                f"({rec.dimension}-dim); active: {provider.provider_name}/{provider.model_name} "
                f"({provider.dimension}-dim)"
            )
        if stale_records:
            await db.commit()
        return len(stale_records)

    async def get_capabilities(
        self,
        db: AsyncSession,
    ) -> SearchCapabilitiesResponse:
        """
        Inspect current system configuration and report honest availability of search modes.
        """
        provider = self.provider
        is_avail, reason = provider.check_availability()

        total_chunks = (
            await db.scalar(select(func.count(DocumentChunk.id)))
        ) or 0

        embedded_chunks = (
            await db.scalar(
                select(func.count(ChunkEmbedding.id)).where(
                    and_(
                        ChunkEmbedding.status == "completed",
                        ChunkEmbedding.provider == provider.provider_name,
                        ChunkEmbedding.model_name == provider.model_name,
                        ChunkEmbedding.dimension == provider.dimension,
                    )
                )
            )
        ) or 0

        unembedded_chunks = max(0, total_chunks - embedded_chunks)

        return SearchCapabilitiesResponse(
            keyword_search_available=True,
            semantic_search_available=is_avail,
            hybrid_search_available=is_avail,
            embedding_provider=provider.provider_name,
            embedding_model=provider.model_name,
            embedding_dimension=provider.dimension,
            total_chunks=total_chunks,
            embedded_chunks=embedded_chunks,
            unembedded_chunks=unembedded_chunks,
            status_message=reason if is_avail else f"Semantic search offline: {reason}",
        )

    # Aliases
    backfill_all_unembedded = backfill_all_embeddings
    get_search_capabilities = get_capabilities


embedding_service = EmbeddingService()
