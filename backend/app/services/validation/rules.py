"""
Deterministic financial validation rules for invoices and itemized line items.
"""

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import List, Optional
from uuid import UUID

from app.models.invoice import Invoice, InvoiceLineItem


@dataclass
class DetectedIssue:
    field_name: str
    issue_type: str
    severity: str  # "error", "warning", "info"
    description: str
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    line_item_id: Optional[UUID] = None
    related_invoice_id: Optional[UUID] = None
    related_document_id: Optional[UUID] = None


class ValidationRuleEngine:
    """
    Core deterministic financial validation engine.
    Executes arithmetic, field presence, and line item integrity checks without LLM calls.
    """

    def __init__(self, rounding_tolerance: Decimal = Decimal("0.02")):
        self.tolerance = rounding_tolerance

    def validate_required_fields(self, invoice: Invoice) -> List[DetectedIssue]:
        """Check for missing or unusable mandatory header fields."""
        issues: List[DetectedIssue] = []

        # 1. Invoice Number (Required - Error)
        if not invoice.invoice_number or not invoice.invoice_number.strip():
            issues.append(
                DetectedIssue(
                    field_name="invoice_number",
                    issue_type="missing_invoice_number",
                    severity="error",
                    description="Missing invoice identification number. Header could not be identified.",
                    expected_value="Valid invoice number string",
                    observed_value=None,
                )
            )

        # 2. Total Amount (Required - Error)
        if invoice.total is None:
            issues.append(
                DetectedIssue(
                    field_name="total",
                    issue_type="missing_total_amount",
                    severity="error",
                    description="Missing invoice total amount. Financial balance due is required.",
                    expected_value="Positive monetary amount",
                    observed_value=None,
                )
            )

        # 3. Supplier Name (Required - Warning)
        if not invoice.supplier_name or not invoice.supplier_name.strip():
            issues.append(
                DetectedIssue(
                    field_name="supplier_name",
                    issue_type="missing_supplier_name",
                    severity="warning",
                    description="Missing vendor / supplier legal or trading entity name.",
                    expected_value="Supplier company name",
                    observed_value=None,
                )
            )

        # 4. Invoice Date (Required - Warning)
        if invoice.invoice_date is None:
            issues.append(
                DetectedIssue(
                    field_name="invoice_date",
                    issue_type="missing_invoice_date",
                    severity="warning",
                    description="Missing invoice issue date. Billing date could not be established.",
                    expected_value="Valid calendar date (YYYY-MM-DD)",
                    observed_value=None,
                )
            )

        # 5. Currency (Required - Warning)
        if not invoice.currency or not invoice.currency.strip():
            issues.append(
                DetectedIssue(
                    field_name="currency",
                    issue_type="missing_currency",
                    severity="warning",
                    description="Missing currency code (e.g. USD, EUR, GBP).",
                    expected_value="ISO currency code",
                    observed_value=None,
                )
            )

        # 6. Subtotal (Warning if missing when tax or line items exist)
        if invoice.subtotal is None:
            has_line_items = bool(invoice.line_items and len(invoice.line_items) > 0)
            if has_line_items or invoice.tax is not None:
                issues.append(
                    DetectedIssue(
                        field_name="subtotal",
                        issue_type="missing_subtotal",
                        severity="warning",
                        description="Pre-tax subtotal is missing but tax or line items are present.",
                        expected_value="Pre-tax subtotal amount",
                        observed_value=None,
                    )
                )

        # 7. Customer Name (Informational if missing)
        if not invoice.customer_name or not invoice.customer_name.strip():
            issues.append(
                DetectedIssue(
                    field_name="customer_name",
                    issue_type="missing_customer_name",
                    severity="info",
                    description="Customer / Bill-to counterparty name is omitted.",
                    expected_value="Customer name",
                    observed_value=None,
                )
            )

        return issues

    def validate_financial_arithmetic(self, invoice: Invoice) -> List[DetectedIssue]:
        """Perform exact Decimal arithmetic comparisons with configurable tolerance."""
        issues: List[DetectedIssue] = []

        # 1. Negative monetary amounts
        if invoice.total is not None and invoice.total < 0:
            issues.append(
                DetectedIssue(
                    field_name="total",
                    issue_type="negative_total_amount",
                    severity="error",
                    description=f"Invoice total cannot be negative ({invoice.total}).",
                    expected_value="Amount >= 0",
                    observed_value=str(invoice.total),
                )
            )

        if invoice.subtotal is not None and invoice.subtotal < 0:
            issues.append(
                DetectedIssue(
                    field_name="subtotal",
                    issue_type="negative_subtotal_amount",
                    severity="error",
                    description=f"Invoice subtotal cannot be negative ({invoice.subtotal}).",
                    expected_value="Amount >= 0",
                    observed_value=str(invoice.subtotal),
                )
            )

        if invoice.tax is not None and invoice.tax < 0:
            issues.append(
                DetectedIssue(
                    field_name="tax",
                    issue_type="negative_tax_amount",
                    severity="warning",
                    description=f"Negative tax amount detected ({invoice.tax}). Verify whether this represents a tax withholding or refund.",
                    expected_value="Tax >= 0",
                    observed_value=str(invoice.tax),
                )
            )

        # 2. Subtotal + Tax versus Total
        if invoice.subtotal is not None and invoice.total is not None:
            if invoice.tax is not None:
                expected_total = invoice.subtotal + invoice.tax
                diff = abs(expected_total - invoice.total)
                if diff > self.tolerance:
                    issues.append(
                        DetectedIssue(
                            field_name="total",
                            issue_type="subtotal_tax_total_mismatch",
                            severity="warning" if diff <= Decimal("1.00") else "error",
                            description=(
                                f"Invoice total ({invoice.currency or ''} {invoice.total}) does not match "
                                f"subtotal ({invoice.subtotal}) + tax ({invoice.tax}) = {expected_total}. "
                                f"Discrepancy of {invoice.currency or ''} {diff} may indicate unextracted shipping, fees, or discounts."
                            ),
                            expected_value=str(expected_total),
                            observed_value=str(invoice.total),
                        )
                    )
            else:
                # Tax is None
                if invoice.subtotal > invoice.total + self.tolerance:
                    diff = invoice.subtotal - invoice.total
                    issues.append(
                        DetectedIssue(
                            field_name="subtotal",
                            issue_type="subtotal_exceeds_total",
                            severity="warning",
                            description=(
                                f"Invoice subtotal ({invoice.subtotal}) exceeds total balance ({invoice.total}) "
                                f"by {diff} without recorded discounts."
                            ),
                            expected_value=f"Subtotal <= {invoice.total}",
                            observed_value=str(invoice.subtotal),
                        )
                    )

        # 3. Sum of Line Items versus Subtotal / Total
        if invoice.line_items and len(invoice.line_items) > 0:
            has_line_totals = any(li.line_total is not None for li in invoice.line_items)
            if has_line_totals:
                line_items_sum = sum(
                    (li.line_total for li in invoice.line_items if li.line_total is not None),
                    Decimal("0.00"),
                )

                if invoice.subtotal is not None:
                    diff = abs(line_items_sum - invoice.subtotal)
                    if diff > self.tolerance:
                        issues.append(
                            DetectedIssue(
                                field_name="subtotal",
                                issue_type="line_items_subtotal_mismatch",
                                severity="warning",
                                description=(
                                    f"Sum of itemized line totals ({line_items_sum}) does not match "
                                    f"invoice subtotal ({invoice.subtotal}). Discrepancy: {diff}."
                                ),
                                expected_value=str(invoice.subtotal),
                                observed_value=str(line_items_sum),
                            )
                        )
                elif invoice.total is not None and invoice.tax is not None:
                    expected_total_from_lines = line_items_sum + invoice.tax
                    diff = abs(expected_total_from_lines - invoice.total)
                    if diff > self.tolerance:
                        issues.append(
                            DetectedIssue(
                                field_name="total",
                                issue_type="line_items_total_mismatch",
                                severity="warning",
                                description=(
                                    f"Sum of itemized lines ({line_items_sum}) + tax ({invoice.tax}) = "
                                    f"{expected_total_from_lines} does not match total ({invoice.total}). Discrepancy: {diff}."
                                ),
                                expected_value=str(invoice.total),
                                observed_value=str(expected_total_from_lines),
                            )
                        )

        return issues

    def validate_line_items(self, invoice: Invoice) -> List[DetectedIssue]:
        """Validate itemized line rows for missing fields, negative values, and arithmetic errors."""
        issues: List[DetectedIssue] = []
        if not invoice.line_items:
            return issues

        seen_lines: List[InvoiceLineItem] = []

        for idx, li in enumerate(invoice.line_items):
            # 1. Missing Description
            if not li.description or not li.description.strip():
                issues.append(
                    DetectedIssue(
                        field_name="description",
                        issue_type="missing_line_description",
                        severity="error",
                        description=f"Line item #{idx + 1} has an empty or blank description.",
                        expected_value="Item / service description",
                        observed_value=None,
                        line_item_id=li.id,
                    )
                )

            # 2. Negative Quantities or Prices
            if li.quantity is not None and li.quantity < 0:
                issues.append(
                    DetectedIssue(
                        field_name="quantity",
                        issue_type="negative_line_quantity",
                        severity="warning",
                        description=f"Line item #{idx + 1} ('{li.description}') has a negative quantity ({li.quantity}).",
                        expected_value="Quantity >= 0",
                        observed_value=str(li.quantity),
                        line_item_id=li.id,
                    )
                )

            if li.unit_price is not None and li.unit_price < 0:
                issues.append(
                    DetectedIssue(
                        field_name="unit_price",
                        issue_type="negative_unit_price",
                        severity="warning",
                        description=f"Line item #{idx + 1} ('{li.description}') has a negative unit price ({li.unit_price}).",
                        expected_value="Unit price >= 0",
                        observed_value=str(li.unit_price),
                        line_item_id=li.id,
                    )
                )

            if li.line_total is not None and li.line_total < 0:
                issues.append(
                    DetectedIssue(
                        field_name="line_total",
                        issue_type="negative_line_total",
                        severity="warning",
                        description=f"Line item #{idx + 1} ('{li.description}') has a negative line total ({li.line_total}).",
                        expected_value="Line total >= 0",
                        observed_value=str(li.line_total),
                        line_item_id=li.id,
                    )
                )

            # 3. Arithmetic: Quantity * Unit Price vs Line Total
            if li.quantity is not None and li.unit_price is not None and li.line_total is not None:
                expected_total = li.quantity * li.unit_price
                diff = abs(expected_total - li.line_total)
                if diff > self.tolerance:
                    issues.append(
                        DetectedIssue(
                            field_name="line_total",
                            issue_type="line_item_math_mismatch",
                            severity="warning",
                            description=(
                                f"Line item #{idx + 1} ('{li.description}') calculation discrepancy: "
                                f"quantity ({li.quantity}) * unit price ({li.unit_price}) = {expected_total}, "
                                f"but line total is {li.line_total} (diff: {diff})."
                            ),
                            expected_value=str(expected_total),
                            observed_value=str(li.line_total),
                            line_item_id=li.id,
                        )
                    )

            # 4. Check for duplicate-looking line items in same invoice
            clean_desc = re.sub(r"\s+", " ", li.description.lower().strip())
            for prev_idx, prev_li in enumerate(seen_lines):
                prev_clean_desc = re.sub(r"\s+", " ", prev_li.description.lower().strip())
                if clean_desc == prev_clean_desc and len(clean_desc) > 3:
                    if (
                        li.quantity == prev_li.quantity
                        and li.unit_price == prev_li.unit_price
                        and li.line_total == prev_li.line_total
                        and li.line_total is not None
                    ):
                        issues.append(
                            DetectedIssue(
                                field_name="line_items",
                                issue_type="duplicate_line_item",
                                severity="warning",
                                description=(
                                    f"Duplicate line item detected: row #{idx + 1} appears identical to row #{prev_idx + 1} "
                                    f"('{li.description}', amount: {li.line_total}). Verify if billed twice."
                                ),
                                expected_value="Unique itemized entry",
                                observed_value=str(li.line_total),
                                line_item_id=li.id,
                            )
                        )
            seen_lines.append(li)

        return issues
