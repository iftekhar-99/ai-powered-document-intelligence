# Known System Limitations and Infrastructure Constraints

**Project**: AI-Powered Financial Document Intelligence System  
**Last Updated**: November 19, 2026  

This document details known limitations, environmental constraints, infrastructure dependencies, and operational boundaries of the current system.

---

## 1. Host Infrastructure & External Dependencies

### A. Tesseract OCR Host Binary
- **Current State**: Tesseract OCR (`tesseract`) is not installed on the local evaluation host (`which tesseract` returns empty).
- **Impact**:
  - Digital PDFs, multi-page PDFs, spreadsheets (`.xlsx`, `.xls`), and `.csv` files process with 100% functionality.
  - Scanned PDF pages and bitmap image files (`.png`, `.jpg`, `.tiff`) degrade gracefully to `NEEDS_REVIEW` with an informative warning logged to `ProcessingEvent`. They do not crash the system.
  - Backend integration test `test_ocr_genuine_integration.py` is safely skipped when Tesseract is absent.
- **Resolution**:
  Install Tesseract on Debian/Ubuntu/Pop!_OS:
  ```bash
  sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-eng libtesseract-dev
  ```
  Once installed, the system automatically detects the binary and activates genuine OCR without requiring code changes.

### B. Database Engines: SQLite vs. PostgreSQL + pgvector
- **Current State**: The system automatically falls back to SQLite (`sqlite+aiosqlite:///./doc_intel.db`) when a PostgreSQL instance is not reachable at `localhost:5432`.
- **Impact**:
  - SQLite uses a JSON column for vector storage (`chunk_embeddings.embedding`) and computes cosine similarity in-memory within Python.
  - SQLite is single-file; concurrent writes under heavy parallel test execution require careful connection locking.
- **Production Recommendation**:
  For high-concurrency production deployments, run the provided Docker Compose stack (`docker compose up db redis`) to enable PostgreSQL 16 with native `pgvector` indexing (`HNSW` / `IVFFlat`).

### C. Background Task Dispatch: Celery vs. Inline BackgroundTasks
- **Current State**: When Redis is not reachable at `localhost:6379`, the system runs in `inline` mode using FastAPI `BackgroundTasks` / `asyncio.create_task`.
- **Impact**:
  - Extraction and embedding tasks execute within the local FastAPI process rather than a distributed Celery queue.
- **Production Recommendation**:
  Set `PROCESSING_MODE=celery` and ensure Redis is active in production.

---

## 2. API Quotas & Provider Rate Limits

### A. Gemini Developer API Rate Limits
- **Extraction Model**: `gemini-flash-lite-latest` on `v1beta`.
- **Embedding Model**: `gemini-embedding-2` on `v1beta` (768 dimensions).
- **Constraints**:
  - The Gemini Developer API enforces requests-per-minute (RPM) and tokens-per-minute (TPM) limits on free/developer tier keys.
  - Generating embeddings for documents with thousands of chunks in rapid succession may encounter HTTP 429 rate limit errors.
- **Mitigations Implemented**:
  - Decoupled ingestion: Document processing completes and stores text chunks even if embedding generation fails or encounters API rate limits.
  - Backfill capability: Chunks that fail embedding remain in `failed` status and can be retried via `POST /api/v1/search/embeddings/backfill`.
  - Batching: `batchEmbedContents` processes chunks in batches of 50 to minimize HTTP request overhead.

### B. Live AI Model Evaluation Sample Size & Benchmark Scope
- **Current State**: Live AI invoice extraction has been validated via the live Gemini API on **1 representative digital document** (`01_digital_single_page.pdf`) in the benchmark suite, plus **1 synthetic invoice** (`TEST-LIVE-001`) in Task 4D.1.
- **Limitation**: Batch live Gemini extraction across all 15 benchmark documents (13 expected invoices) was intentionally not executed during release benchmarking to prevent developer API quota exhaustion, avoid cloud costs, and respect test execution speed.
- **Methodological Impact**: The 13-invoice, 104-field evaluation represents a **controlled synthetic baseline using ground-truth fixtures** to verify schema normalization, mathematical validation, and database persistence. Invoices 2 through 13 have not been evaluated via live Gemini API calls and must be cited as **UNVERIFIED IN LIVE AI MODE**. Live AI extraction claims strictly apply to $N=1$ tested invoices.

