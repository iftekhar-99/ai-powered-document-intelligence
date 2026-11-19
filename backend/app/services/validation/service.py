"""
Validation orchestration service for invoices and itemized line items.
Coordinates deterministic rule execution, duplicate detection, and issue lifecycle management.
"""

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import List, Optional, Tuple
import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.invoice import Invoice, ValidationIssue
from app.schemas.extraction_api import ValidationIssueDetailResponse
from app.schemas.validation import DuplicateMatchDetail, ValidationSummaryResponse
from app.services.validation.duplicate_detector import (
    DuplicateInvoiceDetector,
    duplicate_detector,
)
from app.services.validation.rules import (
    DetectedIssue,
    ValidationRuleEngine,
)

logger = logging.getLogger("doc_intel.validation.service")


class ValidationService:
    """
    Orchestrates deterministic financial validation, duplicate detection,
    and idempotent issue reconciliation across invoices.
    """

    def __init__(
        self,
        rule_engine: Optional[ValidationRuleEngine] = None,
        dup_detector: Optional[DuplicateInvoiceDetector] = None,
    ):
        tolerance = Decimal(str(getattr(settings, "VALIDATION_ROUNDING_TOLERANCE", 0.01)))
        self.rule_engine = rule_engine or ValidationRuleEngine(rounding_tolerance=tolerance)
        self.duplicate_detector = dup_detector or duplicate_detector

    async def validate_invoice(
        self,
        db: AsyncSession,
        invoice_id: UUID,
    ) -> ValidationSummaryResponse:
        """
        Execute deterministic validation checks and duplicate detection on an invoice.
        Reconciles detected issues idempotently with existing database records.
        """
        query = (
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(
                selectinload(Invoice.line_items),
                selectinload(Invoice.validation_issues),
                selectinload(Invoice.document),
            )
        )
        invoice = (await db.execute(query)).scalar_one_or_none()
        if not invoice:
            raise ValueError(f"Invoice with ID '{invoice_id}' not found.")

        # Check if validation is globally enabled
        if not getattr(settings, "VALIDATION_ENABLED", True):
            logger.info("Validation engine is disabled via settings. Skipping validation for invoice %s.", invoice_id)
            return self._build_summary(invoice, [])

        # 1. Execute deterministic rules
        req_issues = self.rule_engine.validate_required_fields(invoice)
        arith_issues = self.rule_engine.validate_financial_arithmetic(invoice)
        line_issues = self.rule_engine.validate_line_items(invoice)

        # 2. Execute duplicate invoice detection
        dup_matches = await self.duplicate_detector.detect_duplicates(db, invoice)
        dup_issues: List[DetectedIssue] = []
        for match in dup_matches:
            is_exact = match.match_type == "exact_duplicate"
            cand_inv = match.candidate_invoice
            doc_label = (
                cand_inv.document.original_filename
                if (cand_inv.document and cand_inv.document.original_filename)
                else str(cand_inv.document_id)
            )
            cand_total = f"{cand_inv.currency or ''} {cand_inv.total}" if cand_inv.total is not None else "unknown total"
            desc = (
                f"Potential duplicate invoice detected in document '{doc_label}' "
                f"(Invoice #{cand_inv.invoice_number or 'UNKNOWN'}, Total: {cand_total}). "
                + " ".join(match.reasons)
            )
            dup_issues.append(
                DetectedIssue(
                    field_name="invoice_number",
                    issue_type="duplicate_invoice_exact" if is_exact else "duplicate_invoice_likely",
                    severity="error" if is_exact else "warning",
                    description=desc,
                    expected_value="Unique invoice across documents",
                    observed_value=f"Matches invoice #{cand_inv.invoice_number} ({cand_inv.id})",
                    related_invoice_id=cand_inv.id,
                    related_document_id=cand_inv.document_id,
                )
            )

        all_detected: List[DetectedIssue] = req_issues + arith_issues + line_issues + dup_issues

        # 3. Idempotent Reconciliation
        existing_by_key = {
            (
                iss.field_name,
                iss.issue_type,
                iss.line_item_id,
                iss.related_invoice_id,
            ): iss
            for iss in invoice.validation_issues
        }

        detected_keys = set()
        for d in all_detected:
            key = (d.field_name, d.issue_type, d.line_item_id, d.related_invoice_id)
            detected_keys.add(key)

            if key in existing_by_key:
                existing_issue = existing_by_key[key]
                existing_issue.description = d.description
                existing_issue.expected_value = d.expected_value
                existing_issue.observed_value = d.observed_value
                existing_issue.severity = d.severity

                # Reopen if previously auto-resolved by system
                if existing_issue.resolved and existing_issue.resolved_by == "system_validation":
                    existing_issue.resolved = False
                    existing_issue.resolved_at = None
                    existing_issue.resolved_by = None
                    existing_issue.resolution_notes = None
            else:
                new_issue = ValidationIssue(
                    id=uuid.uuid4(),
                    invoice_id=invoice.id,
                    line_item_id=d.line_item_id,
                    field_name=d.field_name,
                    issue_type=d.issue_type,
                    severity=d.severity,
                    description=d.description,
                    expected_value=d.expected_value,
                    observed_value=d.observed_value,
                    resolved=False,
                    related_invoice_id=d.related_invoice_id,
                    related_document_id=d.related_document_id,
                )
                db.add(new_issue)
                invoice.validation_issues.append(new_issue)

        # Auto-resolve existing issues that are no longer detected
        for key, existing_issue in existing_by_key.items():
            if key not in detected_keys and not existing_issue.resolved:
                existing_issue.resolved = True
                existing_issue.resolved_at = datetime.now(timezone.utc)
                existing_issue.resolved_by = "system_validation"
                existing_issue.resolution_notes = (
                    "Automatically resolved: discrepancy no longer detected upon re-validation."
                )

        # 4. Update invoice review flags
        unresolved_errors = sum(
            1 for iss in invoice.validation_issues if not iss.resolved and iss.severity == "error"
        )
        unresolved_warnings = sum(
            1 for iss in invoice.validation_issues if not iss.resolved and iss.severity == "warning"
        )

        invoice.needs_manual_review = (unresolved_errors > 0 or unresolved_warnings > 0)

        await db.commit()

        # Reload invoice with relationships eagerly loaded to prevent MissingGreenlet in async context
        reloaded_inv = (
            await db.execute(
                select(Invoice)
                .where(Invoice.id == invoice.id)
                .options(
                    selectinload(Invoice.line_items),
                    selectinload(Invoice.validation_issues),
                    selectinload(Invoice.document),
                )
            )
        ).scalar_one()

        # Format duplicate matches for response
        dup_details = [
            DuplicateMatchDetail(
                invoice_id=m.candidate_invoice.id,
                document_id=m.candidate_invoice.document_id,
                invoice_number=m.candidate_invoice.invoice_number,
                supplier_name=m.candidate_invoice.supplier_name,
                invoice_date=m.candidate_invoice.invoice_date,
                total=m.candidate_invoice.total,
                currency=m.candidate_invoice.currency,
                match_type=m.match_type,
                match_reasons=m.reasons,
            )
            for m in dup_matches
        ]

        return self._build_summary(reloaded_inv, dup_details)

    async def validate_document_invoices(
        self,
        db: AsyncSession,
        document_id: UUID,
    ) -> List[ValidationSummaryResponse]:
        """Validate all invoices belonging to a specific document."""
        stmt = select(Invoice.id).where(Invoice.document_id == document_id)
        invoice_ids = (await db.execute(stmt)).scalars().all()

        summaries: List[ValidationSummaryResponse] = []
        for inv_id in invoice_ids:
            summary = await self.validate_invoice(db, inv_id)
            summaries.append(summary)

        return summaries

    async def resolve_issue(
        self,
        db: AsyncSession,
        issue_id: UUID,
        resolved_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ValidationIssue:
        """Manually mark a validation issue as resolved."""
        issue = await db.scalar(
            select(ValidationIssue).where(ValidationIssue.id == issue_id)
        )
        if not issue:
            raise ValueError(f"Validation issue with ID '{issue_id}' not found.")

        issue.resolved = True
        issue.resolved_at = datetime.now(timezone.utc)
        issue.resolved_by = resolved_by or "operator"
        issue.resolution_notes = notes

        # Re-evaluate invoice review state
        remaining_unresolved = (
            await db.execute(
                select(ValidationIssue).where(
                    ValidationIssue.invoice_id == issue.invoice_id,
                    ValidationIssue.id != issue_id,
                    ValidationIssue.resolved == False,
                    ValidationIssue.severity.in_(["error", "warning"]),
                )
            )
        ).scalars().all()

        if not remaining_unresolved:
            inv = await db.scalar(select(Invoice).where(Invoice.id == issue.invoice_id))
            if inv:
                inv.needs_manual_review = False

        await db.commit()
        await db.refresh(issue)
        return issue

    async def reopen_issue(
        self,
        db: AsyncSession,
        issue_id: UUID,
        reopened_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ValidationIssue:
        """Reopen a previously resolved validation issue."""
        issue = await db.scalar(
            select(ValidationIssue).where(ValidationIssue.id == issue_id)
        )
        if not issue:
            raise ValueError(f"Validation issue with ID '{issue_id}' not found.")

        issue.resolved = False
        issue.resolved_at = None
        issue.resolved_by = None
        if notes:
            issue.resolution_notes = f"Reopened by {reopened_by or 'operator'}: {notes}"

        inv = await db.scalar(select(Invoice).where(Invoice.id == issue.invoice_id))
        if inv:
            inv.needs_manual_review = True

        await db.commit()
        await db.refresh(issue)
        return issue

    async def get_duplicate_matches(
        self,
        db: AsyncSession,
        invoice_id: UUID,
    ) -> List[DuplicateMatchDetail]:
        """Retrieve duplicate candidate invoices matching the given invoice."""
        invoice = await db.scalar(
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(selectinload(Invoice.document))
        )
        if not invoice:
            raise ValueError(f"Invoice with ID '{invoice_id}' not found.")

        matches = await self.duplicate_detector.detect_duplicates(db, invoice)
        return [
            DuplicateMatchDetail(
                invoice_id=m.candidate_invoice.id,
                document_id=m.candidate_invoice.document_id,
                invoice_number=m.candidate_invoice.invoice_number,
                supplier_name=m.candidate_invoice.supplier_name,
                invoice_date=m.candidate_invoice.invoice_date,
                total=m.candidate_invoice.total,
                currency=m.candidate_invoice.currency,
                match_type=m.match_type,
                match_reasons=m.reasons,
            )
            for m in matches
        ]

    async def list_issues(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 50,
        severity: Optional[str] = None,
        issue_type: Optional[str] = None,
        resolved: Optional[bool] = None,
        invoice_id: Optional[UUID] = None,
    ) -> Tuple[int, List[ValidationIssue]]:
        """Query and filter validation issues across the database."""
        base_query = select(ValidationIssue)
        if severity:
            base_query = base_query.where(ValidationIssue.severity == severity)
        if issue_type:
            base_query = base_query.where(ValidationIssue.issue_type == issue_type)
        if resolved is not None:
            base_query = base_query.where(ValidationIssue.resolved == resolved)
        if invoice_id:
            base_query = base_query.where(ValidationIssue.invoice_id == invoice_id)

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = (
            base_query.order_by(ValidationIssue.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items = (await db.execute(stmt)).scalars().all()
        return total, list(items)

    def _build_summary(
        self,
        invoice: Invoice,
        duplicates: List[DuplicateMatchDetail],
    ) -> ValidationSummaryResponse:
        """Construct a ValidationSummaryResponse from an invoice model."""
        issues = invoice.validation_issues or []
        unresolved_errors = sum(1 for iss in issues if not iss.resolved and iss.severity == "error")
        unresolved_warnings = sum(1 for iss in issues if not iss.resolved and iss.severity == "warning")
        unresolved_info = sum(1 for iss in issues if not iss.resolved and iss.severity == "info")
        resolved_count = sum(1 for iss in issues if iss.resolved)

        return ValidationSummaryResponse(
            invoice_id=invoice.id,
            total_issues=len(issues),
            unresolved_errors=unresolved_errors,
            unresolved_warnings=unresolved_warnings,
            unresolved_info=unresolved_info,
            resolved_issues=resolved_count,
            needs_manual_review=invoice.needs_manual_review,
            is_valid=(unresolved_errors == 0 and unresolved_warnings == 0),
            issues=[ValidationIssueDetailResponse.model_validate(iss) for iss in issues],
            duplicates_detected=duplicates,
        )


validation_service = ValidationService()
