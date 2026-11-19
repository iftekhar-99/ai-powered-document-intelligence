# Demonstration Script & Practical Walkthrough Guide

**Project**: AI-Powered Financial Document Intelligence System  
**Estimated Duration**: 5–7 minutes  
**Target Audience**: Technical Evaluators, Hiring Managers, AI Systems Architects  
**Required Preconditions**: Local virtual environment activated, frontend dependencies installed, `.env` file present.  

---

## Demonstration Overview

This practical walkthrough provides a structured, step-by-step demonstration script designed to showcase the complete end-to-end capabilities of the system.

### Test Documents Used
All demonstration documents are pre-generated synthetic files located in `data/evaluation/documents/`:
1. `data/evaluation/documents/01_digital_single_page.pdf`: Clean 1-page digital PDF invoice (\$1,375.00, 2 line items).
2. `data/evaluation/documents/04_arithmetic_error_invoice.pdf`: Invoice with an arithmetic error (\$490.00 printed total vs. \$440.00 expected).
3. `data/evaluation/documents/08_multisheet_invoices.xlsx`: Multi-sheet spreadsheet with 2 invoice worksheets.

> [!NOTE]
> **Host OCR Limitation**: Tesseract OCR is not installed on this local host (`which tesseract` returns empty). If scanned bitmaps (`.png`, `.jpg`, `.tiff`) are uploaded, they gracefully degrade to `NEEDS_REVIEW` with an informative warning rather than crashing. Explain this environmental constraint honestly to the reviewer.

---

## Demonstration Script (Step-by-Step)

### Step 1: Starting the System (0:00 – 0:45)

#### What to Run
Open two terminal windows from the project root:

**Terminal 1 — Backend API Server:**
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend Application:**
```bash
cd frontend
npm run dev
```

#### What Should Happen
- Backend starts on `http://localhost:8000`. You will see the log:
  `PostgreSQL at localhost:5432 is unreachable. Falling back to SQLite local database (sqlite+aiosqlite:///./doc_intel.db)`
- Frontend starts on `http://localhost:5173`.
- Open `http://localhost:5173` in your web browser.

#### What to Explain to the Reviewer
> *"The backend is built with FastAPI and SQLAlchemy 2.0 async. Notice that in local development without Docker running, the system automatically detects that PostgreSQL is offline and falls back gracefully to local SQLite. Ingestion tasks run inline via FastAPI BackgroundTasks, making local evaluation zero-configuration."*

---

### Step 2: Exploring the Dashboard & Architecture (0:45 – 1:30)

#### What to Click
1. Look at the top navigation bar and sidebar on `http://localhost:5173`.
2. Observe the KPI cards: **Total Documents**, **Invoices Extracted**, **Pending Issues**, and **Duplicate Invoices**.
3. Point out the navigation tabs: **Dashboard**, **Documents**, **Invoices**, **Validation & Issues**, and **Search**.

#### What Should Happen
The dashboard displays current metrics and system health indicators. If previous test documents were loaded, they are summarized in the tables.

#### What to Explain to the Reviewer
> *"The frontend is a single-page React 18 application built with TypeScript, Vite, and Tailwind CSS. The dashboard provides operational visibility into financial document processing, extraction confidence, and unresolved validation anomalies."*

---

### Step 3: Uploading a Digital PDF Invoice (1:30 – 2:30)

#### What to Click
1. In the navigation bar, click **Documents** (or stay on the Dashboard upload dropzone).
2. Click **Browse Files** or drag and drop:
   `data/evaluation/documents/01_digital_single_page.pdf`
3. Click **Upload & Process**.

#### What Should Happen
- The file is validated for allowed extension (`.pdf`) and binary signature.
- Streaming upload writes the file in 64 KB chunks, computes SHA-256 hash, and caps size at 100 MB.
- PyMuPDF extracts text chunks page-by-page.
- The document status transitions from `UPLOADED` → `PROCESSING` → `COMPLETED`.
- A success toast notification appears: `"Document processed successfully"`.

#### What to Explain to the Reviewer
> *"Our ingestion pipeline streams files directly to disk while validating magic byte signatures and computing SHA-256 hashes to catch exact duplicates. Digital text extraction uses PyMuPDF generators, achieving over 14,000 pages per second streaming throughput without memory leaks."*

---

### Step 4: Extracting Invoice Data & Inspecting Evidence (2:30 – 3:30)

#### What to Click
1. On the document row for `01_digital_single_page.pdf`, click **Extract Invoices** (or click **Inspect**).
2. Navigate to the **Invoices** tab.
3. Click on the extracted invoice row (`INV-2026-001`).

#### What Should Happen
- An **Invoice Detail Modal** opens.
- **Header Fields**:
  - `Invoice Number`: `INV-2026-001`
  - `Invoice Date`: `2026-11-01`
  - `Supplier`: `Nexus Global Solutions Inc.`
  - `Customer`: `Apex Innovations LLC`
  - `Currency`: `USD`
  - `Subtotal`: `1,250.00`
  - `Tax`: `125.00`
  - `Total`: `1,375.00`
