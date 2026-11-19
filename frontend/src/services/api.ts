import {
  DashboardMetrics,
  DocumentChunkListResponse,
  DocumentDetail,
  DocumentInvoicesResponse,
  DocumentListResponse,
  DuplicateMatchDetail,
  EmbeddingBackfillResponse,
  ExtractionHistoryResponse,
  ExtractionInitiationResponse,
  ExtractionRunItem,
  HealthResponse,
  InvoiceCorrectionAudit,
  InvoiceDetail,
  InvoiceLineItemDetail,
  InvoiceListResponse,
  InvoiceSearchResponse,
  IssueReopenPayload,
  IssueResolvePayload,
  ProcessingSummaryResponse,
  SearchCapabilitiesResponse,
  SearchMode,
  SearchResponse,
  UploadBatchResponse,
  ValidationIssueDetail,
  ValidationIssueListResponse,
  ValidationSummaryResponse,
} from '../types';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch system health status: HTTP ${response.status}`);
  }

  return response.json();
}

export function uploadDocuments(
  files: File[],
  onProgress?: (percent: number) => void
): Promise<UploadBatchResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();

    for (const file of files) {
      formData.append('files', file);
    }

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response: UploadBatchResponse = JSON.parse(xhr.responseText);
          resolve(response);
        } catch {
          reject(new Error('Invalid JSON response received from server.'));
        }
      } else {
        try {
          const errRes = JSON.parse(xhr.responseText);
          reject(new Error(errRes.detail || `Upload failed with HTTP ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed with HTTP ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => {
      reject(new Error('Network error during file upload. Check backend connectivity.'));
    };

    xhr.open('POST', `${API_BASE_URL}/documents/upload`);
    xhr.send(formData);
  });
}

export async function fetchDocuments(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  file_type?: string;
  search?: string;
}): Promise<DocumentListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.append('page', params.page.toString());
  if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
  if (params?.status) searchParams.append('status', params.status);
  if (params?.file_type) searchParams.append('file_type', params.file_type);
  if (params?.search) searchParams.append('search', params.search);

  const url = `${API_BASE_URL}/documents?${searchParams.toString()}`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch documents: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchDocumentDetails(id: string): Promise<DocumentDetail> {
  const response = await fetch(`${API_BASE_URL}/documents/${id}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch document ${id}: HTTP ${response.status}`);
  }

  return response.json();
}

export async function deleteDocument(id: string): Promise<{ status: string; message: string; id: string }> {
  const response = await fetch(`${API_BASE_URL}/documents/${id}`, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to delete document: HTTP ${response.status}`);
  }

  return response.json();
}

export async function triggerProcessing(id: string): Promise<ProcessingSummaryResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/${id}/process`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Processing trigger failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchDocumentChunks(
  id: string,
  params?: {
    page?: number;
    page_size?: number;
    source_type?: string;
    page_number?: number;
    sheet_name?: string;
  }
): Promise<DocumentChunkListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.append('page', params.page.toString());
  if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
  if (params?.source_type) searchParams.append('source_type', params.source_type);
  if (params?.page_number) searchParams.append('page_number', params.page_number.toString());
  if (params?.sheet_name) searchParams.append('sheet_name', params.sheet_name);

  const url = `${API_BASE_URL}/documents/${id}/chunks?${searchParams.toString()}`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch document chunks: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchProcessingSummary(id: string): Promise<ProcessingSummaryResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/${id}/processing-summary`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch processing summary: HTTP ${response.status}`);
  }

  return response.json();
}

export function getDocumentFileUrl(documentId: string): string {
  return `${API_BASE_URL}/documents/${documentId}/file`;
}

export async function fetchDashboardMetrics(): Promise<DashboardMetrics> {
  const response = await fetch(`${API_BASE_URL}/dashboard/metrics`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch dashboard metrics: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchInvoices(params?: {
  skip?: number;
  limit?: number;
  search?: string;
  currency?: string;
  needs_review?: boolean;
  is_manually_corrected?: boolean;
}): Promise<InvoiceListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.skip !== undefined) searchParams.append('skip', params.skip.toString());
  if (params?.limit !== undefined) searchParams.append('limit', params.limit.toString());
  if (params?.search) searchParams.append('search', params.search);
  if (params?.currency) searchParams.append('currency', params.currency);
  if (params?.needs_review !== undefined) searchParams.append('needs_review', String(params.needs_review));
  if (params?.is_manually_corrected !== undefined) searchParams.append('is_manually_corrected', String(params.is_manually_corrected));

  const url = `${API_BASE_URL}/invoices?${searchParams.toString()}`;
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch invoices: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchInvoice(id: string): Promise<InvoiceDetail> {
  const response = await fetch(`${API_BASE_URL}/invoices/${id}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch invoice ${id}: HTTP ${response.status}`);
  }

  return response.json();
}

