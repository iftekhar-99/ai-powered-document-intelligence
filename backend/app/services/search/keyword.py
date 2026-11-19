"""
Deterministic, database-efficient keyword search engine across document chunks, invoices, and line items.
"""

from datetime import date
from decimal import Decimal
import re
import time
from typing import List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.invoice import Invoice, InvoiceLineItem
from app.schemas.search import SearchResponse, SearchResultItem


def clean_query_tokens(query: str) -> List[str]:
    """Extract individual search tokens, stripping punctuation and redundant whitespace."""
    if not query:
        return []
    # Strip special punctuation except alphanumeric and dashes
    cleaned = re.sub(r"[^\w\s\-]", " ", query)
    tokens = [t.strip().lower() for t in cleaned.split() if len(t.strip()) >= 1]
    return tokens


def generate_highlighted_snippet(text: str, tokens: List[str], max_length: int = 220) -> str:
    """
    Finds the earliest match of any query token in text, extracts an excerpt window,
    and highlights occurrences of tokens using markdown bold (**term**).
    """
    if not text:
        return ""
    if not tokens:
        return text[:max_length] + ("..." if len(text) > max_length else "")

    lower_text = text.lower()
    first_pos = len(text)
    matched_any = False

    for tok in tokens:
        pos = lower_text.find(tok)
        if pos != -1 and pos < first_pos:
            first_pos = pos
            matched_any = True

    if not matched_any or first_pos == len(text):
        snippet = text[:max_length]
        prefix = ""
        suffix = "..." if len(text) > max_length else ""
    else:
        start_idx = max(0, first_pos - 40)
        end_idx = min(len(text), start_idx + max_length)
        prefix = "..." if start_idx > 0 else ""
        suffix = "..." if end_idx < len(text) else ""
        snippet = text[start_idx:end_idx]

    # Highlight tokens in snippet
    for tok in tokens:
        # Case-insensitive replacement with markdown bold
        pattern = re.compile(rf"({re.escape(tok)})", re.IGNORECASE)
        snippet = pattern.sub(r"**\1**", snippet)

    return f"{prefix}{snippet}{suffix}"


class KeywordSearchEngine:
    """
    Executes case-insensitive, multi-word full queries using SQL filters across chunks and documents.
    """

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
        tokens = clean_query_tokens(query)

        # Base query joining DocumentChunk to Document
        stmt = (
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .options(
                selectinload(DocumentChunk.document).selectinload(Document.invoices),
            )
        )

        conditions = []

        # 1. Multi-token text matching on chunk content
        if tokens:
            token_conditions = [
                DocumentChunk.content.ilike(f"%{tok}%") for tok in tokens
            ]
            conditions.append(or_(*token_conditions))

        # 2. Filters
        if document_id:
            conditions.append(DocumentChunk.document_id == document_id)
        if file_type:
            conditions.append(Document.file_type == file_type.lower().strip())

        # Subquery filters for linked invoice properties
        if supplier_name or currency or date_from or date_to or amount_min is not None or amount_max is not None or needs_review is not None:
            inv_subquery = select(Invoice.document_id).distinct()
            if supplier_name:
                inv_subquery = inv_subquery.where(Invoice.supplier_name.ilike(f"%{supplier_name.strip()}%"))
            if currency:
                inv_subquery = inv_subquery.where(Invoice.currency.ilike(currency.strip()))
            if date_from:
                inv_subquery = inv_subquery.where(Invoice.invoice_date >= date_from)
            if date_to:
                inv_subquery = inv_subquery.where(Invoice.invoice_date <= date_to)
            if amount_min is not None:
                inv_subquery = inv_subquery.where(Invoice.total >= amount_min)
            if amount_max is not None:
                inv_subquery = inv_subquery.where(Invoice.total <= amount_max)
            if needs_review is not None:
                inv_subquery = inv_subquery.where(Invoice.needs_manual_review == needs_review)
            conditions.append(DocumentChunk.document_id.in_(inv_subquery))

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Execute query
        results = (await db.execute(stmt)).scalars().all()

        # Score and rank in Python
        scored_items: List[Tuple[float, DocumentChunk]] = []
        for chunk in results:
            content_lower = chunk.content.lower()
            # Calculate term match frequency and exact phrase bonus
            matched_token_count = sum(1 for tok in tokens if tok in content_lower)
            exact_phrase_bonus = 2.0 if (query.strip().lower() in content_lower) else 0.0

            # Base score between 0.1 and 1.0
            if tokens:
                score = (matched_token_count / len(tokens)) + exact_phrase_bonus
            else:
                score = 1.0
            scored_items.append((score, chunk))

        # Sort descending by score, then chunk order
        scored_items.sort(key=lambda x: (x[0], -x[1].chunk_index), reverse=True)

        total = len(scored_items)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_items = scored_items[start_idx:end_idx]

        items: List[SearchResultItem] = []
        for rank, (score, chunk) in enumerate(paged_items, start=start_idx + 1):
            doc = chunk.document
            inv = doc.invoices[0] if doc and doc.invoices else None

            # Generate highlighted snippet
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
                    score=round(float(score), 4),
                    match_type="keyword",
                    keyword_rank=rank,
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
            mode="keyword",
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
            fallback_mode=False,
            fallback_reason=None,
            execution_time_ms=exec_time,
        )


keyword_search_engine = KeywordSearchEngine()
