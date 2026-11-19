import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import App from './App';
import * as api from './services/api';

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
  fetchDashboardMetrics: vi.fn().mockResolvedValue({
    total_documents: 1,
    processed_documents: 1,
    processing_documents: 0,
    failed_documents: 0,
    total_invoices: 2,
    needs_review_invoices: 1,
    manually_corrected_invoices: 1,
    recent_extraction_runs: [
      {
        id: 'run-1',
        document_id: '123e4567-e89b-12d3-a456-426614174000',
        provider: 'gemini',
        model_name: 'gemini-flash-lite-latest',
        prompt_version: '1.0',
        status: 'completed',
        processing_time_ms: 1250,
        total_contexts: 1,
        successful_contexts: 1,
        skipped_contexts: 0,
        failed_contexts: 0,
        created_at: new Date().toISOString(),
      },
    ],
    recent_corrections: [
      {
        id: 'audit-1',
        invoice_id: 'inv-test-1',
        correction_type: 'HEADER_UPDATE',
        changed_fields: ['total'],
        previous_values: { total: '120.00' },
        new_values: { total: '125.00' },
        reason: 'Adjusted total for shipping',
        corrected_by: 'reviewer_bob',
        corrected_at: new Date().toISOString(),
      },
    ],
  }),
  fetchInvoices: vi.fn().mockResolvedValue({
    total: 2,
    skip: 0,
    limit: 10,
    items: [
      {
        id: 'inv-test-1',
        document_id: '123e4567-e89b-12d3-a456-426614174000',
        invoice_number: 'INV-TEST-001',
        invoice_date: '2026-11-10',
        supplier_name: 'Acme Corporation',
        customer_name: 'Global Corp Ltd',
        subtotal: 100.0,
        tax: 20.0,
        total: 120.0,
        currency: 'USD',
        needs_manual_review: true,
        is_manually_corrected: false,
        field_evidence: {
          total: {
            source_chunk_id: 'chk-1',
            page_number: 1,
            relevant_text: 'Total Balance: $120.00',
          },
        },
        field_confidence: {
          overall_confidence: 0.92,
        },
        line_items: [
          {
            id: 'li-1',
            invoice_id: 'inv-test-1',
            description: 'Ergonomic Desk Chair',
            quantity: 2,
            unit_price: 50.0,
            tax: 10.0,
            line_total: 100.0,
            field_evidence: {
              relevant_text: 'Ergonomic Desk Chair Qty: 2 @ $50.00',
            },
            created_at: new Date().toISOString(),
          },
        ],
        validation_issues: [
          {
            id: 'val-1',
            invoice_id: 'inv-test-1',
            field_name: 'tax',
            issue_type: 'tax_discrepancy',
            severity: 'warning',
            description: 'Calculated tax deviates from reported tax by 0.05',
            resolved: false,
            created_at: new Date().toISOString(),
          },
        ],
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
    supplier_name: 'Acme Corporation',
    customer_name: 'Global Corp Ltd',
    subtotal: 100.0,
    tax: 20.0,
    total: 120.0,
    currency: 'USD',
    needs_manual_review: true,
    is_manually_corrected: false,
    field_evidence: {
      total: {
        source_chunk_id: 'chk-1',
        page_number: 1,
        relevant_text: 'Total Balance: $120.00',
      },
    },
    field_confidence: {
      overall_confidence: 0.92,
    },
    line_items: [
      {
        id: 'li-1',
        invoice_id: 'inv-test-1',
        description: 'Ergonomic Desk Chair',
        quantity: 2,
        unit_price: 50.0,
        tax: 10.0,
        line_total: 100.0,
        field_evidence: {
          relevant_text: 'Ergonomic Desk Chair Qty: 2 @ $50.00',
        },
        created_at: new Date().toISOString(),
      },
    ],
    validation_issues: [
      {
        id: 'val-1',
        invoice_id: 'inv-test-1',
        field_name: 'tax',
        issue_type: 'tax_discrepancy',
        severity: 'warning',
        description: 'Calculated tax deviates from reported tax by 0.05',
        resolved: false,
        created_at: new Date().toISOString(),
      },
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }),
  updateInvoice: vi.fn().mockImplementation((_id, payload) =>
    Promise.resolve({
      id: 'inv-test-1',
      document_id: '123e4567-e89b-12d3-a456-426614174000',
      invoice_number: payload.invoice_number || 'INV-TEST-001',
      invoice_date: payload.invoice_date || '2026-11-10',
      supplier_name: payload.supplier_name || 'Acme Corporation',
      customer_name: payload.customer_name || 'Global Corp Ltd',
      subtotal: payload.subtotal !== undefined ? payload.subtotal : 100.0,
      tax: payload.tax !== undefined ? payload.tax : 20.0,
      total: payload.total !== undefined ? payload.total : 120.0,
      currency: payload.currency || 'USD',
      needs_manual_review: payload.needs_manual_review !== undefined ? payload.needs_manual_review : false,
      is_manually_corrected: true,
      line_items: [],
      validation_issues: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
  ),
  updateLineItem: vi.fn().mockResolvedValue({
    id: 'li-1',
    description: 'Updated Ergonomic Chair',
  }),
  createLineItem: vi.fn().mockResolvedValue({
    id: 'li-2',
    description: 'Delivery Fee',
  }),
  deleteLineItem: vi.fn().mockResolvedValue({
    message: 'Deleted successfully',
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
      corrected_by: 'reviewer_bob',
      corrected_at: new Date().toISOString(),
    },
  ]),
  triggerInvoiceExtraction: vi.fn().mockResolvedValue({
    extraction_run_id: 'run-1',
    document_id: '123e4567-e89b-12d3-a456-426614174000',
    status: 'queued',
    processing_mode: 'inline',
    message: 'Invoice extraction queued.',
  }),
  fetchExtractionRun: vi.fn().mockResolvedValue({
    id: 'run-1',
    document_id: '123e4567-e89b-12d3-a456-426614174000',
    provider: 'gemini',
    model_name: 'gemini-flash-lite-latest',
    prompt_version: '1.0',
    status: 'completed',
    processing_time_ms: 1250,
    total_contexts: 1,
    successful_contexts: 1,
    skipped_contexts: 0,
    failed_contexts: 0,
    created_at: new Date().toISOString(),
  }),
  getDocumentFileUrl: vi.fn((id: string) => `http://localhost:8000/api/v1/documents/${id}/file`),
  uploadDocuments: vi.fn().mockResolvedValue({ accepted: [], rejected: [], total_accepted: 0, total_rejected: 0 }),
  deleteDocument: vi.fn().mockResolvedValue({ status: 'success', message: 'Deleted', id: '123' }),
  triggerProcessing: vi.fn().mockResolvedValue({ status: 'completed' }),
  fetchDocumentDetails: vi.fn().mockResolvedValue({ id: '123' }),
  fetchDocumentChunks: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  revalidateInvoice: vi.fn().mockResolvedValue({
    invoice_id: 'inv-test-1',
    total_issues: 1,
    unresolved_errors: 0,
    unresolved_warnings: 1,
    unresolved_info: 0,
    resolved_issues: 0,
    needs_manual_review: true,
    is_valid: false,
    issues: [
      {
        id: 'val-1',
        invoice_id: 'inv-test-1',
        field_name: 'tax',
        issue_type: 'tax_discrepancy',
        severity: 'warning',
        description: 'Calculated tax deviates from reported tax by 0.05',
        expected_value: '20.05',
        observed_value: '20.00',
        resolved: false,
        created_at: new Date().toISOString(),
      },
    ],
    duplicates_detected: [
      {
        invoice_id: 'inv-dup-999',
        document_id: 'doc-dup-999',
        invoice_number: 'INV-TEST-001',
        supplier_name: 'Acme Corporation',
        total: 120.0,
        currency: 'USD',
        match_type: 'exact_duplicate',
        match_reasons: ["Normalized invoice number 'INVTEST001' matches candidate."],
      },
    ],
  }),
  revalidateDocumentInvoices: vi.fn().mockResolvedValue([]),
  fetchInvoiceValidationIssues: vi.fn().mockResolvedValue([
    {
      id: 'val-1',
      invoice_id: 'inv-test-1',
      field_name: 'tax',
      issue_type: 'tax_discrepancy',
      severity: 'warning',
      description: 'Calculated tax deviates from reported tax by 0.05',
      expected_value: '20.05',
      observed_value: '20.00',
      resolved: false,
      created_at: new Date().toISOString(),
    },
  ]),
  fetchInvoiceDuplicates: vi.fn().mockResolvedValue([
    {
      invoice_id: 'inv-dup-999',
      document_id: 'doc-dup-999',
      invoice_number: 'INV-TEST-001',
      supplier_name: 'Acme Corporation',
      total: 120.0,
      currency: 'USD',
      match_type: 'exact_duplicate',
      match_reasons: ["Normalized invoice number 'INVTEST001' matches candidate."],
    },
  ]),
  fetchSystemValidationIssues: vi.fn().mockResolvedValue({ total: 0, skip: 0, limit: 50, items: [] }),
  resolveValidationIssue: vi.fn().mockResolvedValue({
    id: 'val-1',
    resolved: true,
    resolved_by: 'auditor_tester',
    resolution_notes: 'Verified rounding discrepancy',
  }),
  reopenValidationIssue: vi.fn().mockResolvedValue({
    id: 'val-1',
    resolved: false,
  }),
}));

describe('Invoice Review and Manual Correction Workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders sidebar navigation with all workflow tabs', async () => {
    render(<App />);

    expect(screen.getByRole('button', { name: /Dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Documents/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Invoices/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Needs Review/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Processing History/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /System Health/i })).toBeInTheDocument();
  });

  it('navigates to Invoices view and displays extracted invoice table', async () => {
    render(<App />);

    // Click on Invoices in sidebar
    const invoicesNav = screen.getByRole('button', { name: /Invoices/i });
    fireEvent.click(invoicesNav);

    await waitFor(() => {
      expect(screen.getByText('Extracted Invoices & Review Dashboard')).toBeInTheDocument();
      expect(screen.getByText('INV-TEST-001')).toBeInTheDocument();
      expect(screen.getByText('Acme Corporation')).toBeInTheDocument();
      expect(screen.getByText(/120\.00/)).toBeInTheDocument();
      expect(screen.getByText(/92% \(Est\.\)/i)).toBeInTheDocument();
    });
  });

  it('opens InvoiceDetailModal, inspects evidence, and toggles edit mode', async () => {
    render(<App />);

    // Go to Invoices
    fireEvent.click(screen.getByRole('button', { name: /Invoices/i }));

    await waitFor(() => {
      expect(screen.getByText('INV-TEST-001')).toBeInTheDocument();
    });

    // Click Review & Edit
    const reviewBtn = screen.getByRole('button', { name: /Review & Edit/i });
    fireEvent.click(reviewBtn);

    // Modal opens
    await waitFor(() => {
      expect(screen.getByText('Invoice #INV-TEST-001')).toBeInTheDocument();
      expect(screen.getAllByText(/Manual Review Required/i).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText(/Pre-tax Subtotal:/i)).toBeInTheDocument();
    });

    // Switch to Source Evidence Inspector tab
    fireEvent.click(screen.getByText('Source Evidence Inspector'));

    await waitFor(() => {
      expect(screen.getByText(/Provenance & Evidence Citations/i)).toBeInTheDocument();
      expect(screen.getByText('Verified in Document')).toBeInTheDocument();
    });

    // Switch to Correction History tab
    fireEvent.click(screen.getByText(/Correction History/i));

    await waitFor(() => {
      expect(screen.getByText(/Audit Trail & Change History/i)).toBeInTheDocument();
      expect(screen.getByText(/Adjusted total for shipping/i)).toBeInTheDocument();
      expect(screen.getByText(/reviewer_bob/i)).toBeInTheDocument();
    });

    // Switch back to Overview and click Edit Header & Totals
    fireEvent.click(screen.getByText('Overview & Summary'));
    const editHeaderBtn = screen.getByRole('button', { name: /Edit Header & Totals/i });
    fireEvent.click(editHeaderBtn);

    await waitFor(() => {
      expect(screen.getByText(/Edit Invoice Header & Financial Totals/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/Explain what was incorrect/i)).toBeInTheDocument();
    });

    // Enter correction reason and save
    const reasonInput = screen.getByPlaceholderText(/Explain what was incorrect/i);
    fireEvent.change(reasonInput, { target: { value: 'Corrected supplier spelling and verified balance' } });

    const saveBtn = screen.getByRole('button', { name: /Save Correction/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.updateInvoice).toHaveBeenCalledWith(
        'inv-test-1',
        expect.objectContaining({
          reason: 'Corrected supplier spelling and verified balance',
        })
      );
    });
  });

  it('displays duplicate invoice alert and supports on-demand revalidation', async () => {
    render(<App />);

    const invoicesNav = screen.getByRole('button', { name: /Invoices/i });
    fireEvent.click(invoicesNav);

    await waitFor(() => {
      expect(screen.getByText('INV-TEST-001')).toBeInTheDocument();
    });

    const reviewBtn = screen.getByRole('button', { name: /Review & Edit/i });
    fireEvent.click(reviewBtn);

    // Verify modal header has Revalidate button
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Revalidate/i })).toBeInTheDocument();
    });

    // Verify duplicate warning banner is rendered
    await waitFor(() => {
      expect(screen.getByText(/Potential Duplicate Invoice Detected!/i)).toBeInTheDocument();
      expect(screen.getByText(/Exact Match/i)).toBeInTheDocument();
    });

    // Click Revalidate button
    const revalidateBtn = screen.getByRole('button', { name: /Revalidate/i });
    fireEvent.click(revalidateBtn);

    await waitFor(() => {
      expect(api.revalidateInvoice).toHaveBeenCalledWith('inv-test-1');
    });
  });

  it('navigates to Validation & Issues tab and allows resolving an issue', async () => {
    render(<App />);

    const invoicesNav = screen.getByRole('button', { name: /Invoices/i });
    fireEvent.click(invoicesNav);

    await waitFor(() => {
      expect(screen.getByText('INV-TEST-001')).toBeInTheDocument();
    });

    const reviewBtn = screen.getByRole('button', { name: /Review & Edit/i });
    fireEvent.click(reviewBtn);

    // Click on Validation & Issues tab
    await waitFor(() => {
      expect(screen.getByText(/Validation & Issues/i)).toBeInTheDocument();
    });
    const valTab = screen.getByText(/Validation & Issues/i);
    fireEvent.click(valTab);

    // Check that issues and metrics are rendered
    await waitFor(() => {
      expect(screen.getAllByText(/Calculated tax deviates from reported tax/i).length).toBeGreaterThan(0);
      expect(screen.getByRole('button', { name: /Mark as Resolved/i })).toBeInTheDocument();
    });

    // Click Mark as Resolved
    const resolveBtn = screen.getByRole('button', { name: /Mark as Resolved/i });
    fireEvent.click(resolveBtn);

    // Fill in inline resolution notes and confirm
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Resolution explanation/i)).toBeInTheDocument();
    });

    const notesInput = screen.getByPlaceholderText(/Resolution explanation/i);
    fireEvent.change(notesInput, { target: { value: 'Verified legitimate tax rounding difference' } });

    const confirmBtn = screen.getByRole('button', { name: /Confirm Resolve/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.resolveValidationIssue).toHaveBeenCalledWith(
        'val-1',
        expect.objectContaining({
          resolution_notes: 'Verified legitimate tax rounding difference',
        })
      );
    });
  });
});