---

## 3. Extraction & Data Modeling Boundaries

### A. Ambiguous Calendar Dates
- **Behavior**: Date formats with ambiguous day/month order (e.g., `03/04/05` or `01/02/03`) or non-calendar quarters (`Q3 2026`) are intentionally parsed to `NULL` for `Invoice.invoice_date`.
- **Rationale**: To prevent financial systems from recording incorrect dates (e.g. interpreting March 4 as April 3), the system avoids guessing. The raw string is preserved in field evidence, and the invoice is flagged with `needs_manual_review = True`.

### B. Complex Non-Tabular Spreadsheets
- **Behavior**: The spreadsheet processor handles standard tabular worksheets, multi-sheet workbooks, and CSV files cleanly.
- **Limitation**: Freeform spreadsheets with arbitrary merged cells, nested sub-tables across multiple directions, or embedded macros may require custom sheet layouts or manual correction in the review dashboard.

### C. Multi-Currency Transactions
- **Behavior**: Invoices are modeled with a single primary currency code.
- **Limitation**: Documents containing multi-currency split billing (e.g. base subtotal in EUR, VAT in GBP, final balance in USD) extract the primary total currency; multi-currency conversions require manual review.

---

## 4. Security & Access Control Boundaries

### A. Authentication & Role-Based Access Control (RBAC)
- **Current State**: User authentication (e.g., JWT, OAuth2) and role-based permissions (Viewer vs. Reviewer vs. Admin) are not implemented in this tier.
- **Impact**: All endpoints in `/api/v1/` are publicly accessible on the local network or configured host.
- **Recommendation**: Integrate an identity provider (e.g. Auth0, Keycloak, or FastAPI OAuth2) before exposing the API to public or multi-tenant production environments.

### B. Cross-Origin Resource Sharing (CORS)
- **Current State**: Permissive CORS (`allow_origins=["*"]`) is enabled for seamless local development between Vite (`localhost:5173`) and FastAPI (`localhost:8000`).
- **Recommendation**: Restrict `allow_origins` to explicit frontend production domains in `backend/app/core/config.py`.

### C. File Upload Size Limits
- **Configured Limit**: Maximum upload size is configured at **100 MB** (`MAX_UPLOAD_SIZE_MB = 100` in `backend/app/core/config.py`, equating to $104,857,600$ bytes enforced via chunked streaming in `storage.py`).
- **Correction Note**: Any earlier documentation or evaluation report draft referencing a 50 MB limit was inaccurate; the actual system enforcement has always been 100 MB.

---

## 5. Scope Boundaries Against Assignment Requirements

| Requirement | Current Status | Notes |
| :--- | :---: | :--- |
| **Multi-Format Ingestion** | Completed | PDF, XLSX, XLS, CSV, images supported (100 MB limit) |
| **1,000-Page PDF Processing** | Completed | 14,084.5 pages/sec streaming throughput verified |
| **OCR Text Extraction** | Implemented | Verified on synthetic/fallback; host binary optional |
| **Gemini AI Extraction** | Completed | Live API verified on representative invoice ($N=1$); 100% accuracy |
| **Financial Validation** | Completed | Arithmetic, required fields, and duplicate checks verified |
| **Manual Review & Audit** | Completed | Mandatory justification, before/after audit records |
| **Hybrid Search** | Completed | Keyword + Semantic (`gemini-embedding-2`) + RRF |
| **Frontend Dashboard** | Completed | 15 Vitest tests passing, production build passing |
| **Automated Evaluation** | Completed | `backend/scripts/run_evaluation.py` (live test separated from 13-invoice fixture baseline) |
