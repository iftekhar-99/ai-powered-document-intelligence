import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import App from './App';

// Mock the API services
vi.mock('./services/api', () => ({
  fetchHealth: vi.fn().mockResolvedValue({
    status: 'healthy',
    app_name: 'Financial Document Intelligence System',
    version: '0.1.0',
    environment: 'development',
    timestamp: new Date().toISOString(),
    services: {
      api: 'online',
      database: 'sqlite (active)',
      redis: 'configured',
    },
    capabilities: {
      pdf_digital_extraction: true,
      tesseract_available: false,
      tesseract_executable: 'not found',
      tesseract_version: 'unavailable',
      ocr_languages: [],
      xlsx_processing: true,
      xls_processing: true,
      csv_processing: true,
      include_hidden_sheets: true,
      background_processing_mode: 'inline',
      redis_connected: false,
      redis_status: 'offline',
    },
  }),
  fetchDocuments: vi.fn().mockResolvedValue({
    items: [
      {
        id: '123e4567-e89b-12d3-a456-426614174000',
        original_filename: 'Q3_Invoice_2026.pdf',
        stored_filename: 'stored-123.pdf',
        file_type: 'pdf',
        mime_type: 'application/pdf',
        file_size: 45678,
        sha256_hash: 'abcdef123456',
        status: 'completed',
        page_count: 2,
        total_chunks: 2,
        extracted_characters: 1540,
        extraction_method_summary: 'DIGITAL_TEXT',
        uploaded_at: new Date().toISOString(),
      },
    ],
    total: 1,
    page: 1,
    page_size: 10,
    total_pages: 1,
  }),
  uploadDocuments: vi.fn().mockResolvedValue({
    accepted: [],
    rejected: [],
    total_accepted: 0,
    total_rejected: 0,
  }),
  deleteDocument: vi.fn().mockResolvedValue({
    status: 'success',
    message: 'Deleted',
    id: '123',
  }),
  fetchDocumentDetails: vi.fn().mockResolvedValue({
    id: '123e4567-e89b-12d3-a456-426614174000',
    original_filename: 'Q3_Invoice_2026.pdf',
    stored_filename: 'stored-123.pdf',
    file_type: 'pdf',
    mime_type: 'application/pdf',
    file_size: 45678,
    sha256_hash: 'abcdef123456',
    status: 'completed',
    page_count: 2,
    total_chunks: 2,
    extracted_characters: 1540,
    extraction_method_summary: 'DIGITAL_TEXT',
    uploaded_at: new Date().toISOString(),
    processed_at: new Date().toISOString(),
    processing_events: [
      {
        id: 'ev-1',
        event_type: 'processing_completed',
        message: 'Extraction completed successfully with 2 chunks.',
        created_at: new Date().toISOString(),
      },
    ],
  }),
  fetchDocumentChunks: vi.fn().mockResolvedValue({
    items: [
      {
        id: 'chk-1',
        document_id: '123e4567-e89b-12d3-a456-426614174000',
        chunk_index: 0,
        source_type: 'PDF_PAGE',
        page_number: 1,
        content: 'Invoice #INV-2026-001\nTotal: $1,500.00',
        extraction_method: 'DIGITAL_TEXT',
        ocr_confidence: null,
        created_at: new Date().toISOString(),
      },
      {
        id: 'chk-2',
        document_id: '123e4567-e89b-12d3-a456-426614174000',
        chunk_index: 1,
        source_type: 'PDF_PAGE',
        page_number: 2,
        content: 'Terms and conditions for payment',
        extraction_method: 'DIGITAL_TEXT',
        ocr_confidence: null,
        created_at: new Date().toISOString(),
      },
    ],
    total: 2,
    page: 1,
    page_size: 10,
    total_pages: 1,
  }),
  triggerProcessing: vi.fn().mockResolvedValue({
    document_id: '123e4567-e89b-12d3-a456-426614174000',
    status: 'completed',
    file_type: 'pdf',
    total_chunks: 2,
    extracted_characters: 1540,
    extraction_method_summary: 'DIGITAL_TEXT',
    uploaded_at: new Date().toISOString(),
    processing_events: [],
  }),
  getDocumentFileUrl: vi.fn((id: string) => `http://localhost:8000/api/v1/documents/${id}/file`),
  fetchDashboardMetrics: vi.fn().mockResolvedValue({
    total_documents: 1,
    processed_documents: 1,
    processing_documents: 0,
    failed_documents: 0,
    total_invoices: 1,
    needs_review_invoices: 0,
    manually_corrected_invoices: 0,
    recent_extraction_runs: [],
    recent_corrections: [],
  }),
  fetchInvoices: vi.fn().mockResolvedValue({
    total: 1,
    skip: 0,
    limit: 10,
    items: [
      {
        id: 'inv-test-1',
        document_id: '123e4567-e89b-12d3-a456-426614174000',
        invoice_number: 'INV-TEST-001',
        invoice_date: '2026-11-10',
        supplier_name: 'ABC Supplies Ltd',
        customer_name: 'XYZ Corporation',
        subtotal: 100.0,
        tax: 20.0,
        total: 120.0,
        currency: 'USD',
        needs_manual_review: false,
        is_manually_corrected: false,
        line_items: [],
        validation_issues: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ],
  }),
  fetchInvoice: vi.fn().mockResolvedValue({
    id: 'inv-test-1',
    document_id: '123e4567-e89b-12d3-a456-426614174000',
    invoice_number: 'INV-TEST-001',
    invoice_date: '2026-11-10',
    supplier_name: 'ABC Supplies Ltd',
    customer_name: 'XYZ Corporation',
    subtotal: 100.0,
    tax: 20.0,
    total: 120.0,
    currency: 'USD',
    needs_manual_review: false,
    is_manually_corrected: false,
    line_items: [
      {
        id: 'li-1',
        invoice_id: 'inv-test-1',
        description: 'Office Chair Model X',
        quantity: 2,
        unit_price: 50.0,
        tax: 10.0,
        line_total: 100.0,
        created_at: new Date().toISOString(),
      },
    ],
    validation_issues: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }),
  updateInvoice: vi.fn().mockResolvedValue({
    id: 'inv-test-1',
    invoice_number: 'INV-TEST-001-EDITED',
    is_manually_corrected: true,
  }),
  updateLineItem: vi.fn().mockResolvedValue({
    id: 'li-1',
    description: 'Updated Chair',
  }),
  createLineItem: vi.fn().mockResolvedValue({
    id: 'li-new',
    description: 'New Item',
  }),
  deleteLineItem: vi.fn().mockResolvedValue({
    message: 'Deleted',
  }),
  fetchInvoiceCorrections: vi.fn().mockResolvedValue([
    {
      id: 'audit-1',
      invoice_id: 'inv-test-1',
      correction_type: 'HEADER_UPDATE',
      changed_fields: ['total'],
      previous_values: { total: '120.00' },
      new_values: { total: '125.00' },
      reason: 'Adjusted total for shipping',
      corrected_by: 'reviewer',
      corrected_at: new Date().toISOString(),
    },
  ]),
  triggerInvoiceExtraction: vi.fn().mockResolvedValue({
    extraction_run_id: 'run-1',
    document_id: '123e4567-e89b-12d3-a456-426614174000',
    status: 'queued',
    processing_mode: 'inline',
    message: 'Invoice extraction queued in inline mode.',
  }),
  fetchExtractionRun: vi.fn().mockResolvedValue({
    id: 'run-1',
    document_id: '123e4567-e89b-12d3-a456-426614174000',
    provider: 'gemini',
    model_name: 'gemini-flash-lite-latest',
    prompt_version: '1.0',
    status: 'completed',
    total_contexts: 1,
    successful_contexts: 1,
    skipped_contexts: 0,
    failed_contexts: 0,
    created_at: new Date().toISOString(),
  }),
  revalidateInvoice: vi.fn().mockResolvedValue({
    invoice_id: 'inv-test-1',
    total_issues: 0,
    unresolved_errors: 0,
    unresolved_warnings: 0,
    unresolved_info: 0,
    resolved_issues: 0,
    needs_manual_review: false,
    is_valid: true,
    issues: [],
    duplicates_detected: [],
  }),
  revalidateDocumentInvoices: vi.fn().mockResolvedValue([]),
  fetchInvoiceValidationIssues: vi.fn().mockResolvedValue([]),
  fetchInvoiceDuplicates: vi.fn().mockResolvedValue([]),
  fetchSystemValidationIssues: vi.fn().mockResolvedValue({ total: 0, skip: 0, limit: 50, items: [] }),
  resolveValidationIssue: vi.fn().mockResolvedValue({
    id: 'val-1',
    resolved: true,
  }),
  reopenValidationIssue: vi.fn().mockResolvedValue({
    id: 'val-1',
    resolved: false,
  }),
}));

describe('App Component', () => {
  it('renders the header and title confirming application is running', async () => {
    render(<App />);
    expect(screen.getByText('DocIntel AI')).toBeInTheDocument();
    expect(
      screen.getAllByText('Financial Document Intelligence System').length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Environment Active')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Overall Status')).toBeInTheDocument();
      expect(screen.getByText('PDF Digital Parser (PyMuPDF)')).toBeInTheDocument();
      expect(screen.getByText('Tesseract OCR Engine')).toBeInTheDocument();
    });
  });

  it('renders the document upload zone with supported format indicators', async () => {
    render(<App />);
    expect(screen.getByText('Upload Financial Documents')).toBeInTheDocument();
    expect(screen.getByText('PDF:')).toBeInTheDocument();
    expect(screen.getByText('Images:')).toBeInTheDocument();
    expect(screen.getByText('Spreadsheets:')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Overall Status')).toBeInTheDocument();
      expect(screen.getByText('PDF Digital Parser (PyMuPDF)')).toBeInTheDocument();
      expect(screen.getByText('Tesseract OCR Engine')).toBeInTheDocument();
    });
  });

  it('renders the document repository table with fetched document and extraction summary', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Q3_Invoice_2026.pdf')).toBeInTheDocument();
      expect(screen.getByText('44.61 KB')).toBeInTheDocument();
      expect(screen.getByText(/2 chunks • 2 pages/i)).toBeInTheDocument();
      expect(screen.getByText('DIGITAL_TEXT')).toBeInTheDocument();
    });
  });

  it('opens DocumentDetailModal and views chunk inspector when Inspect button is clicked', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Q3_Invoice_2026.pdf')).toBeInTheDocument();
    });

    const inspectBtn = screen.getByTitle('Inspect Chunks and Details');
    fireEvent.click(inspectBtn);

    await waitFor(() => {
      expect(screen.getByText('Overview & Events')).toBeInTheDocument();
      expect(screen.getByText('Extracted Chunks (2)')).toBeInTheDocument();
    });

    // Click on Extracted Chunks tab
    const chunksTab = screen.getByText('Extracted Chunks (2)');
    fireEvent.click(chunksTab);

    await waitFor(() => {
      expect(screen.getByText(/Invoice #INV-2026-001/i)).toBeInTheDocument();
      expect(screen.getByText(/Terms and conditions for payment/i)).toBeInTheDocument();
    });
  });

  it('renders the system architecture modules', async () => {
    render(<App />);
    expect(screen.getByText('Processing & OCR')).toBeInTheDocument();
    expect(screen.getByText('AI Extraction & Validation')).toBeInTheDocument();
    expect(screen.getByText('Semantic & Text Search')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Overall Status')).toBeInTheDocument();
      expect(screen.getByText('PDF Digital Parser (PyMuPDF)')).toBeInTheDocument();
      expect(screen.getByText('Tesseract OCR Engine')).toBeInTheDocument();
    });
  });
});
