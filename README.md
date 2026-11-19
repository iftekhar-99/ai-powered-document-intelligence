# AI-Powered Financial Document Intelligence System

A modular monolithic application designed to ingest financial documents (PDFs up to ~1,000 pages, scans, multi-sheet workbooks, CSVs), extract structured invoice data using Google Gemini with strict schema enforcement, validate mathematical and accounting consistency deterministically, and provide hybrid semantic search.

---

## 1. System Overview

### Core Capabilities
- **Multi-Format Ingestion**: Native streaming ingestion for digital PDFs, spreadsheets (`.xlsx`, `.xls`), and CSVs, with fallback handling for scanned images (`.png`, `.jpg`, `.tiff`).
- **High-Volume Document Streaming**: Page-by-page generator pipeline capable of streaming 1,000-page PDF ledgers at **14,084.5 pages/second** with $O(1)$ memory consumption.
- **Configurable LLM Extraction**: Structured extraction powered by Google Gemini (`gemini-flash-lite-latest`, `v1beta`) with Pydantic v2 JSON schema validation, temperature 0.0, and chunk citation verification.
- **Deterministic Financial Validation**: Strict arithmetic validation ($\text{subtotal} + \text{tax} = \text{total}$ with $\pm \$0.01$ rounding tolerance), mandatory field checks, and cross-document duplicate invoice detection.
- **Human-in-the-Loop Review & Audit Trail**: React review dashboard with field-level chunk evidence inspection, mandatory justification for manual edits, and immutable before/after audit logs.
- **Hybrid Search Engine**: Combines full-text/tokenized search with dense vector embeddings (`gemini-embedding-2`, 768 dimensions) fused via Reciprocal Rank Fusion (RRF).

---

## 2. Technology Stack & Architecture

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Lucide Icons |
| **Backend API** | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Celery |
| **Active Local DB** | SQLite 3 via `aiosqlite` with foreign key PRAGMA enforcement & in-memory cosine similarity |
| **Production DB Target** | PostgreSQL 16 with native `pgvector` extension (`HNSW`/`IVFFlat`) — Dockerized |
| **Active Task Runner**| Inline execution via FastAPI `BackgroundTasks` (`PROCESSING_MODE=inline`) |
| **Production Queue** | Redis 7 + Celery distributed background workers — Dockerized |
| **Document Parsers** | PyMuPDF (`fitz`), OpenPyXL, xlrd, Python built-in `csv`, Pillow |
| **AI LLM Extraction**| Google Gemini Developer API (`gemini-flash-lite-latest`, `v1beta`) via `google-genai` SDK |
| **Vector Embeddings** | Google Gemini Embeddings API (`gemini-embedding-2`, 768-dim) |
| **Test Suites** | Pytest, Pytest-Asyncio, Vitest, React Testing Library |

For complete architectural diagrams and entity relationship models, see [docs/architecture.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/architecture.md).

---

## 3. Environment Modes: Local Development vs. Production Target

The system cleanly distinguishes between the verified **Local Development Environment** and the containerized **Production Target**:

```
+-----------------------------------------------------------------------------------+
| LOCAL DEVELOPMENT MODE (Active & Verified)                                         |
| • Database: SQLite 3 (./doc_intel.db) via aiosqlite                               |
| • Background Processing: Inline FastAPI BackgroundTasks (PROCESSING_MODE=inline)  |
| • Vector Search: In-memory Cosine Similarity across JSON-persisted vector arrays    |
| • OCR: Graceful degradation (scanned files mark NEEDS_REVIEW if Tesseract absent)  |
+-----------------------------------------------------------------------------------+
                                         │  (Deploy via Docker Compose)
                                         ▼
+-----------------------------------------------------------------------------------+
| PRODUCTION TARGET (Configured in docker-compose.yml)                              |
| • Database: PostgreSQL 16 + pgvector (native vector indexes)                      |
| • Background Processing: Redis 7 + Celery distributed background task workers     |
| • Vector Search: Database-native pgvector cosine distance (<->)                   |
| • OCR: Containerized Tesseract OCR engine with tesseract-ocr-eng packages         |
+-----------------------------------------------------------------------------------+
```

> [!NOTE]
> Local development mode is tested, verified, and active. Production targets (PostgreSQL, Redis, Celery) are configured in `docker-compose.yml` but have not been executed on this host. Do not claim production services or host OCR are active in local mode.

---

## 4. Quickstart & Installation

### Prerequisites
- **Python**: 3.12+ (tested on Python 3.12.3)
- **Node.js**: 18+ (tested on Node 20 / npm 10)
- **Git**

---

### Step 1: Environment Configuration
Copy the documented environment template:
```bash
cp .env.example .env
```

#### Safe Gemini API Key Configuration
To enable live AI extraction and semantic embeddings, add your Gemini API key to `.env`:
```ini
GEMINI_API_KEY="your-gemini-api-key-here"
GEMINI_MODEL="gemini-flash-lite-latest"
GOOGLE_GENAI_API_VERSION="v1beta"
GEMINI_EMBEDDING_MODEL="gemini-embedding-2"
EMBEDDING_DIMENSION=768
```
- **Security Guarantee**: `.env` is listed in `.gitignore` and is never committed.
- Keys are loaded strictly into memory by `Pydantic BaseSettings`.
- All logging streams pass through `mask_secret()` to redact credentials from logs and API errors.

---

### Step 2: Backend Setup (FastAPI)

