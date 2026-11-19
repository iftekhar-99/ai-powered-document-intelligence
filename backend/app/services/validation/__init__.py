"""
Financial data validation engine and duplicate invoice detection package.
"""

from app.services.validation.duplicate_detector import (
    DuplicateInvoiceDetector,
    DuplicateMatch,
    duplicate_detector,
    normalize_invoice_number,
    normalize_party_name,
)
from app.services.validation.rules import (
    DetectedIssue,
    ValidationRuleEngine,
)
from app.services.validation.service import (
    ValidationService,
    validation_service,
)

__all__ = [
    "ValidationRuleEngine",
    "DetectedIssue",
    "DuplicateInvoiceDetector",
    "DuplicateMatch",
    "duplicate_detector",
    "normalize_invoice_number",
    "normalize_party_name",
    "ValidationService",
    "validation_service",
]
