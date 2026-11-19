"""
Heuristic invoice candidate detector for document chunks and pages.

Analyzes text content using weighted pattern matching, structural markers,
regexes, and financial terms to classify content and extract candidate metadata.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set


# Regex patterns for key financial structures
INVOICE_NUMBER_PATTERNS = [
    re.compile(r"(?i)\binvoice\s*(?:no|num|number|#|id)?[ \t#.:]+([a-z0-9][a-z0-9_\-\/]{2,30})\b"),
    re.compile(r"(?i)\b(?:inv|bill|po)\s*[:#.]+[ \t]*([a-z0-9_\-\/]{3,30})\b"),
    re.compile(r"\b([A-Z]{2,6}-\d{3,10}(?:-[A-Z0-9]+)?)\b"),
]

PAGE_NUMBER_PATTERN = re.compile(r"(?i)\bpage\s*(\d+)\s*(?:of|\/)\s*(\d+)\b")
PAGE_SINGLE_PATTERN = re.compile(r"(?i)\bpage\s*(\d+)\b")

CONTINUATION_PATTERNS = [
    re.compile(r"(?i)\bcontinued\s*(?:on|from)?\s*(?:next\s*page|page)?\b"),
    re.compile(r"(?i)\bbalance\s*brought\s*forward\b"),
    re.compile(r"(?i)\bcarried\s*forward\b"),
    re.compile(r"(?i)\bsubtotal\s*continued\b"),
]

TOTAL_PATTERNS = [
    re.compile(r"(?i)\b(?:grand\s*total|total\s*due|amount\s*due|balance\s*due|total\s*amount)[\s:$]*(\d+(?:,\d{3})*(?:\.\d{2})?)\b"),
    re.compile(r"(?i)\btotal[\s:$]+([\$€£¥₹]?\s*\d+(?:,\d{3})*(?:\.\d{2})?)\b"),
]

CURRENCY_PATTERNS = [
    re.compile(r"[\$€£¥₹]"),
    re.compile(r"\b(?:USD|EUR|GBP|CAD|AUD|JPY|CHF|INR)\b"),
]

# Weighted feature indicators
FEATURE_WEIGHTS = {
    "invoice_heading": 0.35,
    "invoice_number": 0.30,
    "financial_total": 0.20,
    "line_item_table": 0.20,
    "parties_header": 0.15,
    "tax_indicator": 0.10,
    "payment_terms": 0.10,
    "currency_symbol": 0.05,
}


@dataclass
class CandidateScoreResult:
    """Detailed score evaluation of a document chunk or text snippet."""
    score: float
    is_invoice_candidate: bool
    candidate_type: str
    matching_indicators: List[str] = field(default_factory=list)
    detected_invoice_numbers: List[str] = field(default_factory=list)
    has_invoice_start_indicators: bool = False
    has_continuation_indicators: bool = False
    page_current: Optional[int] = None
    page_total: Optional[int] = None
    suggested_review_status: bool = False
    review_reasons: List[str] = field(default_factory=list)


class InvoiceCandidateDetector:
    """
    Configurable candidate detector for identifying invoice pages,
    continuation markers, and financial signals.
    """

    def __init__(self, candidate_threshold: float = 0.35):
        self.candidate_threshold = candidate_threshold

    def evaluate_text(self, text: str) -> CandidateScoreResult:
        """
        Evaluates a block of text and returns a CandidateScoreResult.
        Does not treat keyword matches as absolute proof.
        """
        if not text or not text.strip():
            return CandidateScoreResult(
                score=0.0,
                is_invoice_candidate=False,
                candidate_type="unknown",
                matching_indicators=["empty_content"],
            )

        text_lower = text.lower()
        indicators: List[str] = []
        raw_score = 0.0
        review_reasons: List[str] = []

        # 1. Invoice heading detection
        has_heading = False
        if any(h in text_lower for h in [
            "tax invoice", "commercial invoice", "vat invoice",
            "proforma invoice", "invoice / bill", "facture", "rechnung",
        ]):
            indicators.append("explicit_invoice_heading")
            raw_score += FEATURE_WEIGHTS["invoice_heading"]
            has_heading = True
        elif "invoice" in text_lower:
            indicators.append("invoice_keyword")
            raw_score += FEATURE_WEIGHTS["invoice_heading"] * 0.8
            has_heading = True
        elif any(r in text_lower for r in ["receipt", "sales receipt", "cash receipt"]):
            indicators.append("receipt_keyword")
            raw_score += 0.25

        # 2. Invoice number extraction
        raw_numbers: List[str] = []
        stop_words = {"date", "for", "the", "page", "due", "total", "and", "invoice", "bill", "receipt"}
        for pattern in INVOICE_NUMBER_PATTERNS:
            for match in pattern.finditer(text):
                val = match.group(1).strip(" :.-_/#")
                if len(val) >= 3 and val.lower() not in stop_words:
                    if val not in raw_numbers:
                        raw_numbers.append(val)

        # Deduplicate and prioritize longer identifiers (e.g. keep INV-001 over 001)
        detected_numbers: List[str] = []
        for num in sorted(raw_numbers, key=len, reverse=True):
            if not any(num != existing and num in existing for existing in detected_numbers):
                detected_numbers.append(num)

        if detected_numbers:
            indicators.append(f"invoice_numbers_found({len(detected_numbers)})")
            raw_score += FEATURE_WEIGHTS["invoice_number"]

        # 3. Financial totals
        has_total = False
        for pat in TOTAL_PATTERNS:
            if pat.search(text):
                has_total = True
                break
        if has_total or any(t in text_lower for t in ["subtotal", "grand total", "total due", "amount due", "balance due"]):
            indicators.append("financial_total_found")
            raw_score += FEATURE_WEIGHTS["financial_total"]

        # 4. Line item table markers
        table_markers = 0
        for marker in ["unit price", "unit cost", "qty", "quantity", "description", "line total", "extended price", "item no"]:
            if marker in text_lower:
                table_markers += 1
        if table_markers >= 2:
            indicators.append(f"line_item_table_markers({table_markers})")
            raw_score += FEATURE_WEIGHTS["line_item_table"]

        # 5. Bill To / Ship To / Parties
        if any(p in text_lower for p in ["bill to", "sold to", "ship to", "customer:", "supplier:", "vendor:"]):
            indicators.append("parties_header_found")
            raw_score += FEATURE_WEIGHTS["parties_header"]

        # 6. Tax / VAT / GST
        if any(tx in text_lower for tx in ["vat", "gst", "sales tax", "tax rate", "tax amount"]):
            indicators.append("tax_indicator_found")
            raw_score += FEATURE_WEIGHTS["tax_indicator"]

        # 7. Payment terms / Due date
        if any(pm in text_lower for pm in ["payment terms", "due date", "net 30", "net 15", "due upon receipt", "remit to"]):
            indicators.append("payment_terms_found")
            raw_score += FEATURE_WEIGHTS["payment_terms"]

        # 8. Currency symbols
        has_currency = any(cp.search(text) for cp in CURRENCY_PATTERNS)
        if has_currency:
            indicators.append("currency_symbol_found")
            raw_score += FEATURE_WEIGHTS["currency_symbol"]

        # 9. Continuation and page indicators
        page_curr = None
        page_tot = None
        page_match = PAGE_NUMBER_PATTERN.search(text)
        if page_match:
            try:
                page_curr = int(page_match.group(1))
                page_tot = int(page_match.group(2))
                indicators.append(f"page_x_of_y({page_curr}/{page_tot})")
            except ValueError:
                pass
        else:
            single_match = PAGE_SINGLE_PATTERN.search(text)
            if single_match:
                try:
                    page_curr = int(single_match.group(1))
                    indicators.append(f"page_number({page_curr})")
                except ValueError:
                    pass

        has_continuation_marker = any(cp.search(text) for cp in CONTINUATION_PATTERNS)
        if has_continuation_marker:
            indicators.append("continuation_marker_found")

        # Determine start vs continuation indicators
        has_start = False
        has_cont = False

        if page_curr is not None and page_curr > 1:
            has_cont = True
        elif has_continuation_marker:
            has_cont = True

        if (page_curr == 1 or page_curr is None) and (has_heading or (detected_numbers and "bill to" in text_lower)):
            has_start = True

        # Normalized score capped at 1.0
        final_score = min(1.0, round(raw_score, 3))
        is_candidate = final_score >= self.candidate_threshold

        # Candidate type classification
        candidate_type = "unknown"
        if is_candidate:
            if "receipt_keyword" in indicators and "invoice" not in text_lower:
                candidate_type = "receipt"
            elif any(s in text_lower for s in ["balance sheet", "income statement", "cash flow statement"]):
                candidate_type = "financial_statement"
            else:
                candidate_type = "invoice"
        else:
            if any(s in text_lower for s in ["balance sheet", "financial statement", "profit and loss"]):
                candidate_type = "financial_statement"
            elif len(text.strip()) > 30:
                candidate_type = "other"

        # Check for ambiguity requiring manual review
        suggest_review = False
        if len(detected_numbers) > 2:
            suggest_review = True
            review_reasons.append(f"Multiple distinct invoice numbers detected on single page/chunk: {detected_numbers}")

        if is_candidate and not detected_numbers and not has_total:
            suggest_review = True
            review_reasons.append("Invoice candidate detected but missing explicit invoice number and financial total")

        return CandidateScoreResult(
            score=final_score,
            is_invoice_candidate=is_candidate,
            candidate_type=candidate_type,
            matching_indicators=indicators,
            detected_invoice_numbers=detected_numbers,
            has_invoice_start_indicators=has_start,
            has_continuation_indicators=has_cont,
            page_current=page_curr,
            page_total=page_tot,
            suggested_review_status=suggest_review,
            review_reasons=review_reasons,
        )