- **Line Items Table**:
  1. *Cloud Architecture Consulting* — Qty: 10, Unit: \$100.00, Total: \$1,000.00
  2. *Infrastructure Maintenance* — Qty: 1, Unit: \$250.00, Total: \$250.00
- Click on any field (e.g. `Supplier` or `Total`) to view the **Supporting Chunk Evidence** panel showing the verbatim quotation from the PDF.

#### What to Explain to the Reviewer
> *"The extraction orchestrator leverages Google Gemini (`gemini-flash-lite-latest`) with temperature 0.0 and Pydantic v2 structured schemas. Every extracted field is grounded: our EvidenceValidator validates citations against the raw document chunk before database persistence."*

---

### Step 5: Demonstrating Financial Validation & Arithmetic Errors (3:30 – 4:45)

#### What to Click
1. Go to **Documents** and upload the intentional arithmetic error file:
   `data/evaluation/documents/04_arithmetic_error_invoice.pdf`
2. Wait for processing to complete, then click **Extract Invoices**.
3. Navigate to **Validation & Issues** in the sidebar.

#### What Should Happen
- An error badge appears: `subtotal_tax_total_mismatch` (Severity: ERROR).
- The issue card states:
  - **Field**: `total`
  - **Observed Value**: `490.00`
  - **Expected Value**: `440.00` (Subtotal \$400.00 + Tax \$40.00)
  - **Description**: *"Calculated total (440.00) does not match invoice total (490.00)"*

#### What to Explain to the Reviewer
> *"Our financial validation engine is completely deterministic. It executes strict accounting rules, verifying that subtotal plus tax equals total within a \$0.01 tolerance. Notice how it flagged this intentional discrepancy without needing an LLM to guess."*

---

### Step 6: Manual Correction, Justification, & Revalidation (4:45 – 5:45)

#### What to Click
1. From the issue card or Invoices table, open the invoice detail for `INV-2026-004`.
2. Click **Edit Invoice** or click the pencil icon next to the **Total** field.
3. Change the Total value from `490.00` to `440.00`.
4. In the mandatory **Justification / Reason** box, enter:
   `"Corrected printed total of $490.00 to match subtotal + tax ($400.00 + $40.00 = $440.00)"`
5. Click **Save Changes**.

#### What Should Happen
- The invoice updates immediately.
- The invoice displays an `is_manually_corrected = True` badge.
- An immutable entry is written to `invoice_correction_audits`.
- The system automatically triggers revalidation.
- The arithmetic discrepancy in **Validation & Issues** resolves automatically and transitions to `Resolved`.
- Click the **Audit History** tab to inspect the before-and-after audit log showing timestamp, changed fields, previous value (`490.00`), new value (`440.00`), and your justification.

#### What to Explain to the Reviewer
> *"In enterprise financial systems, human review is essential. Our workflow enforces that any manual correction requires a mandatory business justification. The edit is recorded in an immutable audit log, and the validation engine automatically revalidates the document to clear the resolved anomaly."*

---

### Step 7: Hybrid Search & Retrieval (5:45 – 6:30)

#### What to Click
1. Click **Search** in the sidebar.
2. In the search box, enter query: `"Cloud consulting"`
3. Toggle between **Keyword**, **Semantic**, and **Hybrid** search modes.
4. Click **Search**.

#### What Should Happen
- In **Hybrid** mode, the system retrieves chunk matches ranked by Reciprocal Rank Fusion (RRF).
- The top hit displays:
  - Document link: `01_digital_single_page.pdf`
  - Extracted invoice: `INV-2026-001`
  - Page number: `1`
  - Highlighted text snippet with matched query terms
- Point out the latency counter (typically 50–70 ms for keyword, ~600 ms for live Gemini semantic embeddings).

#### What to Explain to the Reviewer
> *"Our hybrid search engine combines PostgreSQL full-text/SQLite tokenized search with vector embeddings generated via `gemini-embedding-2` (768 dimensions). Results are fused using Reciprocal Rank Fusion, ensuring users find invoices by exact vendor names, invoice numbers, or natural language semantic intent."*

---

### Step 8: Concluding with Evaluation & Limitations (6:30 – 7:00)

#### What to Show
1. Open the documentation in your code editor or browser:
   - [docs/evaluation_report.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/evaluation_report.md)
   - [docs/known_limitations.md](file:///home/ima19/Documents/AI-Powered%20Document%20Intelligence%20System/docs/known_limitations.md)
2. Highlight:
   - The **173 passed backend tests** and **15 passed frontend tests**.
   - The verified **100.0% accuracy** on live Gemini extraction ($N=1$).
   - The **14,084.5 pages/sec** streaming throughput on the 1,000-page benchmark.
   - The transparent documentation of environmental limitations (Tesseract host absence, local SQLite fallback).

#### What to Explain to the Reviewer
> *"All capabilities presented today are backed by automated regression tests and a reproducible benchmarking harness. We have audited our methodology to strictly separate live AI trials from synthetic baseline fixtures, ensuring that all reported metrics are honest, credible, and reproducible."*
