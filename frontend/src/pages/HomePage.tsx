import React, { useEffect, useState, useCallback } from 'react';
import { Sidebar } from '../components/Sidebar';
import { HealthCard } from '../components/HealthCard';
import { DocumentUploadZone } from '../components/DocumentUploadZone';
import { DocumentList } from '../components/DocumentList';
import { DocumentDetailModal } from '../components/DocumentDetailModal';
import { ExtractionRunModal } from '../components/ExtractionRunModal';
import { InvoicesPage } from './InvoicesPage';
import { ProcessingHistoryPage } from './ProcessingHistoryPage';
import { SearchPage } from './SearchPage';
import {
  fetchDocuments,
  fetchHealth,
  deleteDocument,
  triggerProcessing,
  fetchDashboardMetrics,
} from '../services/api';
import {
  DashboardMetrics,
  DocumentItem,
  DocumentListResponse,
  HealthResponse,
  UploadBatchResponse,
} from '../types';
import {
  FileText,
  Layers,
  Search,
  ShieldCheck,
  Cpu,
  CheckCircle,
  Receipt,
  AlertTriangle,
  Edit3,
  ArrowRight,
} from 'lucide-react';

export const HomePage: React.FC = () => {
  const [activeView, setActiveView] = useState<string>('dashboard');

  // System Health state
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  // Dashboard Metrics
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);

  // Document list state
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [totalDocs, setTotalDocs] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(10);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [docsLoading, setDocsLoading] = useState<boolean>(false);
  const [filters, setFilters] = useState<{
    status?: string;
    fileType?: string;
    search?: string;
  }>({});

  // Document details modal state
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);

  // AI Extraction modal state
  const [extractingDoc, setExtractingDoc] = useState<DocumentItem | null>(null);

  const checkHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setHealthError(err.message);
      } else {
        setHealthError('Unknown error connecting to API');
      }
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const loadMetrics = useCallback(async () => {
    try {
      const data = await fetchDashboardMetrics();
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load metrics:', err);
    }
  }, []);

  const loadDocuments = useCallback(async () => {
    setDocsLoading(true);
    try {
      const response: DocumentListResponse = await fetchDocuments({
        page,
        page_size: pageSize,
        status: filters.status,
        file_type: filters.fileType,
        search: filters.search,
      });
      setDocuments(response.items);
      setTotalDocs(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setDocsLoading(false);
    }
  }, [page, pageSize, filters]);

  useEffect(() => {
    checkHealth();
    loadMetrics();
  }, [checkHealth, loadMetrics]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const handleUploadSuccess = (_batch: UploadBatchResponse) => {
    loadDocuments();
    loadMetrics();
  };

  const handleDeleteDocument = async (id: string) => {
    await deleteDocument(id);
    loadDocuments();
    loadMetrics();
  };

  const handleTriggerProcess = async (id: string) => {
    try {
      await triggerProcessing(id);
      await loadDocuments();
      await loadMetrics();
    } catch (err) {
      console.error('Failed to trigger processing:', err);
    }
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
  };

  const handleFilterChange = (newFilters: {
    status?: string;
    fileType?: string;
    search?: string;
  }) => {
    setPage(1);
    setFilters(newFilters);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Persistent Left Sidebar Navigation */}
      <Sidebar
        activeView={activeView}
        onViewChange={(view) => setActiveView(view)}
        reviewCount={metrics?.needs_review_invoices || 0}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Navigation Header */}
        <header className="bg-white border-b border-slate-200 sticky top-0 z-20 shadow-xs">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="bg-sky-600 p-2 rounded-lg text-white shadow-xs">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-base font-bold text-slate-900 tracking-tight">
                  DocIntel AI
                </h1>
                <p className="text-xs text-slate-500">
                  Financial Document Intelligence System
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
                <span className="w-1.5 h-1.5 mr-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                Environment Active
              </span>
            </div>
          </div>
        </header>

        {/* View Routing */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full space-y-8">
          {/* VIEW: SEARCH */}
          {activeView === 'search' && (
            <SearchPage
              onViewInvoice={(_invoiceId) => {
                setActiveView('invoices');
              }}
              onViewDocument={(_documentId) => {
                setActiveView('documents');
              }}
            />
          )}

          {/* VIEW: INVOICES (ALL) */}
          {activeView === 'invoices' && (
            <InvoicesPage initialNeedsReviewOnly={false} onReviewCountChange={loadMetrics} />
          )}

          {/* VIEW: NEEDS REVIEW */}
          {activeView === 'review' && (
            <InvoicesPage initialNeedsReviewOnly={true} onReviewCountChange={loadMetrics} />
          )}

          {/* VIEW: PROCESSING HISTORY */}
          {activeView === 'history' && <ProcessingHistoryPage />}

          {/* VIEW: SYSTEM HEALTH */}
          {activeView === 'health' && (
            <div className="space-y-6">
              <div className="border-b border-slate-200 pb-4">
                <h2 className="text-lg font-bold text-slate-900">System Capabilities & Health</h2>
                <p className="text-xs text-slate-500">Live inspection of parsers, OCR engines, Celery workers, and database connections.</p>
              </div>
              <HealthCard
                health={health}
                loading={healthLoading}
                error={healthError}
                onRefresh={checkHealth}
              />
            </div>
          )}

          {/* VIEW: DOCUMENTS (INGESTION & MANAGEMENT) */}
          {activeView === 'documents' && (
            <div className="space-y-8">
              <div className="border-b border-slate-200 pb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-slate-900">Document Management & Ingestion</h2>
                  <p className="text-xs text-slate-500">Upload financial documents, trigger processing, and launch AI extraction.</p>
                </div>
              </div>
              <DocumentUploadZone onUploadSuccess={handleUploadSuccess} />
              <DocumentList
                documents={documents}
                total={totalDocs}
                page={page}
                pageSize={pageSize}
                totalPages={totalPages}
                loading={docsLoading}
                onPageChange={handlePageChange}
                onFilterChange={handleFilterChange}
                onViewDetails={(doc) => setSelectedDoc(doc)}
                onDeleteDocument={handleDeleteDocument}
                onRefresh={loadDocuments}
                onTriggerProcess={handleTriggerProcess}
                onExtractInvoices={(doc) => setExtractingDoc(doc)}
              />
            </div>
          )}

          {/* VIEW: DASHBOARD (DEFAULT VIEW) */}
          {activeView === 'dashboard' && (
            <div className="space-y-8">
              {/* Executive Welcome & Hero */}
              <div className="bg-gradient-to-r from-sky-900 via-slate-900 to-indigo-950 rounded-2xl p-6 sm:p-8 text-white shadow-md relative overflow-hidden">
                <div className="relative z-10 max-w-3xl">
                  <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-white/10 backdrop-blur-sm text-xs font-semibold text-sky-200 mb-4">
                    <CheckCircle className="w-3.5 h-3.5 text-sky-400" />
                    <span>Database Foundation & Document Ingestion Initialized</span>
                  </div>
                  <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
                    Financial Document Intelligence System
                  </h2>
                  <p className="mt-3 text-slate-300 text-sm sm:text-base leading-relaxed">
                    Upload multi-page financial documents (PDFs up to ~1,000 pages, scans, and spreadsheets),
                    verify content integrity with SHA-256 signatures, and store structured metadata in PostgreSQL / SQLite.
                  </p>
                </div>
              </div>

              {/* KPI Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div
                  onClick={() => setActiveView('documents')}
                  className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-indigo-300 transition cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Documents</span>
                    <div className="p-2 bg-slate-100 rounded-lg text-slate-600 group-hover:bg-indigo-50 group-hover:text-indigo-600 transition">
                      <FileText className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-slate-900 font-mono">
                      {metrics ? metrics.total_documents : totalDocs}
                    </span>
                    <span className="text-[11px] text-emerald-600 font-medium">
                      {metrics ? `${metrics.processed_documents} processed` : 'Ready'}
                    </span>
                  </div>
                </div>

                <div
                  onClick={() => setActiveView('invoices')}
                  className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-indigo-300 transition cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Invoices Extracted</span>
                    <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600 transition">
                      <Receipt className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-indigo-700 font-mono">
                      {metrics ? metrics.total_invoices : 0}
                    </span>
                    <span className="text-[11px] text-slate-500">Gemini Flash-Lite</span>
                  </div>
                </div>

                <div
                  onClick={() => setActiveView('review')}
                  className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-amber-300 transition cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Needs Review</span>
                    <div className="p-2 bg-amber-50 rounded-lg text-amber-600 transition">
                      <AlertTriangle className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-amber-700 font-mono">
                      {metrics ? metrics.needs_review_invoices : 0}
                    </span>
                    <span className="text-[11px] text-amber-600 font-semibold flex items-center gap-1">
                      Action Required <ArrowRight className="w-3 h-3" />
                    </span>
                  </div>
                </div>

                <div
                  onClick={() => setActiveView('invoices')}
                  className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-indigo-300 transition cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Human Corrected</span>
                    <div className="p-2 bg-blue-50 rounded-lg text-blue-600 transition">
                      <Edit3 className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-blue-800 font-mono">
                      {metrics ? metrics.manually_corrected_invoices : 0}
                    </span>
                    <span className="text-[11px] text-slate-500 font-medium">Audit verified</span>
                  </div>
                </div>
              </div>

              {/* System Health Status Card */}
              <section>
                <HealthCard
                  health={health}
                  loading={healthLoading}
                  error={healthError}
                  onRefresh={checkHealth}
                />
              </section>

              {/* Document Upload Zone */}
              <section>
                <DocumentUploadZone onUploadSuccess={handleUploadSuccess} />
              </section>

              {/* Uploaded Documents List */}
              <section>
                <DocumentList
                  documents={documents}
                  total={totalDocs}
                  page={page}
                  pageSize={pageSize}
                  totalPages={totalPages}
                  loading={docsLoading}
                  onPageChange={handlePageChange}
                  onFilterChange={handleFilterChange}
                  onViewDetails={(doc) => setSelectedDoc(doc)}
                  onDeleteDocument={handleDeleteDocument}
                  onRefresh={loadDocuments}
                  onTriggerProcess={handleTriggerProcess}
                  onExtractInvoices={(doc) => setExtractingDoc(doc)}
                />
              </section>

              {/* Pipeline Architecture Highlights */}
              <section className="space-y-4">
                <h2 className="text-base font-semibold text-slate-900">
                  System Architecture & Pipeline Modules
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                    <div className="w-10 h-10 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center mb-3">
                      <FileText className="w-5 h-5" />
                    </div>
                    <h3 className="font-semibold text-slate-900 text-sm">Document Ingestion</h3>
                    <p className="text-xs text-slate-500 mt-1">
                      Multi-format ingestion supporting PDF, JPG, PNG, TIFF, XLS, XLSX, and CSV with SHA-256 verification and streaming chunking.
                    </p>
                  </div>

                  <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                    <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center mb-3">
                      <Cpu className="w-5 h-5" />
                    </div>
                    <h3 className="font-semibold text-slate-900 text-sm">Processing & OCR</h3>
                    <p className="text-xs text-slate-500 mt-1">
                      PyMuPDF for rapid multi-page PDF rendering, Tesseract OCR with OpenCV image enhancement, and Pandas/OpenPyXL spreadsheet parsers.
                    </p>
                  </div>

                  <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
                    <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center mb-3">
                      <ShieldCheck className="w-5 h-5" />
                    </div>
                    <h3 className="font-semibold text-slate-900 text-sm">AI Extraction & Validation</h3>
                    <p className="text-xs text-slate-500 mt-1">
                      Configurable LLM provider for structured invoice extraction, mathematical total validation, line-item reconciliation, and uncertainty tracking.
                    </p>
                  </div>

                  <div
                    onClick={() => setActiveView('search')}
                    className="bg-white p-5 rounded-xl border border-slate-200 shadow-xs hover:border-indigo-300 transition cursor-pointer group"
                  >
                    <div className="w-10 h-10 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center mb-3 group-hover:bg-indigo-50 group-hover:text-indigo-600 transition">
                      <Search className="w-5 h-5" />
                    </div>
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-slate-900 text-sm">Semantic & Text Search</h3>
                      <ArrowRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-indigo-600 transition" />
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      Keyword, vector semantic, and hybrid Reciprocal Rank Fusion (RRF) search across document chunks and structured invoices.
                    </p>
                  </div>
                </div>
              </section>

              {/* Database & Models Spec Summary */}
              <section className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
                <div className="flex items-center space-x-2 pb-3 border-b border-slate-100">
                  <Layers className="w-5 h-5 text-slate-700" />
                  <h3 className="font-semibold text-slate-900 text-sm">Relational Schema & Database Models</h3>
                </div>
                <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 text-xs text-slate-600">
                  <div className="p-3 bg-slate-50 rounded-lg">
                    <span className="font-semibold text-slate-800 block">Document</span>
                    UUID, original/stored filename, file path, mime/file type, size, SHA-256 hash, status.
                  </div>
                  <div className="p-3 bg-slate-50 rounded-lg">
                    <span className="font-semibold text-slate-800 block">Invoice & Line Items</span>
                    Document FK, invoice number, date, supplier, customer, Numeric amounts, line items.
                  </div>
                  <div className="p-3 bg-slate-50 rounded-lg">
                    <span className="font-semibold text-slate-800 block">Audit & Validation</span>
                    ValidationIssue (severity, resolved status) and ProcessingEvent timeline audit log.
                  </div>
                </div>
              </section>
            </div>
          )}
        </main>

        {/* Document Details Modal */}
        <DocumentDetailModal
          document={selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onProcessingComplete={loadDocuments}
        />

        {/* AI Extraction Run Modal */}
        {extractingDoc && (
          <ExtractionRunModal
            document={extractingDoc}
            onClose={() => setExtractingDoc(null)}
            onViewInvoices={(_docId) => {
              setExtractingDoc(null);
              setActiveView('invoices');
            }}
          />
        )}

        {/* Footer */}
        <footer className="bg-white border-t border-slate-200 py-4 mt-auto">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500">
            <p>Financial Document Intelligence System &bull; AI Engineer Recruitment Assessment</p>
            <p className="mt-1 sm:mt-0 font-mono">FastAPI + React Document Ingestion Baseline</p>
          </div>
        </footer>
      </div>
    </div>
  );
};
