"""
Dashboard aggregation and operational metrics endpoints.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.document import Document, DocumentStatus
from app.models.extraction_run import ExtractionRun
from app.models.invoice import Invoice
from app.models.invoice_correction import InvoiceCorrectionAudit
from app.schemas.extraction_api import ExtractionRunResponse
from app.schemas.invoice_correction import (
    DashboardMetricsResponse,
    InvoiceCorrectionAuditResponse,
)

router = APIRouter()


@router.get(
    "/metrics",
    response_model=DashboardMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get system-wide dashboard metrics",
    description="Returns aggregate KPI metrics, recent extraction runs, and recent manual correction audit logs.",
)
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
) -> DashboardMetricsResponse:
    # 1. Document metrics
    total_docs = (
        await db.scalar(select(func.count(Document.id)))
    ) or 0

    processed_docs = (
        await db.scalar(
            select(func.count(Document.id)).where(
                Document.status == DocumentStatus.COMPLETED.value
            )
        )
    ) or 0

    processing_docs = (
        await db.scalar(
            select(func.count(Document.id)).where(
                Document.status.in_(
                    [
                        DocumentStatus.UPLOADED.value,
                        DocumentStatus.QUEUED.value,
                        DocumentStatus.PROCESSING.value,
                    ]
                )
            )
        )
    ) or 0

    failed_docs = (
        await db.scalar(
            select(func.count(Document.id)).where(
                Document.status.in_(
                    [
                        DocumentStatus.FAILED.value,
                        DocumentStatus.NEEDS_REVIEW.value,
                    ]
                )
            )
        )
    ) or 0

    # 2. Invoice metrics
    total_invs = (
        await db.scalar(select(func.count(Invoice.id)))
    ) or 0

    needs_review_invs = (
        await db.scalar(
            select(func.count(Invoice.id)).where(
                Invoice.needs_manual_review.is_(True)
            )
        )
    ) or 0

    manually_corrected_invs = (
        await db.scalar(
            select(func.count(Invoice.id)).where(
                Invoice.is_manually_corrected.is_(True)
            )
        )
    ) or 0

    # 3. Recent extraction runs
    runs_stmt = (
        select(ExtractionRun)
        .order_by(ExtractionRun.created_at.desc())
        .limit(5)
    )
    recent_runs = (await db.execute(runs_stmt)).scalars().all()

    # 4. Recent manual corrections
    corrections_stmt = (
        select(InvoiceCorrectionAudit)
        .order_by(InvoiceCorrectionAudit.corrected_at.desc())
        .limit(5)
    )
    recent_corrections = (await db.execute(corrections_stmt)).scalars().all()

    return DashboardMetricsResponse(
        total_documents=total_docs,
        processed_documents=processed_docs,
        processing_documents=processing_docs,
        failed_documents=failed_docs,
        total_invoices=total_invs,
        needs_review_invoices=needs_review_invs,
        manually_corrected_invoices=manually_corrected_invs,
        recent_extraction_runs=[
            ExtractionRunResponse.model_validate(r) for r in recent_runs
        ],
        recent_corrections=[
            InvoiceCorrectionAuditResponse.model_validate(c)
            for c in recent_corrections
        ],
    )
