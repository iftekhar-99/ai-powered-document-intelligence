# AI Development Disclosure & Runtime LLM Architecture

**Project**: AI-Powered Financial Document Intelligence System  
**Document Version**: 1.0  
**Date**: November 19, 2026  

---

## 1. AI Coding Assistance During Development

In accordance with responsible engineering standards, this document discloses how AI coding assistance was utilized during the development of this project, how AI is utilized at runtime, and where deterministic software engineering practices were applied.

### 1.1 Development-Time AI Usage
An agentic AI coding assistant (Antigravity by Google DeepMind) was used collaboratively throughout the implementation phases to accelerate system development:
- **Architecture & Scaffolding**: Initial repository structure, Docker Compose definitions, FastAPI endpoint boilerplate, and Vite frontend scaffolding.
- **Schema Authoring**: Pydantic v2 data models (`DocumentExtractionResponse`, `InvoiceExtraction`, `InvoiceLineItemExtraction`, `SourceEvidence`) and TypeScript interfaces.
- **Service Implementation**: Writing parsers, orchestrators, adapters (`GeminiProvider`), search algorithms (Reciprocal Rank Fusion), and database models.
- **Test Generation**: Generating comprehensive Pytest test suites (174 backend tests) and Vitest component specs (15 frontend tests).
- **Synthetic Benchmark Creation**: Scripting the 15-document evaluation suite and ground-truth JSON files.

### 1.2 Human Engineering & Rigorous Verification
All AI-generated code underwent continuous testing, review, and empirical verification:
- **Regression Testing**: Every development task required passing the complete backend test suite and frontend unit/build suites.
- **Static Analysis & Schema Validation**: Strict Pydantic v2 schemas and TypeScript compiler verification (`tsc && vite build`) enforced compile-time type safety.
- **Methodological Auditing (Task 5A.1)**: When the evaluation harness initially reported an ambiguous 100% accuracy claim across 13 invoices, a rigorous pre-release audit traced the discrepancy, identified that 12 invoices were evaluated against ground truth directly rather than through live API calls, and corrected the documentation to strictly separate live AI metrics from fixture baselines.

---

## 2. Runtime AI Capabilities: Google Gemini Integration

At runtime, the application leverages the **Google Gemini Developer API** for two core capabilities:

### 2.1 Structured Invoice Extraction
- **Model**: `gemini-flash-lite-latest`
- **API Version**: `v1beta` (Interactions API)
- **SDK**: Official `google-genai` Python library
- **Operational Parameters**:
  - `temperature: 0.0` (zero sampling entropy to enforce strict determinism)
  - `response_mime_type: "application/json"`
  - `max_output_tokens: 8000`
  - `timeout: 120` seconds
- **Role**: Converting unstructured natural language text chunks from invoices, receipts, and spreadsheets into structured JSON conforming to `DocumentExtractionResponse`.

### 2.2 Semantic Vector Embeddings
- **Model**: `gemini-embedding-2`
- **API Version**: `v1beta`
- **Output Dimensionality**: 768 dimensions
- **Batching**: 50 chunks per batch request via `batchEmbedContents`
- **Role**: Computing dense semantic representations of document chunks and natural language search queries to power vector similarity matching.

---

## 3. Deterministic Software Engineering vs. AI Roles

A foundational architectural decision in this system is that **AI is never trusted to perform mathematical calculations, accounting reconciliations, or critical integrity checks**. The division of responsibility is strictly partitioned:

| System Component | Execution Paradigm | Method / Technology | Why This Approach Was Chosen |
| :--- | :--- | :--- | :--- |
| **Document Streaming** | **Deterministic** | PyMuPDF page-by-page generator | Guaranteed $O(1)$ memory, 14,000+ pages/sec throughput. |
| **Tabular Parsing** | **Deterministic** | OpenPyXL, xlrd, Python csv | Accurate cell grid coordinates, preserved column headers. |
| **Boundary Segmentation** | **Deterministic** | Weighted heuristic scoring (8 weights) | Predictable windowing, prevents token overflow. |
| **Unstructured Extraction** | **Generative AI** | Gemini `gemini-flash-lite-latest` | High flexibility across varied visual and textual invoice layouts. |
| **Citation Verification** | **Deterministic** | String substring & chunk ID validation | Rejects fabricated citations and ungrounded hallucinations. |
| **Schema Validation** | **Deterministic** | Pydantic v2 strict models | Guarantees type safety and rejects malformed JSON. |
| **Financial Validation** | **Deterministic** | Python `Decimal` arithmetic rules | Absolute mathematical precision ($\pm \$0.01$). LLMs are prone to arithmetic errors. |
| **Duplicate Detection** | **Deterministic** | Relational SQL queries on hashes & keys | Prevents duplicate vendor disbursements. |
| **Manual Correction Audit** | **Deterministic** | Immutable relational audit log | Mandates business justification and compliance accountability. |
| **Hybrid Search Ranking** | **Hybrid (AI + Deterministic)**| Cosine similarity + SQL LIKE + RRF | Balances exact keyword matching with semantic intent. |

---

## 4. How Extraction Guardrails Constrain LLM Behavior

To mitigate common LLM risks (hallucinations, fabricated numbers, format drift), four layers of runtime guardrails are enforced:

1. **Strict Pydantic v2 Schema Enforcement**:
   Gemini is constrained to output structured JSON matching the Pydantic definition. Malformed payloads or missing required schema properties fail validation immediately.
2. **Source Evidence Citations**:
   Every extracted field (`ExtractedField`) requires a `SourceEvidence` citation containing a valid `source_chunk_id`. The `EvidenceValidator` verifies that:
   - The cited chunk ID actually exists in the source document.
   - If quotation text is provided, the substring exists within the raw chunk content.
   - Fields failing evidence verification are flagged and recorded as unsupported.
3. **Conservative Ambiguity Handling**:
   The extraction prompt builder explicitly instructs the model:
   > *"If an invoice number or invoice date is missing, ambiguous, or cannot be confirmed from text, return `null`. Never guess or fabricate financial values."*
   In evaluation, ambiguous dates such as `03/04/05` and pro-forma quotes lacking invoice numbers were successfully extracted as `None/NULL`.
4. **Mandatory Human-in-the-Loop Review**:
   Extracted data is never auto-committed as final without human visibility. The React dashboard displays extracted fields alongside raw chunk quotations, visual validation badges, and mandatory justification logging for any corrections.

---

## 5. Known Limitations & AI-Specific Risks

1. **Single Live Trial Benchmark**:
   While the live Gemini API was verified with 100% accuracy on representative synthetic test documents ($N=1$ in benchmark, $N=1$ in Task 4D.1), batch live extraction across all 15 benchmark documents was not run during the benchmark harness to avoid cloud costs and rate limits. Performance on untried layouts should be verified through pilot testing.
2. **API Latency & Rate Limits**:
   The Gemini Developer API introduces network latency (typically 5–9 seconds per document extraction) and is subject to requests-per-minute (RPM) quotas. In production, requests should be decoupled using Celery and Redis with backoff retries.
3. **Complex Freeform Spreadsheets**:
   While standard tabular spreadsheets and CSV files parse cleanly, freeform spreadsheets with arbitrary merged cells, nested subtables, or multi-directional layouts may require manual correction in the review dashboard.
4. **Date Ambiguity**:
   International date conventions (`DD/MM/YYYY` vs. `MM/DD/YYYY`) remain challenging without locale metadata. The system intentionally resolves ambiguous dates to `NULL` to prevent erroneous financial postings.
