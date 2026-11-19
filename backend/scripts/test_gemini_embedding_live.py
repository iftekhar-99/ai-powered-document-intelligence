#!/usr/bin/env python3
"""
Live smoke test script for Gemini Embedding (gemini-embedding-2).
Verifies:
1. Real Gemini API embedding generation with gemini-embedding-2.
2. Vector shape (768-dim), non-emptiness, and finite values.
3. Database persistence via EmbeddingService.
4. Real query embedding generation and cosine similarity retrieval via SemanticSearchEngine.
5. Complete cleanup of synthetic test records.

SECURITY RULE: NEVER print, log, display, or expose GEMINI_API_KEY.
"""

import asyncio
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import sys
import time
import uuid

# 1. Path resolution and environment setup
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for path_dir in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if path_dir not in sys.path:
        sys.path.insert(0, path_dir)

from dotenv import load_dotenv

env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(dotenv_path=env_file, override=True)
else:
    load_dotenv(dotenv_path=Path(".env"), override=True)

from app.core.config import settings
from app.db.session import async_session_maker
from app.models.chunk import ChunkSourceType, DocumentChunk
from app.models.chunk_embedding import ChunkEmbedding
from app.models.document import Document, DocumentStatus
from app.services.search.embedding_service import embedding_service
from app.services.search.embeddings.gemini import GeminiEmbeddingProvider
from app.services.search.semantic import semantic_search_engine


def mask_secret(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "[REDACTED_API_KEY]")


