import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SearchPage } from './pages/SearchPage';
import * as api from './services/api';

vi.mock('./services/api', () => ({
  fetchSearchCapabilities: vi.fn(),
  executeSearch: vi.fn(),
  executeInvoiceSearch: vi.fn(),
  triggerEmbeddingBackfill: vi.fn(),
}));

describe('SearchPage Component', () => {
  const mockCapabilities = {
    keyword_search_available: true,
    semantic_search_available: true,
    hybrid_search_available: true,
    embedding_provider: 'gemini',
    embedding_model: 'text-embedding-004',
    embedding_dimension: 768,
    total_chunks: 10,
    embedded_chunks: 8,
    unembedded_chunks: 2,
    status_message: 'Gemini embedding provider is available.',
  };

  const mockChunkResponse = {
    query: 'Acme',
    mode: 'hybrid',
    total: 1,
    page: 1,
    page_size: 15,
    total_pages: 1,
    fallback_mode: false,
    fallback_reason: null,
    execution_time_ms: 45,
    items: [
      {
        chunk_id: 'c1111111-1111-1111-1111-111111111111',
        document_id: 'd1111111-1111-1111-1111-111111111111',
        document_filename: 'acme_invoice.pdf',
        file_type: 'pdf',
        page_number: 1,
        content: 'Acme Corporation Invoice INV-1001. Total: $1,250.00 USD.',
        highlighted_snippet: '**Acme** Corporation Invoice INV-1001. Total: $1,250.00 USD.',
        score: 0.01639,
        match_type: 'hybrid',
        keyword_rank: 1,
        semantic_rank: 1,
        invoice_id: 'i1111111-1111-1111-1111-111111111111',
        invoice_number: 'INV-1001',
        supplier_name: 'Acme Corporation',
        invoice_total: 1250.0,
        currency: 'USD',
        needs_manual_review: false,
      },
    ],
  };

  const mockFallbackResponse = {
    query: 'Acme',
    mode: 'hybrid',
    total: 1,
    page: 1,
    page_size: 15,
    total_pages: 1,
    fallback_mode: true,
    fallback_reason: 'Semantic search is unavailable. Operating in keyword-only fallback mode.',
    execution_time_ms: 12,
    items: [
      {
        chunk_id: 'c1111111-1111-1111-1111-111111111111',
        document_id: 'd1111111-1111-1111-1111-111111111111',
        document_filename: 'acme_invoice.pdf',
        file_type: 'pdf',
        page_number: 1,
        content: 'Acme Corporation Invoice INV-1001.',
        highlighted_snippet: '**Acme** Corporation Invoice INV-1001.',
        score: 1.0,
        match_type: 'keyword',
        keyword_rank: 1,
      },
    ],
  };

  const mockInvoiceResponse = {
    query: 'Wayne',
    total: 1,
    page: 1,
    page_size: 15,
    total_pages: 1,
    execution_time_ms: 18,
    items: [
      {
        invoice_id: 'i2222222-2222-2222-2222-222222222222',
        document_id: 'd2222222-2222-2222-2222-222222222222',
        document_filename: 'wayne_q2.xlsx',
        invoice_number: 'WT-9921',
        invoice_date: '2026-06-01',
        supplier_name: 'Wayne Enterprises',
        customer_name: 'Gotham City',
        subtotal: 8000.0,
        tax: 500.0,
        total: 8500.0,
        currency: 'EUR',
        needs_manual_review: true,
        is_manually_corrected: false,
        is_valid: true,
        has_duplicates: false,
        unresolved_issue_count: 0,
        line_items_count: 3,
        matched_fields: ['supplier_name'],
        highlighted_snippet: 'Supplier: **Wayne** Enterprises',
        created_at: new Date().toISOString(),
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchSearchCapabilities).mockResolvedValue(mockCapabilities);
    vi.mocked(api.executeSearch).mockResolvedValue(mockChunkResponse);
    vi.mocked(api.executeInvoiceSearch).mockResolvedValue(mockInvoiceResponse);
    vi.mocked(api.triggerEmbeddingBackfill).mockResolvedValue({
      total_chunks_processed: 2,
      embedded_count: 2,
      skipped_count: 0,
      failed_count: 0,
      status: 'completed',
      message: 'Backfilled 2 chunks successfully.',
    });
  });

  it('renders search bar, mode selector, and capabilities banner', async () => {
    render(<SearchPage />);

    expect(screen.getByText('Hybrid Document & Financial Search')).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/Search by keywords, invoice number/i)
    ).toBeInTheDocument();
    expect(screen.getByText('Hybrid (RRF)')).toBeInTheDocument();
    expect(screen.getByText('Keyword Only')).toBeInTheDocument();
    expect(screen.getByText('Semantic Only')).toBeInTheDocument();
    expect(screen.getByText('Structured Invoices')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Keyword Search/i)).toBeInTheDocument();
      expect(screen.getByText(/text-embedding-004/i)).toBeInTheDocument();
      expect(screen.getByText(/8 \/ 10 Chunks Embedded/i)).toBeInTheDocument();
    });
  });

  it('triggers hybrid search and displays highlighted match items', async () => {
    render(<SearchPage />);

    const input = screen.getByPlaceholderText(/Search by keywords, invoice number/i);
    fireEvent.change(input, { target: { value: 'Acme' } });

    const searchBtn = screen.getByRole('button', { name: /Search/i });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(api.executeSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          q: 'Acme',
          mode: 'hybrid',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('HYBRID MATCH (RRF)')).toBeInTheDocument();
      expect(screen.getByText('acme_invoice.pdf')).toBeInTheDocument();
      expect(screen.getByText('Linked Invoice #INV-1001')).toBeInTheDocument();
    });
  });

  it('displays fallback banner when semantic search is unavailable', async () => {
    vi.mocked(api.executeSearch).mockResolvedValue(mockFallbackResponse);

    render(<SearchPage />);

    const input = screen.getByPlaceholderText(/Search by keywords, invoice number/i);
    fireEvent.change(input, { target: { value: 'Acme' } });

    const searchBtn = screen.getByRole('button', { name: /Search/i });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(screen.getByText('Fallback Retrieval Mode Active')).toBeInTheDocument();
      expect(
        screen.getByText(/Operating in keyword-only fallback mode/i)
      ).toBeInTheDocument();
    });
  });

  it('switches to structured invoices mode and renders invoice hit cards', async () => {
    render(<SearchPage />);

    // Click on Structured Invoices mode tab
    const invoiceTab = screen.getByText('Structured Invoices');
    fireEvent.click(invoiceTab);

    const input = screen.getByPlaceholderText(/Search by keywords, invoice number/i);
    fireEvent.change(input, { target: { value: 'Wayne' } });

    const searchBtn = screen.getByRole('button', { name: /Search/i });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(api.executeInvoiceSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          q: 'Wayne',
        })
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Invoice #WT-9921')).toBeInTheDocument();
      expect(screen.getByText(/Wayne Enterprises/i)).toBeInTheDocument();
      expect(screen.getByText(/EUR 8500.00/i)).toBeInTheDocument();
      expect(screen.getByText('NEEDS REVIEW')).toBeInTheDocument();
      expect(screen.getByText('supplier_name')).toBeInTheDocument();
    });
  });

  it('triggers backfill when clicking backfill button', async () => {
    render(<SearchPage />);

    await waitFor(() => {
      expect(screen.getByText(/Backfill \(2\)/i)).toBeInTheDocument();
    });

    const backfillBtn = screen.getByText(/Backfill \(2\)/i);
    fireEvent.click(backfillBtn);

    await waitFor(() => {
      expect(api.triggerEmbeddingBackfill).toHaveBeenCalled();
      expect(screen.getByText('Backfilled 2 chunks successfully.')).toBeInTheDocument();
    });
  });
});