export async function updateInvoice(
  id: string,
  payload: {
    invoice_number?: string;
    invoice_date?: string;
    supplier_name?: string;
    customer_name?: string;
    subtotal?: number;
    tax?: number;
    total?: number;
    currency?: string;
    needs_manual_review?: boolean;
    reason: string;
    corrected_by?: string;
  }
): Promise<InvoiceDetail> {
  const response = await fetch(`${API_BASE_URL}/invoices/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Update invoice failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function updateLineItem(
  invoiceId: string,
  lineItemId: string,
  payload: {
    description?: string;
    quantity?: number;
    unit_price?: number;
    tax?: number;
    line_total?: number;
    reason: string;
    corrected_by?: string;
  }
): Promise<InvoiceLineItemDetail> {
  const response = await fetch(`${API_BASE_URL}/invoices/${invoiceId}/line-items/${lineItemId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Update line item failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function createLineItem(
  invoiceId: string,
  payload: {
    description: string;
    quantity?: number;
    unit_price?: number;
    tax?: number;
    line_total?: number;
    reason: string;
    corrected_by?: string;
  }
): Promise<InvoiceLineItemDetail> {
  const response = await fetch(`${API_BASE_URL}/invoices/${invoiceId}/line-items`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Create line item failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function deleteLineItem(
  invoiceId: string,
  lineItemId: string,
  reason: string,
  correctedBy?: string
): Promise<{ message: string; line_item_id: string; invoice_id: string }> {
  const searchParams = new URLSearchParams({ reason });
  if (correctedBy) searchParams.append('corrected_by', correctedBy);

  const url = `${API_BASE_URL}/invoices/${invoiceId}/line-items/${lineItemId}?${searchParams.toString()}`;
  const response = await fetch(url, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Delete line item failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchInvoiceCorrections(invoiceId: string): Promise<InvoiceCorrectionAudit[]> {
  const response = await fetch(`${API_BASE_URL}/invoices/${invoiceId}/corrections`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch corrections for invoice ${invoiceId}: HTTP ${response.status}`);
  }

  return response.json();
}

export async function triggerInvoiceExtraction(documentId: string): Promise<ExtractionInitiationResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}/extract-invoices`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Trigger extraction failed with HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchDocumentInvoices(
  documentId: string,
  extractionRunId?: string
): Promise<DocumentInvoicesResponse> {
  const url = extractionRunId
    ? `${API_BASE_URL}/documents/${documentId}/invoices?extraction_run_id=${extractionRunId}`
    : `${API_BASE_URL}/documents/${documentId}/invoices`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch document invoices: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchDocumentExtractionHistory(documentId: string): Promise<ExtractionHistoryResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}/extraction-history`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch extraction history: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchExtractionRun(runId: string): Promise<ExtractionRunItem> {
  const response = await fetch(`${API_BASE_URL}/extraction-runs/${runId}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch extraction run ${runId}: HTTP ${response.status}`);
  }

  return response.json();
}

export async function revalidateInvoice(invoiceId: string): Promise<ValidationSummaryResponse> {
  const response = await fetch(`${API_BASE_URL}/invoices/${invoiceId}/validate`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to revalidate invoice ${invoiceId}: HTTP ${response.status}`);
  }

  return response.json();
}

export async function revalidateDocumentInvoices(documentId: string): Promise<ValidationSummaryResponse[]> {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}/validate-invoices`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to revalidate document invoices: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchInvoiceValidationIssues(
  invoiceId: string,
  resolved?: boolean
): Promise<ValidationIssueDetail[]> {
  const query = resolved !== undefined ? `?resolved=${resolved}` : '';
  const response = await fetch(`${API_BASE_URL}/invoices/${invoiceId}/validation-issues${query}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch validation issues: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchInvoiceDuplicates(invoiceId: string): Promise<DuplicateMatchDetail[]> {
  const response = await fetch(`${API_BASE_URL}/invoices/${invoiceId}/duplicates`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch duplicate invoices: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchSystemValidationIssues(params?: {
  skip?: number;
  limit?: number;
  severity?: string;
  issue_type?: string;
  resolved?: boolean;
  invoice_id?: string;
}): Promise<ValidationIssueListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.skip !== undefined) searchParams.set('skip', params.skip.toString());
  if (params?.limit !== undefined) searchParams.set('limit', params.limit.toString());
  if (params?.severity) searchParams.set('severity', params.severity);
  if (params?.issue_type) searchParams.set('issue_type', params.issue_type);
  if (params?.resolved !== undefined) searchParams.set('resolved', params.resolved.toString());
  if (params?.invoice_id) searchParams.set('invoice_id', params.invoice_id);

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  const response = await fetch(`${API_BASE_URL}/validation-issues${query}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch validation issues list: HTTP ${response.status}`);
  }

  return response.json();
}

export async function resolveValidationIssue(
  issueId: string,
  payload: IssueResolvePayload
): Promise<ValidationIssueDetail> {
  const response = await fetch(`${API_BASE_URL}/validation-issues/${issueId}/resolve`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Failed to resolve validation issue ${issueId}: HTTP ${response.status}`);
  }

  return response.json();
}

export async function reopenValidationIssue(
  issueId: string,
  payload: IssueReopenPayload
): Promise<ValidationIssueDetail> {
  const response = await fetch(`${API_BASE_URL}/validation-issues/${issueId}/reopen`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Failed to reopen validation issue ${issueId}: HTTP ${response.status}`);
  }

  return response.json();
}

export interface SearchQueryParams {
  q?: string;
  mode?: SearchMode;
  page?: number;
  page_size?: number;
  document_id?: string;
  file_type?: string;
  supplier_name?: string;
  customer_name?: string;
  currency?: string;
  date_from?: string;
  date_to?: string;
  amount_min?: number;
  amount_max?: number;
  needs_review?: boolean;
  is_manually_corrected?: boolean;
  is_valid?: boolean;
  has_duplicates?: boolean;
}

export async function executeSearch(
  params: SearchQueryParams
): Promise<SearchResponse | InvoiceSearchResponse> {
  const query = new URLSearchParams();
  if (params.q !== undefined && params.q !== '') query.append('q', params.q);
  if (params.mode) query.append('mode', params.mode);
  if (params.page) query.append('page', params.page.toString());
  if (params.page_size) query.append('page_size', params.page_size.toString());
  if (params.document_id) query.append('document_id', params.document_id);
  if (params.file_type) query.append('file_type', params.file_type);
  if (params.supplier_name) query.append('supplier_name', params.supplier_name);
  if (params.customer_name) query.append('customer_name', params.customer_name);
  if (params.currency) query.append('currency', params.currency);
  if (params.date_from) query.append('date_from', params.date_from);
  if (params.date_to) query.append('date_to', params.date_to);
  if (params.amount_min !== undefined) query.append('amount_min', params.amount_min.toString());
  if (params.amount_max !== undefined) query.append('amount_max', params.amount_max.toString());
  if (params.needs_review !== undefined) query.append('needs_review', String(params.needs_review));
  if (params.is_manually_corrected !== undefined)
    query.append('is_manually_corrected', String(params.is_manually_corrected));
  if (params.is_valid !== undefined) query.append('is_valid', String(params.is_valid));
  if (params.has_duplicates !== undefined)
    query.append('has_duplicates', String(params.has_duplicates));

  const response = await fetch(`${API_BASE_URL}/search?${query.toString()}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.detail || `Search failed: HTTP ${response.status}`);
  }

  return response.json();
}

export async function executeInvoiceSearch(
  params: SearchQueryParams
): Promise<InvoiceSearchResponse> {
  const query = new URLSearchParams();
  if (params.q !== undefined && params.q !== '') query.append('q', params.q);
  if (params.page) query.append('page', params.page.toString());
  if (params.page_size) query.append('page_size', params.page_size.toString());
  if (params.document_id) query.append('document_id', params.document_id);
  if (params.supplier_name) query.append('supplier_name', params.supplier_name);
  if (params.customer_name) query.append('customer_name', params.customer_name);
  if (params.currency) query.append('currency', params.currency);
  if (params.date_from) query.append('date_from', params.date_from);
  if (params.date_to) query.append('date_to', params.date_to);
  if (params.amount_min !== undefined) query.append('amount_min', params.amount_min.toString());
  if (params.amount_max !== undefined) query.append('amount_max', params.amount_max.toString());
  if (params.needs_review !== undefined) query.append('needs_review', String(params.needs_review));
  if (params.is_manually_corrected !== undefined)
    query.append('is_manually_corrected', String(params.is_manually_corrected));
  if (params.is_valid !== undefined) query.append('is_valid', String(params.is_valid));
  if (params.has_duplicates !== undefined)
    query.append('has_duplicates', String(params.has_duplicates));

  const response = await fetch(`${API_BASE_URL}/search/invoices?${query.toString()}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.detail || `Invoice search failed: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchSearchCapabilities(): Promise<SearchCapabilitiesResponse> {
  const response = await fetch(`${API_BASE_URL}/search/capabilities`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch search capabilities: HTTP ${response.status}`);
  }

  return response.json();
}

export async function triggerEmbeddingBackfill(
  batchSize: number = 50
): Promise<EmbeddingBackfillResponse> {
  const response = await fetch(
    `${API_BASE_URL}/search/embeddings/backfill?batch_size=${batchSize}`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errBody = await response.json().catch(() => ({}));
    throw new Error(errBody.detail || `Backfill failed: HTTP ${response.status}`);
  }

  return response.json();
}