async def run_live_embedding_smoke_test() -> int:
    api_key = (settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")).strip()
    model_name = (
        getattr(settings, "GEMINI_EMBEDDING_MODEL", None)
        or getattr(settings, "EMBEDDING_MODEL", "gemini-embedding-2")
    ).strip()
    api_version = (
        getattr(settings, "GOOGLE_GENAI_API_VERSION", "v1beta")
    ).strip()
    target_dim = getattr(settings, "EMBEDDING_DIMENSION", 768)

    print("=" * 72)
    print("TASK 4H.1: Gemini Live Semantic Retrieval Smoke Test")
    print("=" * 72)

    # 1. Credentials and Configuration verification
    print("\n[1] Configuration & Credentials Check:")
    if not api_key:
        print("  • ERROR: GEMINI_API_KEY is not configured in environment.")
        return 1

    print(f"  • GEMINI_API_KEY: PRESENT ({len(api_key)} chars, [SECURELY_MASKED])")
    print(f"  • Model: {model_name}")
    print(f"  • API Version: {api_version}")
    print(f"  • Target Dimension: {target_dim}")

    # 2. Initialize Real Gemini Embedding Provider
    print("\n[2] Initializing GeminiEmbeddingProvider:")
    provider = GeminiEmbeddingProvider(
        api_key=api_key,
        model=model_name,
        api_version=api_version,
        dimension=target_dim,
    )

    is_avail, reason = provider.check_availability()
    print(f"  • Provider availability: {is_avail}")
    print(f"  • Status reason: {reason}")
    if not is_avail:
        print("  • ERROR: Gemini provider reported unavailable.")
        return 1

    # Override service provider for this live test run
    embedding_service._provider = provider
    semantic_search_engine._provider = provider

    # Synthetic Document Content
    synthetic_doc_id = uuid.uuid4()
    synthetic_chunk_id = uuid.uuid4()
    chunk_text = (
        "Invoice TEST-LIVE-EMB-001. Acme Server Solutions Ltd. "
        "Dedicated cloud cluster maintenance and rack hosting services for Q3 2026. "
        "Total amount due: USD 1,450.00. Payment terms: Net 30."
    )
    query_text = "cloud cluster maintenance and rack hosting"

    async with async_session_maker() as session:
        try:
            # 3. Generate Real Chunk Embedding via Gemini API
            print("\n[3] Generating Real Document Chunk Embedding:")
            t0 = time.perf_counter()
            chunk_vec = await provider.embed_text(chunk_text)
            chunk_latency = (time.perf_counter() - t0) * 1000

            print(f"  • Latency: {chunk_latency:.1f}ms")
            print(f"  • Vector length: {len(chunk_vec)}")
            print(f"  • First 4 values: {[round(v, 5) for v in chunk_vec[:4]]}")

            # Validation
            assert len(chunk_vec) == target_dim, f"Expected dim {target_dim}, got {len(chunk_vec)}"
            assert all(math.isfinite(v) for v in chunk_vec), "Vector contains non-finite values!"
            norm = math.sqrt(sum(v * v for v in chunk_vec))
            print(f"  • Vector Euclidean norm: {norm:.4f} (finite & non-empty: PASS)")

            # 4. Database Persistence via EmbeddingService
            print("\n[4] Persisting Synthetic Records to Database:")
            doc = Document(
                id=synthetic_doc_id,
                original_filename="synthetic_live_test.pdf",
                stored_filename=f"s_{synthetic_doc_id}.pdf",
                file_path=f"/tmp/s_{synthetic_doc_id}.pdf",
                file_type="pdf",
                mime_type="application/pdf",
                file_size=1024,
                sha256_hash=f"hash_{synthetic_doc_id}",
                status=DocumentStatus.COMPLETED.value,
                total_chunks=1,
            )
            session.add(doc)
            await session.flush()

            chunk = DocumentChunk(
                id=synthetic_chunk_id,
                document_id=synthetic_doc_id,
                chunk_index=0,
                content=chunk_text,
                extraction_method="DIGITAL_TEXT",
                source_type=ChunkSourceType.PDF_PAGE.value,
                page_number=1,
            )
            session.add(chunk)
            await session.commit()

            # Embed and persist through embedding service
            emb_record = await embedding_service.embed_chunk(session, chunk)
            assert emb_record is not None, "Failed to persist embedding record!"
            assert emb_record.status == "completed", f"Status is {emb_record.status}"
            assert emb_record.model_name == model_name, f"Expected {model_name}, got {emb_record.model_name}"
            assert emb_record.dimension == target_dim, f"Expected {target_dim}, got {emb_record.dimension}"
            print(f"  • Persisted ChunkEmbedding id: {emb_record.id}")
            print(f"  • Stored model: {emb_record.model_name}")
            print(f"  • Stored dimension: {emb_record.dimension}")

            # 5. Generate Real Query Embedding & Run Semantic Retrieval
            print("\n[5] Executing Real Semantic Query & Cosine Similarity Match:")
            print(f"  • Natural language query: \"{query_text}\"")
            t1 = time.perf_counter()
            search_res = await semantic_search_engine.search(
                db=session,
                query=query_text,
                document_id=synthetic_doc_id,
                page=1,
                page_size=10,
            )
            search_latency = (time.perf_counter() - t1) * 1000

            print(f"  • Search execution time: {search_res.execution_time_ms}ms (total: {search_latency:.1f}ms)")
            print(f"  • Total hits: {search_res.total}")
            assert search_res.total >= 1, "Semantic search returned 0 hits for synthetic document!"

            top_item = search_res.items[0]
            print(f"  • Top hit chunk ID: {top_item.chunk_id}")
            print(f"  • Top hit similarity score: {top_item.score:.4f}")
            print(f"  • Top hit excerpt: {top_item.highlighted_snippet}")
            assert top_item.chunk_id == synthetic_chunk_id, "Retrieved chunk ID does not match expected chunk!"
            assert top_item.score > 0.50, f"Expected strong cosine similarity (>0.50), got {top_item.score}"

            print("\n[6] Semantic Retrieval Verification: PASSED")
            return 0

        except Exception as exc:
            safe_err = mask_secret(str(exc), api_key)
            print(f"\n[FAILURE CATEGORY: Live Gemini API / Search error]")
            print(f"ERROR: {safe_err}")
            return 1

        finally:
            # 6. Strict Cleanup of Synthetic Records
            print("\n[7] Cleaning Up Synthetic Test Records:")
            try:
                # Deleting document cascades to chunks and chunk_embeddings
                if doc:
                    await session.delete(doc)
                    await session.commit()
                print("  • Synthetic records cleaned up cleanly: True")
            except Exception as clean_err:
                print(f"  • Warning during cleanup: {clean_err}")


def main():
    return asyncio.run(run_live_embedding_smoke_test())


if __name__ == "__main__":
    sys.exit(main())
