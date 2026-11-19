"""
Extraction service package.
"""

from app.services.extraction.context_models import (
    ContextPreparationResult,
    ExtractionContext,
    ExtractionContextListResponse,
    ExtractionContextSummary,
    RowRange,
)
from app.services.extraction.context_selector import (
    CandidateScoreResult,
    InvoiceCandidateDetector,
)
from app.services.extraction.context_service import (
    ContextPreparationService,
    context_service,
)
from app.services.extraction.orchestrator import (
    EvidenceValidator,
    InvoiceExtractionOrchestrator,
    MultiBatchMerger,
    extract_document_invoices,
    extraction_orchestrator,
    inline_schema_defs,
)
from app.services.extraction.prompt_builder import (
    ExtractionPrompt,
    ExtractionPromptBuilder,
)
from app.services.extraction.providers import (
    GeminiProvider,
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMMalformedResponseError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMStructuredResponse,
    LLMTimeoutError,
    LLMUsageMetadata,
    get_llm_provider,
    mask_secret,
)
from app.services.extraction.segmenter import DocumentSegmenter

__all__ = [
    # Providers
    "LLMProvider",
    "LLMStructuredResponse",
    "LLMUsageMetadata",
    "LLMProviderError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMServiceUnavailableError",
    "LLMTimeoutError",
    "LLMMalformedResponseError",
    "LLMConfigurationError",
    "mask_secret",
    "GeminiProvider",
    "get_llm_provider",
    # Context Preparation & Segmentation
    "RowRange",
    "ExtractionContext",
    "ContextPreparationResult",
    "ExtractionContextSummary",
    "ExtractionContextListResponse",
    "InvoiceCandidateDetector",
    "CandidateScoreResult",
    "DocumentSegmenter",
    "ExtractionPrompt",
    "ExtractionPromptBuilder",
    "ContextPreparationService",
    "context_service",
    # Orchestration
    "EvidenceValidator",
    "MultiBatchMerger",
    "InvoiceExtractionOrchestrator",
    "extraction_orchestrator",
    "extract_document_invoices",
    "inline_schema_defs",
]
