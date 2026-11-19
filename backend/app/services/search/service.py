"""
Unified Search Service facade coordinating keyword, semantic, hybrid, and structured invoice searches.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.search import (
    EmbeddingBackfillResponse,
    InvoiceSearchResponse,
    SearchCapabilitiesResponse,
    SearchMode,
    SearchResponse,
)
from app.services.search.embedding_service import embedding_service
from app.services.search.hybrid import hybrid_search_engine
from app.services.search.invoice_search import invoice_search_engine
from app.services.search.keyword import keyword_search_engine
from app.services.search.semantic import semantic_search_engine


class SearchService:
    """
    Facade for all document and financial search capabilities in the system.
    """

    def __init__(self):
        self.keyword_engine = keyword_search_engine
        self.semantic_engine = semantic_search_engine
        self.hybrid_engine = hybrid_search_engine
        self.invoice_engine = invoice_search_engine
        self.embedding_service = embedding_service

    async def search(
        self,
        db: AsyncSession,
        query: str,
        mode: Union[SearchMode, str] = SearchMode.HYBRID,
        page: int = 1,
        page_size: int = 20,
        document_id: Optional[UUID] = None,
        file_type: Optional[str] = None,
        supplier_name: Optional[str] = None,
        customer_name: Optional[str] = None,
        currency: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        amount_min: Optional[Decimal] = None,
        amount_max: Optional[Decimal] = None,
        needs_review: Optional[bool] = None,
        is_manually_corrected: Optional[bool] = None,
        is_valid: Optional[bool] = None,
        has_duplicates: Optional[bool] = None,
    ) -> Union[SearchResponse, InvoiceSearchResponse]:
        """
        Unified search dispatcher routing to keyword, semantic, hybrid, or invoice engines.
        """
        normalized_mode = str(mode).lower()

        if normalized_mode == SearchMode.KEYWORD or normalized_mode == "keyword":
            return await self.keyword_engine.search(
                db=db,
                query=query,
                page=page,
                page_size=page_size,
                document_id=document_id,
                file_type=file_type,
                supplier_name=supplier_name,
                currency=currency,
                date_from=date_from,
                date_to=date_to,
                amount_min=amount_min,
                amount_max=amount_max,
                needs_review=needs_review,
            )
        elif normalized_mode == SearchMode.SEMANTIC or normalized_mode == "semantic":
            return await self.semantic_engine.search(
                db=db,
                query=query,
                page=page,
                page_size=page_size,
                document_id=document_id,
                file_type=file_type,
                supplier_name=supplier_name,
                currency=currency,
                date_from=date_from,
                date_to=date_to,
                amount_min=amount_min,
                amount_max=amount_max,
                needs_review=needs_review,
            )
        elif normalized_mode == SearchMode.INVOICE or normalized_mode == "invoice":
            return await self.invoice_engine.search(
                db=db,
                query=query,
                page=page,
                page_size=page_size,
                document_id=document_id,
                supplier_name=supplier_name,
                customer_name=customer_name,
                currency=currency,
                date_from=date_from,
                date_to=date_to,
                amount_min=amount_min,
                amount_max=amount_max,
                needs_manual_review=needs_review,
                is_manually_corrected=is_manually_corrected,
                is_valid=is_valid,
                has_duplicates=has_duplicates,
            )
        else:
            # Default to Hybrid search
            return await self.hybrid_engine.search(
                db=db,
                query=query,
                page=page,
                page_size=page_size,
                document_id=document_id,
                file_type=file_type,
                supplier_name=supplier_name,
                currency=currency,
                date_from=date_from,
                date_to=date_to,
                amount_min=amount_min,
                amount_max=amount_max,
                needs_review=needs_review,
            )

    async def search_invoices(
        self,
        db: AsyncSession,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        document_id: Optional[UUID] = None,
        supplier_name: Optional[str] = None,
        customer_name: Optional[str] = None,
        currency: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        amount_min: Optional[Decimal] = None,
        amount_max: Optional[Decimal] = None,
        needs_manual_review: Optional[bool] = None,
        is_manually_corrected: Optional[bool] = None,
        is_valid: Optional[bool] = None,
        has_duplicates: Optional[bool] = None,
    ) -> InvoiceSearchResponse:
        return await self.invoice_engine.search(
            db=db,
            query=query,
            page=page,
            page_size=page_size,
            document_id=document_id,
            supplier_name=supplier_name,
            customer_name=customer_name,
            currency=currency,
            date_from=date_from,
            date_to=date_to,
            amount_min=amount_min,
            amount_max=amount_max,
            needs_manual_review=needs_manual_review,
            is_manually_corrected=is_manually_corrected,
            is_valid=is_valid,
            has_duplicates=has_duplicates,
        )

    async def get_capabilities(self, db: AsyncSession) -> SearchCapabilitiesResponse:
        """
        Inspect genuine search capabilities without misrepresenting keyword search as semantic.
        """
        return await self.embedding_service.get_search_capabilities(db)

    async def backfill_embeddings(
        self, db: AsyncSession, batch_size: int = 50
    ) -> EmbeddingBackfillResponse:
        """
        Run backfill process for unembedded chunks.
        """
        return await self.embedding_service.backfill_all_unembedded(
            db=db, batch_size=batch_size
        )


search_service = SearchService()
