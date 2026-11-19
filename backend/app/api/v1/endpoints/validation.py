"""
REST API endpoints for the Financial Validation Engine, Duplicate Detection, and Issue Resolution.
"""

from typing import List, Optional
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.extraction_api import ValidationIssueDetailResponse
from app.schemas.validation import (
    DuplicateMatchDetail,
    IssueReopenRequest,
    IssueResolveRequest,
    ValidationIssueListResponse,
    ValidationSummaryResponse,
)
from app.services.validation import validation_service

router = APIRouter()


@router.post(
    "/invoices/{invoice_id}/validate",
    response_model=ValidationSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger deterministic validation and duplicate detection for an invoice",
    description="Executes deterministic financial arithmetic, field presence, line item consistency, and duplicate invoice detection.",
)
async def validate_invoice_endpoint(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ValidationSummaryResponse:
    try:
        return await validation_service.validate_invoice(db, invoice_id)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Validation failed: {str(exc)}",
        )


@router.post(
    "/documents/{document_id}/validate-invoices",
    response_model=List[ValidationSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="Validate all extracted invoices in a document",
    description="Batch-validates all invoices belonging to the specified document record.",
)
async def validate_document_invoices_endpoint(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> List[ValidationSummaryResponse]:
    try:
        return await validation_service.validate_document_invoices(db, document_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document validation failed: {str(exc)}",
        )


@router.get(
    "/invoices/{invoice_id}/validation-issues",
    response_model=List[ValidationIssueDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="Get validation issues for an invoice",
    description="Retrieve list of all active or resolved validation discrepancies for a specific invoice.",
)
async def get_invoice_validation_issues_endpoint(
    invoice_id: UUID,
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    db: AsyncSession = Depends(get_db),
) -> List[ValidationIssueDetailResponse]:
    _, items = await validation_service.list_issues(
        db,
        skip=0,
        limit=500,
        resolved=resolved,
        invoice_id=invoice_id,
    )
    return [ValidationIssueDetailResponse.model_validate(iss) for iss in items]


@router.get(
    "/invoices/{invoice_id}/duplicates",
    response_model=List[DuplicateMatchDetail],
    status_code=status.HTTP_200_OK,
    summary="Get duplicate invoice matches",
    description="Scans the database and returns potential exact or likely duplicate invoices across documents.",
)
async def get_invoice_duplicates_endpoint(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> List[DuplicateMatchDetail]:
    try:
        return await validation_service.get_duplicate_matches(db, invoice_id)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan duplicates: {str(exc)}",
        )


@router.get(
    "/validation-issues",
    response_model=ValidationIssueListResponse,
    status_code=status.HTTP_200_OK,
    summary="List validation issues across all invoices",
    description="Filterable and paginated list of validation issues across the financial document workspace.",
)
async def list_validation_issues_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    severity: Optional[str] = Query(None, description="'error', 'warning', or 'info'"),
    issue_type: Optional[str] = Query(None, description="Specific issue category code"),
    resolved: Optional[bool] = Query(None, description="Filter by resolution state"),
    invoice_id: Optional[UUID] = Query(None, description="Filter by invoice UUID"),
    db: AsyncSession = Depends(get_db),
) -> ValidationIssueListResponse:
    total, items = await validation_service.list_issues(
        db,
        skip=skip,
        limit=limit,
        severity=severity,
        issue_type=issue_type,
        resolved=resolved,
        invoice_id=invoice_id,
    )
    return ValidationIssueListResponse(
        total=total,
        skip=skip,
        limit=limit,
        items=[ValidationIssueDetailResponse.model_validate(iss) for iss in items],
    )


@router.patch(
    "/validation-issues/{issue_id}/resolve",
    response_model=ValidationIssueDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually resolve a validation issue",
    description="Mark an identified discrepancy or warning as resolved by an operator with justification.",
)
async def resolve_validation_issue_endpoint(
    issue_id: UUID,
    payload: IssueResolveRequest,
    db: AsyncSession = Depends(get_db),
) -> ValidationIssueDetailResponse:
    try:
        issue = await validation_service.resolve_issue(
            db=db,
            issue_id=issue_id,
            resolved_by=payload.resolved_by,
            notes=payload.resolution_notes,
        )
        return ValidationIssueDetailResponse.model_validate(issue)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve issue: {str(exc)}",
        )


@router.patch(
    "/validation-issues/{issue_id}/reopen",
    response_model=ValidationIssueDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Reopen a previously resolved validation issue",
    description="Revert a resolved validation discrepancy back to active review status.",
)
async def reopen_validation_issue_endpoint(
    issue_id: UUID,
    payload: IssueReopenRequest,
    db: AsyncSession = Depends(get_db),
) -> ValidationIssueDetailResponse:
    try:
        issue = await validation_service.reopen_issue(
            db=db,
            issue_id=issue_id,
            reopened_by=payload.reopened_by,
            notes=payload.reopen_notes,
        )
        return ValidationIssueDetailResponse.model_validate(issue)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reopen issue: {str(exc)}",
        )
