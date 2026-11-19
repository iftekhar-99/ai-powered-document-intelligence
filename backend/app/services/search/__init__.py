"""
Search package initialization exporting engines, service facade, and embedding providers.
"""

from app.services.search.embedding_service import EmbeddingService, embedding_service
from app.services.search.embeddings import (
    EmbeddingAuthError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    GeminiEmbeddingProvider,
    MockEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
    set_embedding_provider,
)
from app.services.search.hybrid import HybridSearchEngine, hybrid_search_engine
from app.services.search.invoice_search import (
    StructuredInvoiceSearchEngine,
    invoice_search_engine,
)
from app.services.search.keyword import (
    KeywordSearchEngine,
    clean_query_tokens,
    generate_highlighted_snippet,
    keyword_search_engine,
)
from app.services.search.semantic import SemanticSearchEngine, semantic_search_engine
from app.services.search.service import SearchService, search_service

__all__ = [
    "clean_query_tokens",
    "generate_highlighted_snippet",
    "KeywordSearchEngine",
    "keyword_search_engine",
    "SemanticSearchEngine",
    "semantic_search_engine",
    "HybridSearchEngine",
    "hybrid_search_engine",
    "StructuredInvoiceSearchEngine",
    "invoice_search_engine",
    "EmbeddingService",
    "embedding_service",
    "SearchService",
    "search_service",
    "EmbeddingError",
    "EmbeddingUnavailableError",
    "EmbeddingAuthError",
    "EmbeddingProvider",
    "GeminiEmbeddingProvider",
    "MockEmbeddingProvider",
    "cosine_similarity",
    "get_embedding_provider",
    "set_embedding_provider",
]
