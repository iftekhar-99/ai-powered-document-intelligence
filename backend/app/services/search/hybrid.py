"""
Hybrid document search engine combining keyword matching and vector semantic retrieval
via Reciprocal Rank Fusion (RRF) with automatic graceful fallback.
"""

from datetime import date
from decimal import Decimal
import time
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.search import SearchResponse, SearchResultItem
from app.services.search.embeddings import EmbeddingUnavailableError
from app.services.search.keyword import KeywordSearchEngine, keyword_search_engine
from app.services.search.semantic import SemanticSearchEngine, semantic_search_engine


class HybridSearchEngine:
    """
    Executes hybrid retrieval by combining keyword search and semantic cosine ranking
    using Reciprocal Rank Fusion (RRF). If semantic search is unavailable, it gracefully
    falls back to keyword-only search with clear attribution.
    """

    def __init__(
        self,
        keyword_engine: Optional[KeywordSearchEngine] = None,
        semantic_engine: Optional[SemanticSearchEngine] = None,
    ):
        self.keyword_engine = keyword_engine or keyword_search_engine
        self.semantic_engine = semantic_engine or semantic_search_engine

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

        # 1. Check if semantic search is available
        provider = self.semantic_engine.provider
        is_avail, reason = provider.check_availability()

        if not is_avail:
            # Automatic fallback to keyword search with explicit disclosure
            kw_resp = await self.keyword_engine.search(
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
            exec_time = int((time.perf_counter() - start_time) * 1000)
            return SearchResponse(
                query=query,
                mode="hybrid",
                total=kw_resp.total,
                page=kw_resp.page,
                page_size=kw_resp.page_size,
                total_pages=kw_resp.total_pages,
                items=kw_resp.items,
                fallback_mode=True,
                fallback_reason=f"Semantic retrieval unavailable: {reason}. Operating in keyword-only fallback mode.",
                execution_time_ms=exec_time,
            )

        # 2. Retrieve candidate pools for both keyword and semantic searches
        candidate_limit = max(100, page * page_size * 2)

        try:
            kw_resp = await self.keyword_engine.search(
                db=db,
                query=query,
                page=1,
                page_size=candidate_limit,
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
        except Exception:
            kw_resp = None

        try:
            sem_resp = await self.semantic_engine.search(
                db=db,
                query=query,
                page=1,
                page_size=candidate_limit,
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
        except (EmbeddingUnavailableError, Exception) as exc:
            # Fall back to keyword if semantic fails mid-execution
            if kw_resp is not None:
                exec_time = int((time.perf_counter() - start_time) * 1000)
                # Slice keyword items according to requested page
                total = kw_resp.total
                total_pages = max(1, (total + page_size - 1) // page_size)
                start_idx = (page - 1) * page_size
                paged_kw = kw_resp.items[start_idx : start_idx + page_size]
                return SearchResponse(
                    query=query,
                    mode="hybrid",
                    total=total,
                    page=page,
                    page_size=page_size,
                    total_pages=total_pages,
                    items=paged_kw,
                    fallback_mode=True,
                    fallback_reason=f"Semantic retrieval encountered an error: {str(exc)}. Falling back to keyword search.",
                    execution_time_ms=exec_time,
                )
            raise exc

        # 3. Reciprocal Rank Fusion (RRF)
        # RRF formula: RRF_score(d) = sum_{m in {kw, sem}} (w_m / (k + rank_m(d)))
        # Standard k = 60, w_kw = 0.5, w_sem = 0.5
        K = 60
        W_KW = 0.5
        W_SEM = 0.5

        fused_scores: Dict[UUID, float] = {}
        items_by_chunk_id: Dict[UUID, SearchResultItem] = {}
        kw_ranks: Dict[UUID, int] = {}
        sem_ranks: Dict[UUID, int] = {}

        if kw_resp:
            for rank, item in enumerate(kw_resp.items, start=1):
                if not item.chunk_id:
                    continue
                kw_ranks[item.chunk_id] = rank
                rrf_term = W_KW / (K + rank)
                fused_scores[item.chunk_id] = fused_scores.get(item.chunk_id, 0.0) + rrf_term
                items_by_chunk_id[item.chunk_id] = item

        if sem_resp:
            for rank, item in enumerate(sem_resp.items, start=1):
                if not item.chunk_id:
                    continue
                sem_ranks[item.chunk_id] = rank
                rrf_term = W_SEM / (K + rank)
                fused_scores[item.chunk_id] = fused_scores.get(item.chunk_id, 0.0) + rrf_term
                if item.chunk_id not in items_by_chunk_id:
                    items_by_chunk_id[item.chunk_id] = item

        # Sort all chunks by fused score descending
        sorted_chunk_ids = sorted(
            fused_scores.keys(), key=lambda cid: fused_scores[cid], reverse=True
        )

        total = len(sorted_chunk_ids)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_chunk_ids = sorted_chunk_ids[start_idx:end_idx]

        fused_items: List[SearchResultItem] = []
        for cid in paged_chunk_ids:
            base_item = items_by_chunk_id[cid]
            kr = kw_ranks.get(cid)
            sr = sem_ranks.get(cid)

            if kr is not None and sr is not None:
                match_type = "hybrid"
            elif kr is not None:
                match_type = "keyword"
            else:
                match_type = "semantic"

            score = round(fused_scores[cid], 5)

            fused_items.append(
                SearchResultItem(
                    chunk_id=base_item.chunk_id,
                    document_id=base_item.document_id,
                    document_filename=base_item.document_filename,
                    file_type=base_item.file_type,
                    chunk_index=base_item.chunk_index,
                    source_type=base_item.source_type,
                    page_number=base_item.page_number,
                    sheet_name=base_item.sheet_name,
                    row_start=base_item.row_start,
                    row_end=base_item.row_end,
                    content=base_item.content,
                    highlighted_snippet=base_item.highlighted_snippet,
                    score=score,
                    match_type=match_type,
                    keyword_rank=kr,
                    semantic_rank=sr,
                    invoice_id=base_item.invoice_id,
                    invoice_number=base_item.invoice_number,
                    supplier_name=base_item.supplier_name,
                    invoice_total=base_item.invoice_total,
                    currency=base_item.currency,
                    invoice_date=base_item.invoice_date,
                    needs_manual_review=base_item.needs_manual_review,
                )
            )

        exec_time = int((time.perf_counter() - start_time) * 1000)
        return SearchResponse(
            query=query,
            mode="hybrid",
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=fused_items,
            fallback_mode=False,
            fallback_reason=None,
            execution_time_ms=exec_time,
        )


hybrid_search_engine = HybridSearchEngine()
