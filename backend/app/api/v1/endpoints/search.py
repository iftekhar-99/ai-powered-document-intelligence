"""
Search API endpoints for keyword, semantic, hybrid, and structured invoice searches.
"""

from datetime import date
from decimal import Decimal
from typing import Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.search import (
    EmbeddingBackfillResponse,
    InvoiceSearchResponse,
    SearchCapabilitiesResponse,
    SearchMode,
    SearchResponse,
)
from app.services.search import (
    EmbeddingUnavailableError,
    search_service,
)

router = APIRouter()


@router.get(
    "",
    response_model=Union[SearchResponse, InvoiceSearchResponse],
    summary="Unified document and financial search",
)
@router.get(
    "/",
    response_model=Union[SearchResponse, InvoiceSearchResponse],
    include_in_schema=False,
)
async def unified_search(
    q: str = Query("", description="Search query string"),
    mode: SearchMode = Query(SearchMode.HYBRID, description="Search retrieval mode"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    document_id: Optional[UUID] = Query(None, description="Filter by document ID"),
    file_type: Optional[str] = Query(None, description="Filter by file extension / type"),
    supplier_name: Optional[str] = Query(None, description="Filter by supplier name"),
    customer_name: Optional[str] = Query(None, description="Filter by customer name"),
    currency: Optional[str] = Query(None, description="Filter by currency code"),
    date_from: Optional[date] = Query(None, description="Invoice date on or after"),
    date_to: Optional[date] = Query(None, description="Invoice date on or before"),
    amount_min: Optional[Decimal] = Query(None, description="Minimum invoice total"),
    amount_max: Optional[Decimal] = Query(None, description="Maximum invoice total"),
    needs_review: Optional[bool] = Query(None, description="Filter by manual review flag"),
    is_manually_corrected: Optional[bool] = Query(None, description="Filter by manual correction status"),
    is_valid: Optional[bool] = Query(None, description="Filter by validity / absence of errors"),
    has_duplicates: Optional[bool] = Query(None, description="Filter by duplicate flags"),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await search_service.search(
            db=db,
            query=q,
            mode=mode,
            page=page,
            page_size=page_size,
            document_id=document_id,
            file_type=file_type,
            supplier_name=supplier_name,
            customer_name=customer_name,
            currency=currency,
            date_from=date_from,
            date_to=date_to,
            amount_min=amount_min,
            amount_max=amount_max,
            needs_review=needs_review,
            is_manually_corrected=is_manually_corrected,
            is_valid=is_valid,
            has_duplicates=has_duplicates,
        )
    except EmbeddingUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.get(
    "/keyword",
    response_model=SearchResponse,
    summary="Direct keyword search across chunks",
)
async def keyword_search(
    q: str = Query(..., description="Keyword query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_id: Optional[UUID] = Query(None),
    file_type: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    amount_min: Optional[Decimal] = Query(None),
    amount_max: Optional[Decimal] = Query(None),
    needs_review: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await search_service.keyword_engine.search(
        db=db,
        query=q,
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


@router.get(
    "/semantic",
    response_model=SearchResponse,
    summary="Direct semantic vector search across chunks",
)
async def semantic_search(
    q: str = Query(..., description="Semantic query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_id: Optional[UUID] = Query(None),
    file_type: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    amount_min: Optional[Decimal] = Query(None),
    amount_max: Optional[Decimal] = Query(None),
    needs_review: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await search_service.semantic_engine.search(
            db=db,
            query=q,
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
    except EmbeddingUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.get(
    "/hybrid",
    response_model=SearchResponse,
    summary="Hybrid RRF search combining keyword and vector semantic retrieval",
)
async def hybrid_search(
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_id: Optional[UUID] = Query(None),
    file_type: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    amount_min: Optional[Decimal] = Query(None),
    amount_max: Optional[Decimal] = Query(None),
    needs_review: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await search_service.hybrid_engine.search(
        db=db,
        query=q,
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


@router.get(
    "/invoices",
    response_model=InvoiceSearchResponse,
    summary="Structured financial invoice and line-item search",
)
async def invoice_search(
    q: Optional[str] = Query(None, description="Free text matching invoice number, supplier, items"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_id: Optional[UUID] = Query(None),
    supplier_name: Optional[str] = Query(None),
    customer_name: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    amount_min: Optional[Decimal] = Query(None),
    amount_max: Optional[Decimal] = Query(None),
    needs_review: Optional[bool] = Query(None),
    is_manually_corrected: Optional[bool] = Query(None),
    is_valid: Optional[bool] = Query(None),
    has_duplicates: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await search_service.invoice_engine.search(
        db=db,
        query=q,
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


@router.get(
    "/capabilities",
    response_model=SearchCapabilitiesResponse,
    summary="Check active search modes, embedding model, and embedding metrics",
)
async def get_search_capabilities(
    db: AsyncSession = Depends(get_db),
):
    return await search_service.get_capabilities(db)


@router.post(
    "/embeddings/backfill",
    response_model=EmbeddingBackfillResponse,
    summary="Trigger backfill embedding generation for unembedded chunks",
)
async def backfill_embeddings(
    batch_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    return await search_service.backfill_embeddings(db=db, batch_size=batch_size)
