"""
Structured invoice search engine querying normalized invoice metadata, line items, and validation flags.
"""

from datetime import date
from decimal import Decimal
import time
from typing import List, Optional, Set
from uuid import UUID

from sqlalchemy import and_, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document
from app.models.invoice import Invoice, InvoiceLineItem, ValidationIssue
from app.schemas.search import InvoiceSearchResponse, InvoiceSearchResultItem
from app.services.search.keyword import clean_query_tokens, generate_highlighted_snippet


class StructuredInvoiceSearchEngine:
    """
    Search engine specialized in finding and filtering structured financial invoice records
    by supplier, customer, invoice numbers, amounts, dates, line items, and audit flags.
    """

    async def search(
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
        start_time = time.perf_counter()
        tokens = clean_query_tokens(query) if query else []

        # Base query loading related entities
        stmt = (
            select(Invoice)
            .join(Document, Invoice.document_id == Document.id)
            .options(
                selectinload(Invoice.document),
                selectinload(Invoice.line_items),
                selectinload(Invoice.validation_issues),
            )
        )

        conditions = []

        # 1. Text search across invoice fields and line items
        if tokens:
            token_conditions = []
            for tok in tokens:
                pattern = f"%{tok}%"
                # Check invoice number, supplier, customer, document filename
                term_cond = or_(
                    Invoice.invoice_number.ilike(pattern),
                    Invoice.supplier_name.ilike(pattern),
                    Invoice.customer_name.ilike(pattern),
                    Document.original_filename.ilike(pattern),
                    # Check line item descriptions
                    exists(
                        select(InvoiceLineItem.id).where(
                            and_(
                                InvoiceLineItem.invoice_id == Invoice.id,
                                InvoiceLineItem.description.ilike(pattern),
                            )
                        )
                    ),
                )
                token_conditions.append(term_cond)

            conditions.append(or_(*token_conditions))

        # 2. Targeted field filters
        if document_id:
            conditions.append(Invoice.document_id == document_id)
        if supplier_name:
            conditions.append(Invoice.supplier_name.ilike(f"%{supplier_name.strip()}%"))
        if customer_name:
            conditions.append(Invoice.customer_name.ilike(f"%{customer_name.strip()}%"))
        if currency:
            conditions.append(Invoice.currency.ilike(currency.strip()))
        if date_from:
            conditions.append(Invoice.invoice_date >= date_from)
        if date_to:
            conditions.append(Invoice.invoice_date <= date_to)
        if amount_min is not None:
            conditions.append(Invoice.total >= amount_min)
        if amount_max is not None:
            conditions.append(Invoice.total <= amount_max)
        if needs_manual_review is not None:
            conditions.append(Invoice.needs_manual_review == needs_manual_review)
        if is_manually_corrected is not None:
            conditions.append(Invoice.is_manually_corrected == is_manually_corrected)

        # 3. Validation and duplicate filters
        if is_valid is not None:
            error_exists = exists(
                select(ValidationIssue.id).where(
                    and_(
                        ValidationIssue.invoice_id == Invoice.id,
                        ValidationIssue.severity == "error",
                        ValidationIssue.resolved == False,
                    )
                )
            )
            if is_valid:
                conditions.append(~error_exists)
            else:
                conditions.append(error_exists)

        if has_duplicates is not None:
            dup_exists = exists(
                select(ValidationIssue.id).where(
                    and_(
                        ValidationIssue.invoice_id == Invoice.id,
                        ValidationIssue.issue_type.in_(
                            ["duplicate_invoice_number", "duplicate_amount_date"]
                        ),
                        ValidationIssue.resolved == False,
                    )
                )
            )
            if has_duplicates:
                conditions.append(dup_exists)
            else:
                conditions.append(~dup_exists)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Order by creation date descending
        stmt = stmt.order_by(Invoice.created_at.desc())

        # Execute query
        invoices = (await db.execute(stmt)).scalars().all()

        total = len(invoices)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_invoices = invoices[start_idx:end_idx]

        items: List[InvoiceSearchResultItem] = []
        for inv in paged_invoices:
            doc = inv.document
            issues = inv.validation_issues or []
            line_items = inv.line_items or []

            unresolved_count = sum(1 for iss in issues if not iss.resolved)
            has_error = any(iss.severity == "error" and not iss.resolved for iss in issues)
            has_dup = any(
                iss.issue_type in ["duplicate_invoice_number", "duplicate_amount_date"]
                and not iss.resolved
                for iss in issues
            )

            # Match identification and snippet creation
            matched_fields: List[str] = []
            snippet_candidates: List[str] = []

            if tokens:
                for tok in tokens:
                    if inv.invoice_number and tok in inv.invoice_number.lower():
                        if "invoice_number" not in matched_fields:
                            matched_fields.append("invoice_number")
                            snippet_candidates.append(f"Invoice #{inv.invoice_number}")
                    if inv.supplier_name and tok in inv.supplier_name.lower():
                        if "supplier_name" not in matched_fields:
                            matched_fields.append("supplier_name")
                            snippet_candidates.append(f"Supplier: {inv.supplier_name}")
                    if inv.customer_name and tok in inv.customer_name.lower():
                        if "customer_name" not in matched_fields:
                            matched_fields.append("customer_name")
                            snippet_candidates.append(f"Customer: {inv.customer_name}")
                    if doc and tok in doc.original_filename.lower():
                        if "document_filename" not in matched_fields:
                            matched_fields.append("document_filename")
                            snippet_candidates.append(f"File: {doc.original_filename}")

                    for item in line_items:
                        if item.description and tok in item.description.lower():
                            if "line_items" not in matched_fields:
                                matched_fields.append("line_items")
                            snippet_candidates.append(f"Item: {item.description}")

            snippet = None
            if snippet_candidates:
                full_raw = " | ".join(snippet_candidates[:3])
                snippet = generate_highlighted_snippet(full_raw, tokens)

            items.append(
                InvoiceSearchResultItem(
                    invoice_id=inv.id,
                    document_id=inv.document_id,
                    document_filename=doc.original_filename if doc else "unknown",
                    invoice_number=inv.invoice_number,
                    invoice_date=inv.invoice_date,
                    supplier_name=inv.supplier_name,
                    customer_name=inv.customer_name,
                    subtotal=inv.subtotal,
                    tax=inv.tax,
                    total=inv.total,
                    currency=inv.currency,
                    needs_manual_review=inv.needs_manual_review,
                    is_manually_corrected=inv.is_manually_corrected,
                    is_valid=not has_error,
                    has_duplicates=has_dup,
                    unresolved_issue_count=unresolved_count,
                    line_items_count=len(line_items),
                    matched_fields=matched_fields,
                    highlighted_snippet=snippet,
                    created_at=inv.created_at,
                )
            )

        exec_time = int((time.perf_counter() - start_time) * 1000)
        return InvoiceSearchResponse(
            query=query,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items,
            execution_time_ms=exec_time,
        )


invoice_search_engine = StructuredInvoiceSearchEngine()
