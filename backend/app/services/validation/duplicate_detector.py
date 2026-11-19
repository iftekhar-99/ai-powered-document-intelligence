"""
Deterministic duplicate invoice detection engine across persisted documents.
"""

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice


def normalize_invoice_number(val: Optional[str]) -> str:
    """Normalize invoice number by removing punctuation, spaces, and converting to uppercase."""
    if not val:
        return ""
    # Strip common prefixes like 'INV-', 'INV#', 'NO.', etc.
    cleaned = re.sub(r"[\s\-_#/\\:.]", "", val.upper())
    return cleaned.strip()


def normalize_party_name(val: Optional[str]) -> str:
    """Normalize supplier or vendor name by removing corporate designations and punctuation."""
    if not val:
        return ""
    cleaned = val.lower().strip()
    cleaned = re.sub(r"[,\.\'\"]", "", cleaned)
    # Strip common entity suffixes at word boundaries
    suffixes = [
        r"\b(limited|ltd|corp|corporation|inc|incorporated|llc|gmbh|co|company|sa|plc|pty|pvt)\b",
    ]
    for s in suffixes:
        cleaned = re.sub(s, "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


@dataclass
class DuplicateMatch:
    candidate_invoice: Invoice
    match_type: str  # "exact_duplicate" | "likely_duplicate"
    reasons: List[str]


class DuplicateInvoiceDetector:
    """
    Conservative duplicate invoice detection across different documents.
    Distinguishes exact duplicates, likely duplicates, and distinct invoices with shared numbers.
    """

    def __init__(self, rounding_tolerance: Decimal = Decimal("0.02")):
        self.tolerance = rounding_tolerance

    async def detect_duplicates(
        self,
        db: AsyncSession,
        invoice: Invoice,
    ) -> List[DuplicateMatch]:
        """
        Scan database for invoices that match the given invoice across different documents.
        """
        curr_norm_num = normalize_invoice_number(invoice.invoice_number)
        if not curr_norm_num or len(curr_norm_num) < 2 or curr_norm_num in ("INV", "INVOICE", "BILL"):
            # Cannot safely detect duplicates on missing or trivially short numbers
            return []

        curr_norm_supp = normalize_party_name(invoice.supplier_name)

        # Query all other invoices across different documents
        query = (
            select(Invoice)
            .where(
                Invoice.id != invoice.id,
                Invoice.document_id != invoice.document_id,
            )
            .options(selectinload(Invoice.document))
        )
        candidates = (await db.execute(query)).scalars().all()

        matches: List[DuplicateMatch] = []

        for cand in candidates:
            cand_norm_num = normalize_invoice_number(cand.invoice_number)
            if cand_norm_num != curr_norm_num:
                continue

            cand_norm_supp = normalize_party_name(cand.supplier_name)

            # Check if suppliers are distinctly different
            if curr_norm_supp and cand_norm_supp:
                if curr_norm_supp != cand_norm_supp and curr_norm_supp not in cand_norm_supp and cand_norm_supp not in curr_norm_supp:
                    # Distinct suppliers sharing a number -> DIFFERENT INVOICE!
                    continue

            # Compare totals
            totals_match = False
            total_diff = None
            if invoice.total is not None and cand.total is not None:
                total_diff = abs(invoice.total - cand.total)
                totals_match = total_diff <= self.tolerance

            # Compare currencies
            curr_match = (
                invoice.currency
                and cand.currency
                and invoice.currency.upper() == cand.currency.upper()
            )

            # Compare dates
            dates_match = False
            if invoice.invoice_date and cand.invoice_date:
                dates_match = invoice.invoice_date == cand.invoice_date

            reasons: List[str] = [
                f"Normalized invoice number '{curr_norm_num}' matches candidate #{cand.invoice_number}."
            ]

            # Classification
            if curr_norm_supp and cand_norm_supp and totals_match:
                reasons.append(f"Supplier names match: '{invoice.supplier_name}' vs '{cand.supplier_name}'.")
                reasons.append(f"Total amounts match: {invoice.currency or ''} {invoice.total}.")
                if dates_match:
                    reasons.append(f"Invoice dates match: {invoice.invoice_date}.")
                    matches.append(
                        DuplicateMatch(
                            candidate_invoice=cand,
                            match_type="exact_duplicate",
                            reasons=reasons,
                        )
                    )
                else:
                    if invoice.invoice_date or cand.invoice_date:
                        reasons.append(
                            f"Dates differ: {invoice.invoice_date} vs {cand.invoice_date}."
                        )
                    matches.append(
                        DuplicateMatch(
                            candidate_invoice=cand,
                            match_type="likely_duplicate",
                            reasons=reasons,
                        )
                    )
            elif totals_match and (not curr_norm_supp or not cand_norm_supp):
                # Number and total match, but one supplier is unextracted
                reasons.append(f"Total amounts match: {invoice.currency or ''} {invoice.total}.")
                reasons.append("Supplier name missing on one or both records.")
                matches.append(
                    DuplicateMatch(
                        candidate_invoice=cand,
                        match_type="likely_duplicate",
                        reasons=reasons,
                    )
                )
            elif curr_norm_supp and cand_norm_supp and total_diff is not None and total_diff <= Decimal("1.00"):
                # Number and supplier match, totals very close (e.g. minor fee or rounding difference)
                reasons.append(f"Supplier names match: '{invoice.supplier_name}'.")
                reasons.append(f"Totals close: {invoice.total} vs {cand.total} (diff: {total_diff}).")
                matches.append(
                    DuplicateMatch(
                        candidate_invoice=cand,
                        match_type="likely_duplicate",
                        reasons=reasons,
                    )
                )

        return matches


duplicate_detector = DuplicateInvoiceDetector()
