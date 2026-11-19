"""
Comprehensive tests for Hybrid Document Search (Task 4H).
Covers:
1. Keyword search: case-insensitivity, tokenization, multi-word matching, snippet highlights.
2. Location preservation: page_number, sheet_name, row ranges in search hits.
3. Mock embedding provider: deterministic unit vectors, cosine similarity.
4. Semantic search: vector similarity ranking, error handling when offline.
5. Hybrid search: Reciprocal Rank Fusion (RRF), boosted scores for dual matches, graceful fallback.
6. Structured invoice search: invoice number, supplier, line items, audit/validation flags.
7. Embedding lifecycle: SHA-256 duplicate prevention, backfill idempotency.
8. REST API endpoints: /search, /search/keyword, /search/semantic, /search/hybrid, /search/invoices, /search/capabilities, /search/embeddings/backfill.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator
import uuid
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.chunk import ChunkSourceType, DocumentChunk
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document import Document, DocumentStatus
from app.models.invoice import Invoice, InvoiceLineItem, ValidationIssue
from app.schemas.search import SearchMode
from app.services.search import (
    EmbeddingUnavailableError,
    GeminiEmbeddingProvider,
    MockEmbeddingProvider,
    clean_query_tokens,
    cosine_similarity,
    generate_highlighted_snippet,
    get_embedding_provider,
    set_embedding_provider,
)
from app.services.search.embedding_service import embedding_service
from app.services.search.hybrid import hybrid_search_engine
from app.services.search.invoice_search import invoice_search_engine
from app.services.search.keyword import keyword_search_engine
from app.services.search.semantic import semantic_search_engine


@pytest.fixture
def sync_session(client: TestClient):
    with client.sync_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def async_session(client: TestClient) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{client.db_path}", echo=False)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def use_mock_embedding():
    """Ensure all tests in this module run hermetically with MockEmbeddingProvider."""
    original = get_embedding_provider()
    mock_prov = MockEmbeddingProvider(dimension=768)
    set_embedding_provider(mock_prov)
    yield mock_prov
    set_embedding_provider(original)



def _seed_test_corpus(sync_session):
    """Seed sample documents, chunks, embeddings, invoices, and line items."""
    # Document 1: PDF invoice from Acme Corp
    doc1_id = uuid.uuid4()
    doc1 = Document(
        id=doc1_id,
        original_filename="acme_invoice_1001.pdf",
        stored_filename=f"s_{doc1_id}.pdf",
        file_path=f"/tmp/s_{doc1_id}.pdf",
        file_type="pdf",
        mime_type="application/pdf",
        file_size=2048,
        sha256_hash=f"hash_{doc1_id}",
        status=DocumentStatus.COMPLETED.value,
        total_chunks=2,
    )
    sync_session.add(doc1)
    sync_session.flush()

    chunk1_1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc1_id,
        chunk_index=0,
        content="Acme Corporation Invoice INV-1001. Date: 2026-05-10. Bill To: Globex International. Total Due: $1,250.00 USD.",
        extraction_method="DIGITAL_TEXT",
        source_type=ChunkSourceType.PDF_PAGE.value,
        page_number=1,
    )
    chunk1_2 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc1_id,
        chunk_index=1,
        content="Payment terms: Net 30. Direct bank transfer to Acme Corp. Server hardware maintenance services included.",
        extraction_method="DIGITAL_TEXT",
        source_type=ChunkSourceType.PDF_PAGE.value,
        page_number=1,
    )
    sync_session.add_all([chunk1_1, chunk1_2])

    inv1 = Invoice(
        id=uuid.uuid4(),
        document_id=doc1_id,
        invoice_number="INV-1001",
        invoice_date=date(2026, 5, 10),
        supplier_name="Acme Corporation",
        customer_name="Globex International",
        subtotal=Decimal("1100.00"),
        tax=Decimal("150.00"),
        total=Decimal("1250.00"),
        currency="USD",
        needs_manual_review=False,
        is_manually_corrected=False,
    )
    sync_session.add(inv1)
    sync_session.flush()

    li1 = InvoiceLineItem(
        id=uuid.uuid4(),
        invoice_id=inv1.id,
        description="High-performance Rack Server maintenance",
        quantity=Decimal("1"),
        unit_price=Decimal("1100.00"),
        line_total=Decimal("1100.00"),
    )
    sync_session.add(li1)

    # Document 2: Excel sheet from Wayne Tech
    doc2_id = uuid.uuid4()
    doc2 = Document(
        id=doc2_id,
        original_filename="wayne_q2_expenses.xlsx",
        stored_filename=f"s_{doc2_id}.xlsx",
        file_path=f"/tmp/s_{doc2_id}.xlsx",
        file_type="xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        file_size=4096,
        sha256_hash=f"hash_{doc2_id}",
        status=DocumentStatus.COMPLETED.value,
        total_chunks=1,
    )
    sync_session.add(doc2)
    sync_session.flush()

    chunk2_1 = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc2_id,
        chunk_index=0,
        content="Wayne Enterprises Q2 billing statement for cloud compute and quantum encryption consulting. Total: EUR 8500.00.",
        extraction_method="TABULAR_PARSER",
        source_type=ChunkSourceType.SPREADSHEET_SHEET.value,
        sheet_name="ConsultingServices",
        row_start=1,
        row_end=25,
    )
    sync_session.add(chunk2_1)

    inv2 = Invoice(
        id=uuid.uuid4(),
        document_id=doc2_id,
        invoice_number="WT-9921",
        invoice_date=date(2026, 6, 1),
        supplier_name="Wayne Enterprises",
        customer_name="Gotham Municipal",
        subtotal=Decimal("8000.00"),
        tax=Decimal("500.00"),
        total=Decimal("8500.00"),
        currency="EUR",
        needs_manual_review=True,
        is_manually_corrected=False,
    )
    sync_session.add(inv2)
    sync_session.flush()

    issue2 = ValidationIssue(
        id=uuid.uuid4(),
        invoice_id=inv2.id,
        field_name="total",
        issue_type="tax_calculation_mismatch",
        severity="error",
        description="Tax mismatch: expected 1600.00 but got 500.00",
        resolved=False,
    )
    sync_session.add(issue2)

    sync_session.commit()

    return {
        "doc1": doc1,
        "chunk1_1": chunk1_1,
        "chunk1_2": chunk1_2,
        "inv1": inv1,
        "doc2": doc2,
        "chunk2_1": chunk2_1,
        "inv2": inv2,
    }


# ==============================================================================
# Unit Tests: Query Utilities & Snippet Highlighting
# ==============================================================================


def test_clean_query_tokens():
    tokens = clean_query_tokens("Acme Corp!  INV-1001? (Total: $1250)")
    assert "acme" in tokens
    assert "corp" in tokens
    assert "inv-1001" in tokens
    assert "total" in tokens


def test_generate_highlighted_snippet():
    text = "Payment terms: Net 30. Direct bank transfer to Acme Corp. Server maintenance."
    snippet = generate_highlighted_snippet(text, ["acme", "server"])
    assert "**Acme**" in snippet or "**acme**" in snippet
    assert "**Server**" in snippet or "**server**" in snippet


def test_cosine_similarity():
    # Identity
    v1 = [1.0, 0.0, 0.0]
    assert pytest.approx(cosine_similarity(v1, v1), 0.001) == 1.0

    # Orthogonal
    v2 = [0.0, 1.0, 0.0]
    assert pytest.approx(cosine_similarity(v1, v2), 0.001) == 0.0

    # Opposite
    v3 = [-1.0, 0.0, 0.0]
    assert pytest.approx(cosine_similarity(v1, v3), 0.001) == -1.0


# ==============================================================================
# Integration Tests: Search Service & Engines
# ==============================================================================


@pytest.mark.asyncio
async def test_keyword_search_engine(async_session, sync_session):
    data = _seed_test_corpus(sync_session)

    # 1. Basic keyword hit
    res = await keyword_search_engine.search(async_session, query="Acme")
    assert res.total >= 1
    assert res.mode == "keyword"
    assert res.items[0].document_filename == "acme_invoice_1001.pdf"
    assert res.items[0].page_number == 1
    assert res.items[0].match_type == "keyword"

    # 2. Excel sheet location preservation
    res_excel = await keyword_search_engine.search(async_session, query="quantum encryption")
    assert res_excel.total == 1
    item = res_excel.items[0]
    assert item.sheet_name == "ConsultingServices"
    assert item.row_start == 1
    assert item.row_end == 25

    # 3. Filter by currency
    res_cur = await keyword_search_engine.search(async_session, query="Total", currency="EUR")
    assert res_cur.total == 1
    assert res_cur.items[0].currency == "EUR"


@pytest.mark.asyncio
async def test_semantic_search_engine(async_session, sync_session, use_mock_embedding):
    data = _seed_test_corpus(sync_session)

    # First generate embeddings via embedding service
    backfill_res = await embedding_service.backfill_all_unembedded(async_session)
    assert backfill_res.embedded_count >= 3

    # Semantic search
    res = await semantic_search_engine.search(async_session, query="hardware server maintenance")
    assert res.total >= 1
    assert res.mode == "semantic"
    assert res.items[0].match_type == "semantic"
    assert res.items[0].score > 0.0


@pytest.mark.asyncio
async def test_hybrid_search_and_rrf(async_session, sync_session, use_mock_embedding):
    data = _seed_test_corpus(sync_session)

    # Embed chunks
    await embedding_service.backfill_all_unembedded(async_session)

    # Hybrid search query
    res = await hybrid_search_engine.search(async_session, query="Acme Corp INV-1001")
    assert res.total >= 1
    assert res.mode == "hybrid"
    assert res.fallback_mode is False

    # First item should be hybrid match
    top_hit = res.items[0]
    assert top_hit.match_type in ("hybrid", "keyword")
    assert top_hit.score > 0.0


@pytest.mark.asyncio
async def test_hybrid_search_fallback_when_semantic_unavailable(async_session, sync_session):
    data = _seed_test_corpus(sync_session)

    # Configure a mock provider that reports unavailable
    broken_mock = MockEmbeddingProvider(dimension=768, is_available=False)
    set_embedding_provider(broken_mock)

    res = await hybrid_search_engine.search(async_session, query="Acme Corp")
    assert res.mode == "hybrid"
    assert res.fallback_mode is True
    assert "unavailable" in res.fallback_reason.lower()
    assert len(res.items) >= 1


@pytest.mark.asyncio
async def test_structured_invoice_search(async_session, sync_session):
    data = _seed_test_corpus(sync_session)

    # 1. Search by invoice number
    res1 = await invoice_search_engine.search(async_session, query="INV-1001")
    assert res1.total == 1
    assert res1.items[0].invoice_number == "INV-1001"
    assert "invoice_number" in res1.items[0].matched_fields

    # 2. Search by line item description
    res2 = await invoice_search_engine.search(async_session, query="Rack Server")
    assert res2.total == 1
    assert "line_items" in res2.items[0].matched_fields
    assert res2.items[0].supplier_name == "Acme Corporation"

    # 3. Filter by validity (Wayne Tech has an unresolved error issue)
    res_valid = await invoice_search_engine.search(async_session, is_valid=True)
    assert any(i.invoice_number == "INV-1001" for i in res_valid.items)
    assert not any(i.invoice_number == "WT-9921" for i in res_valid.items)

    # 4. Filter by amount range
    res_amt = await invoice_search_engine.search(async_session, amount_min=Decimal("5000.00"))
    assert res_amt.total == 1
    assert res_amt.items[0].invoice_number == "WT-9921"


@pytest.mark.asyncio
async def test_embedding_lifecycle_and_deduplication(async_session, sync_session, use_mock_embedding):
    data = _seed_test_corpus(sync_session)

    # First backfill
    b1 = await embedding_service.backfill_all_unembedded(async_session)
    assert b1.embedded_count >= 3

    # Second backfill should skip all already embedded chunks (duplicate hash)
    b2 = await embedding_service.backfill_all_unembedded(async_session)
    assert b2.embedded_count == 0
    assert b2.skipped_count >= 3


@pytest.mark.asyncio
async def test_stale_embedding_exclusion_and_migration(async_session, sync_session, use_mock_embedding):
    data = _seed_test_corpus(sync_session)

    # 1. Manually insert an obsolete embedding with legacy model name 'text-embedding-004'
    obsolete_emb = ChunkEmbedding(
        id=uuid.uuid4(),
        chunk_id=data["chunk1_1"].id,
        document_id=data["doc1"].id,
        provider="gemini",
        model_name="text-embedding-004",
        dimension=768,
        embedding=[0.01] * 768,
        chunk_hash="old_hash_123",
        status="completed",
    )
    async_session.add(obsolete_emb)
    await async_session.commit()

    # 2. Mark stale embeddings
    stale_count = await embedding_service.mark_stale_embeddings(async_session)
    assert stale_count >= 1

    # 3. Verify semantic search excludes stale embeddings
    res = await semantic_search_engine.search(
        async_session,
        query="Acme Corporation",
        document_id=data["doc1"].id,
    )
    assert not any(item.chunk_id == data["chunk1_1"].id for item in res.items)

    # 4. Backfill regenerates stale embedding with current active model
    b_res = await embedding_service.backfill_all_unembedded(async_session)
    assert b_res.embedded_count >= 1

    # 5. Now search includes the regenerated chunk with current active model
    res_after = await semantic_search_engine.search(
        async_session,
        query="Acme Corporation",
        document_id=data["doc1"].id,
    )
    assert any(item.chunk_id == data["chunk1_1"].id for item in res_after.items)




# ==============================================================================
# REST API Endpoint Tests
# ==============================================================================


def test_api_search_capabilities(client: TestClient, sync_session, use_mock_embedding):
    data = _seed_test_corpus(sync_session)

    resp = client.get("/api/v1/search/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["keyword_search_available"] is True
    assert body["embedding_dimension"] == 768
    assert "total_chunks" in body


def test_api_unified_search_endpoint(client: TestClient, sync_session, use_mock_embedding):
    data = _seed_test_corpus(sync_session)

    # 1. Backfill embeddings
    bf_resp = client.post("/api/v1/search/embeddings/backfill?batch_size=50")
    assert bf_resp.status_code == 200

    # 2. Unified hybrid search
    resp = client.get("/api/v1/search?q=Acme&mode=hybrid")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "hybrid"
    assert len(body["items"]) >= 1

    # 3. Direct keyword endpoint
    kw_resp = client.get("/api/v1/search/keyword?q=Globex")
    assert kw_resp.status_code == 200
    assert kw_resp.json()["total"] >= 1

    # 4. Direct semantic endpoint
    sem_resp = client.get("/api/v1/search/semantic?q=server+maintenance")
    assert sem_resp.status_code == 200
    assert sem_resp.json()["mode"] == "semantic"

    # 5. Direct invoice search endpoint
    inv_resp = client.get("/api/v1/search/invoices?q=Wayne")
    assert inv_resp.status_code == 200
    assert inv_resp.json()["total"] == 1
    assert inv_resp.json()["items"][0]["supplier_name"] == "Wayne Enterprises"


def test_gemini_embedding_provider_initialization():
    provider = GeminiEmbeddingProvider(
        api_key="test_dummy_key_1234567890",
        model="gemini-embedding-2",
        dimension=768,
    )
    assert provider.provider_name == "gemini"
    assert provider.model_name == "gemini-embedding-2"
    assert provider.dimension == 768
    is_avail, reason = provider.check_availability()
    assert is_avail is True
    assert "gemini-embedding-2" in reason
    assert "test_dummy_key_1234567890" not in reason
