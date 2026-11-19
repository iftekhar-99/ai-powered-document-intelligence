"""
Invoice inspection, manual correction, and audit retrieval endpoints.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.invoice_correction import InvoiceCorrectionAudit
from app.schemas.extraction_api import (
    InvoiceDetailResponse,
    InvoiceLineItemDetailResponse,
)
from app.schemas.invoice_correction import (
    InvoiceCorrectionAuditResponse,
    InvoiceListResponse,
    InvoiceUpdateRequest,
    LineItemCreateRequest,
    LineItemUpdateRequest,
)
from app.services.validation import validation_service

router = APIRouter()


def _serialize_val(val: Any) -> Any:
    """Safely serialize date, Decimal, or UUID for JSON storage."""
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, uuid.UUID):
        return str(val)
    return val


@router.get(
    "",
    response_model=InvoiceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all invoices",
    description="Query and filter all extracted invoices across all documents with pagination and full text search.",
)
async def list_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search invoice number, supplier or customer"),
    currency: Optional[str] = Query(None, description="Filter by currency code"),
    needs_review: Optional[bool] = Query(None, description="Filter by needs_manual_review status"),
    is_manually_corrected: Optional[bool] = Query(None, description="Filter by correction status"),
    db: AsyncSession = Depends(get_db),
) -> InvoiceListResponse:
    base_query = select(Invoice)

    if search:
        search_pattern = f"%{search.strip()}%"
        base_query = base_query.where(
            or_(
                Invoice.invoice_number.ilike(search_pattern),
                Invoice.supplier_name.ilike(search_pattern),
                Invoice.customer_name.ilike(search_pattern),
            )
        )

    if currency:
        base_query = base_query.where(Invoice.currency == currency.strip().upper())

    if needs_review is not None:
        base_query = base_query.where(Invoice.needs_manual_review == needs_review)

    if is_manually_corrected is not None:
        base_query = base_query.where(Invoice.is_manually_corrected == is_manually_corrected)

    # Count total matching
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total_count = (await db.execute(count_stmt)).scalar() or 0

    # Retrieve page
    stmt = (
        base_query.options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.validation_issues),
        )
        .order_by(Invoice.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    invoices = (await db.execute(stmt)).scalars().all()

    return InvoiceListResponse(
        total=total_count,
        skip=skip,
        limit=limit,
        items=[InvoiceDetailResponse.model_validate(inv) for inv in invoices],
    )


@router.get(
    "/{invoice_id}",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve individual invoice",
    description="Retrieve full details for an individual extracted invoice, including line items, field evidence, confidence metrics, review flags, and validation issues.",
)
async def get_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> InvoiceDetailResponse:
    query = (
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.validation_issues),
        )
    )
    invoice = (await db.execute(query)).scalar_one_or_none()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID '{invoice_id}' not found.",
        )

    return InvoiceDetailResponse.model_validate(invoice)


@router.patch(
    "/{invoice_id}",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update invoice headers and financial totals",
    description="Manually edit invoice fields, record audit trail with user justification, and flag as manually corrected.",
)
async def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> InvoiceDetailResponse:
    query = (
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.validation_issues),
        )
    )
    invoice = (await db.execute(query)).scalar_one_or_none()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID '{invoice_id}' not found.",
        )

    update_fields = [
        "invoice_number",
        "invoice_date",
        "supplier_name",
        "customer_name",
        "subtotal",
        "tax",
        "total",
        "currency",
        "needs_manual_review",
    ]

    changed_fields = []
    previous_values: Dict[str, Any] = {}
    new_values: Dict[str, Any] = {}

    for field in update_fields:
        val = getattr(payload, field)
        if val is not None:
            current_val = getattr(invoice, field)
            if current_val != val:
                changed_fields.append(field)
                previous_values[field] = _serialize_val(current_val)
                new_values[field] = _serialize_val(val)
                setattr(invoice, field, val)

    if not changed_fields:
        # No actual fields changed, return existing invoice
        return InvoiceDetailResponse.model_validate(invoice)

    invoice.is_manually_corrected = True

    audit_entry = InvoiceCorrectionAudit(
        invoice_id=invoice.id,
        correction_type="HEADER_UPDATE",
        changed_fields=changed_fields,
        previous_values=previous_values,
        new_values=new_values,
        reason=payload.reason,
        corrected_by=payload.corrected_by,
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(invoice)

    # Re-validate invoice after manual header update
    try:
        await validation_service.validate_invoice(db, invoice.id)
    except Exception as val_err:
        pass

    # Re-fetch with relationships loaded
    refreshed_invoice = (await db.execute(query)).scalar_one()
    return InvoiceDetailResponse.model_validate(refreshed_invoice)


@router.patch(
    "/{invoice_id}/line-items/{line_item_id}",
    response_model=InvoiceLineItemDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update an existing invoice line item",
    description="Update the description, quantity, price, tax, or total of an itemized line item with audit logging.",
)
async def update_line_item(
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    payload: LineItemUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> InvoiceLineItemDetailResponse:
    # 1. Verify invoice exists
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID '{invoice_id}' not found.",
        )

    # 2. Verify line item exists
    line_item = await db.scalar(
        select(InvoiceLineItem).where(InvoiceLineItem.id == line_item_id)
    )
    if not line_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Line item with ID '{line_item_id}' not found.",
        )

    # 3. Verify line item belongs to this invoice
    if line_item.invoice_id != invoice_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Line item '{line_item_id}' does not belong to invoice '{invoice_id}'.",
        )

    update_fields = ["description", "quantity", "unit_price", "tax", "line_total"]
    changed_fields = []
    previous_values: Dict[str, Any] = {}
    new_values: Dict[str, Any] = {}

    for field in update_fields:
        val = getattr(payload, field)
        if val is not None:
            current_val = getattr(line_item, field)
            if current_val != val:
                changed_fields.append(field)
                previous_values[field] = _serialize_val(current_val)
                new_values[field] = _serialize_val(val)
                setattr(line_item, field, val)

    if changed_fields:
        invoice.is_manually_corrected = True
        audit_entry = InvoiceCorrectionAudit(
            invoice_id=invoice.id,
            correction_type="LINE_ITEM_UPDATE",
            changed_fields=changed_fields,
            previous_values=previous_values,
            new_values=new_values,
            reason=payload.reason,
            corrected_by=payload.corrected_by,
        )
        db.add(audit_entry)
        await db.commit()

        # Re-validate parent invoice after line item update
        try:
            await validation_service.validate_invoice(db, invoice_id)
        except Exception:
            pass

        await db.refresh(line_item)

    return InvoiceLineItemDetailResponse.model_validate(line_item)


@router.post(
    "/{invoice_id}/line-items",
    response_model=InvoiceLineItemDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new line item to an invoice",
    description="Manually insert a line item row that was missed or improperly segmented during AI extraction.",
)
async def create_line_item(
    invoice_id: uuid.UUID,
    payload: LineItemCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> InvoiceLineItemDetailResponse:
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID '{invoice_id}' not found.",
        )

    line_item = InvoiceLineItem(
        invoice_id=invoice.id,
        description=payload.description,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        tax=payload.tax,
        line_total=payload.line_total,
    )
    db.add(line_item)
    invoice.is_manually_corrected = True

    new_vals = {
        "description": payload.description,
        "quantity": _serialize_val(payload.quantity),
        "unit_price": _serialize_val(payload.unit_price),
        "tax": _serialize_val(payload.tax),
        "line_total": _serialize_val(payload.line_total),
    }

    audit_entry = InvoiceCorrectionAudit(
        invoice_id=invoice.id,
        correction_type="LINE_ITEM_ADD",
        changed_fields=list(new_vals.keys()),
        previous_values={},
        new_values=new_vals,
        reason=payload.reason,
        corrected_by=payload.corrected_by,
    )
    db.add(audit_entry)

    await db.commit()

    # Re-validate parent invoice after adding line item
    try:
        await validation_service.validate_invoice(db, invoice_id)
    except Exception:
        pass

    await db.refresh(line_item)

    return InvoiceLineItemDetailResponse.model_validate(line_item)


@router.delete(
    "/{invoice_id}/line-items/{line_item_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a line item from an invoice",
    description="Remove an erroneous or hallucinated line item from an invoice with mandatory justification.",
)
async def delete_line_item(
    invoice_id: uuid.UUID,
    line_item_id: uuid.UUID,
    reason: str = Query(..., min_length=1, description="Mandatory reason for removing line item"),
    corrected_by: Optional[str] = Query(None, description="Optional user identity"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    cleaned_reason = reason.strip()
    if not cleaned_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Correction reason cannot be blank or whitespace-only.",
        )

    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID '{invoice_id}' not found.",
        )

    line_item = await db.scalar(
        select(InvoiceLineItem).where(InvoiceLineItem.id == line_item_id)
    )
    if not line_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Line item with ID '{line_item_id}' not found.",
        )

    if line_item.invoice_id != invoice_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Line item '{line_item_id}' does not belong to invoice '{invoice_id}'.",
        )

    previous_vals = {
        "id": str(line_item.id),
        "description": line_item.description,
        "quantity": _serialize_val(line_item.quantity),
        "unit_price": _serialize_val(line_item.unit_price),
        "tax": _serialize_val(line_item.tax),
        "line_total": _serialize_val(line_item.line_total),
    }

    await db.delete(line_item)
    invoice.is_manually_corrected = True

    audit_entry = InvoiceCorrectionAudit(
        invoice_id=invoice.id,
        correction_type="LINE_ITEM_DELETE",
        changed_fields=["line_item"],
        previous_values=previous_vals,
        new_values={},
        reason=cleaned_reason,
        corrected_by=corrected_by,
    )
    db.add(audit_entry)

    await db.commit()

    # Re-validate parent invoice after deleting line item
    try:
        await validation_service.validate_invoice(db, invoice_id)
    except Exception:
        pass

    return {
        "message": f"Line item '{line_item_id}' successfully removed.",
        "line_item_id": str(line_item_id),
        "invoice_id": str(invoice_id),
    }


@router.get(
    "/{invoice_id}/corrections",
    response_model=List[InvoiceCorrectionAuditResponse],
    status_code=status.HTTP_200_OK,
    summary="Get correction audit history for an invoice",
    description="Retrieve chronological audit log of all manual changes applied to this invoice.",
)
async def get_invoice_corrections(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[InvoiceCorrectionAuditResponse]:
    invoice = await db.scalar(select(Invoice).where(Invoice.id == invoice_id))
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice with ID '{invoice_id}' not found.",
        )

    query = (
        select(InvoiceCorrectionAudit)
        .where(InvoiceCorrectionAudit.invoice_id == invoice_id)
        .order_by(InvoiceCorrectionAudit.corrected_at.desc())
    )
    audits = (await db.execute(query)).scalars().all()

    return [InvoiceCorrectionAuditResponse.model_validate(a) for a in audits]