```bash
cd backend

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI server in local development mode
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- **Backend API**: `http://localhost:8000`
- **Interactive OpenAPI Documentation**: `http://localhost:8000/api/v1/docs`
- **System Capabilities**: `http://localhost:8000/api/v1/capabilities`
- **Health Check**: `http://localhost:8000/api/v1/health`

---

### Step 3: Frontend Setup (React + Vite)

In a new terminal window:
```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```
- **Frontend Dashboard**: `http://localhost:5173`

---

## 5. How Document Processing & AI Extraction Work

1. **Ingestion & Storage**:
   - Files uploaded to `POST /api/v1/documents/upload` are validated against strictly whitelisted extensions and verified via 512-byte magic signatures.
   - Files are streamed in 64 KB chunks while incrementally computing SHA-256 hashes. Maximum file size is strictly capped at **100 MB** (`MAX_UPLOAD_SIZE_MB = 100`).
2. **Chunk Extraction**:
   - **Digital PDFs**: Extracted page-by-page using PyMuPDF generators.
   - **Spreadsheets**: Sheet-by-sheet extraction via OpenPyXL and Python csv in 50-row chunks with column headers preserved.
   - **Scanned Images**: Checked for host Tesseract OCR. If unavailable, logs an informative event and safely marks document `NEEDS_REVIEW` without crashing.
3. **Context Preparation**:
   - `ContextPreparationService` segments document chunks into bounded `ExtractionContext` objects (max 30,000 characters) using 8 normalized detection weights (invoice keywords, date formats, total keywords).
4. **Gemini Extraction**:
   - `GeminiProvider` submits context to `gemini-flash-lite-latest` (`v1beta`) with temperature 0.0.
   - Results are strictly validated against Pydantic v2 schema `DocumentExtractionResponse`.
   - `EvidenceValidator` verifies that citations match raw chunk text before persisting.
5. **Validation & Auditing**:
   - Deterministic accounting rules verify arithmetic ($\text{subtotal} + \text{tax} = \text{total}$) and flag missing numbers or cross-document duplicates.
   - Manual corrections require structured business justification, write immutable audit records, and trigger automatic revalidation.

---

## 6. Verification, Testing & Evaluation

### 1. Backend Pytest Suite
```bash
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests
```
- **Result**: **173 passed, 1 skipped** (genuine OCR skipped due to missing host binary).

### 2. Frontend Vitest Suite
```bash
npm --prefix frontend test -- --run
```
- **Result**: **15 passed** across 3 test suites (`App.test.tsx`, `InvoiceReview.test.tsx`, `Search.test.tsx`).

### 3. Frontend Production Build
```bash
npm --prefix frontend run build
```
- **Result**: TypeScript compilation (`tsc`) and Vite build passed with **0 errors**.

### 4. End-to-End Evaluation Benchmark
```bash
# Generate synthetic benchmark suite (15 documents + ground-truth JSONs)
backend/.venv/bin/python backend/scripts/generate_evaluation_dataset.py

# Execute full evaluation harness
backend/.venv/bin/python backend/scripts/run_evaluation.py
```
- **Benchmark Results**:
  - **Live Gemini Extraction**: **100.0% accuracy** on representative test document ($N=1$ invoice, 8 fields, 2 line items, 9,493.66 ms latency).
  - **Controlled Synthetic Baseline**: **100.0% accuracy** across 13 invoices / 104 fields on ground-truth fixtures.
  - **1,000-Page PDF Throughput**: **14,084.5 pages/second** (0.071s processing time).
  - **Financial Validation**: Successfully detected arithmetic mismatches, missing fields, and duplicate invoices.

For the full audited evaluation report, see [docs/evaluation_report.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/evaluation_report.md) and machine-readable data in [docs/evaluation_results.json](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/evaluation_results.json).

---

## 7. Project Documentation Index

- [docs/architecture.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/architecture.md): Complete architecture diagram, data lifecycles, and database entity relationships.
- [docs/demo_walkthrough.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/demo_walkthrough.md): Step-by-step 5–7 minute demonstration script with exact synthetic test filenames and click actions.
- [docs/ai_development_disclosure.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/ai_development_disclosure.md): Factual disclosure of development-time AI tools and runtime Gemini architecture.
- [docs/evaluation_report.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/evaluation_report.md): Audited benchmark report separating live AI extraction from fixture baselines.
- [docs/known_limitations.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/known_limitations.md): Documented infrastructure constraints, OCR absence, and local SQLite behavior.

---

## 8. Known Limitations & Constraints Summary

1. **Host OCR Absence**: Tesseract OCR is not installed on the local evaluation host (`which tesseract` is empty). Bitmap images (`.png`, `.jpg`, `.tiff`) degrade gracefully to `NEEDS_REVIEW` with explicit warnings. To install on Ubuntu/Debian:
   ```bash
   sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-eng
   ```
2. **Single Live AI Evaluation Sample**: Live Gemini extraction was verified on representative synthetic test documents ($N=1$ in benchmark, $N=1$ in Task 4D.1). Batch live AI extraction was omitted for invoices 2–13 to conserve API quota.
3. **Local Dev SQLite vs. Production pgvector**: SQLite computes cosine similarity in-memory; high-throughput production requires PostgreSQL 16 with native `pgvector` indexing (`docker compose up db redis`).
4. **No Authentication / RBAC**: REST endpoints and the UI do not enforce multi-user permissions in this development tier.
