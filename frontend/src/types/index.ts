export interface ServiceStatusMap {
  [service: string]: string;
}

export interface ProcessingCapabilities {
  pdf_digital_extraction: boolean;
  tesseract_available: boolean;
  tesseract_executable: string;
  tesseract_version: string;
  ocr_languages: string[];
  xlsx_processing: boolean;
  xls_processing: boolean;
  csv_processing: boolean;
  include_hidden_sheets: boolean;
  background_processing_mode: string;
  redis_connected: boolean;
  redis_status: string;
}

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  environment: string;
  timestamp: string;
  services: ServiceStatusMap;
  capabilities?: ProcessingCapabilities;
}

export interface ApiError {
  message: string;
  detail?: string;
}

export interface DocumentItem {
  id: string;
  original_filename: string;
  stored_filename: string;
  file_type: string;
  mime_type: string;
  file_size: number;
  sha256_hash: string;
  status: 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed' | 'needs_review' | string;
  page_count?: number | null;
  sheet_count?: number | null;
  total_chunks?: number;
  extracted_characters?: number;
  extraction_method_summary?: string | null;
  uploaded_at: string;
  processed_at?: string | null;
  error_message?: string | null;
}

export interface RejectedDocument {
  filename: string;
  error: string;
  reason: string;
}

export interface UploadBatchResponse {
  accepted: DocumentItem[];
  rejected: RejectedDocument[];
  total_accepted: number;
  total_rejected: number;
}

export interface DocumentListResponse {
  items: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ProcessingEvent {
  id: string;
  event_type: string;
  message: string;
  created_at: string;
}

export interface DocumentChunk {
  id: string;
  document_id: string;
  chunk_index: number;
  source_type: 'PDF_PAGE' | 'IMAGE' | 'TIFF_PAGE' | 'SPREADSHEET_SHEET' | 'CSV' | string;
  page_number?: number | null;
  sheet_name?: string | null;
  row_start?: number | null;
  row_end?: number | null;
  content: string;
  extraction_method: string;
  ocr_confidence?: number | null;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface DocumentChunkListResponse {
  items: DocumentChunk[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ProcessingSummaryResponse {
  document_id: string;
  status: string;
  file_type: string;
  page_count?: number | null;
  sheet_count?: number | null;
  total_chunks: number;
  extracted_characters: number;
  extraction_method_summary?: string | null;
  error_message?: string | null;
  uploaded_at: string;
  processed_at?: string | null;
  processing_events: ProcessingEvent[];
}

export interface DocumentDetail extends DocumentItem {
  processing_events: ProcessingEvent[];
  invoice?: {
    id: string;
    invoice_number?: string | null;
    invoice_date?: string | null;
    supplier_name?: string | null;
    customer_name?: string | null;
    subtotal?: number | null;
    tax?: number | null;
    total?: number | null;
    currency?: string | null;
    line_items?: Array<{
      id: string;
      description: string;
      quantity?: number | null;
      unit_price?: number | null;
      line_total?: number | null;
    }>;
    validation_issues?: Array<{
      id: string;
      field_name: string;
      severity: string;
      description: string;
    }>;
  } | null;
}

export interface InvoiceLineItemDetail {
  id: string;
  invoice_id: string;
  description: string;
  quantity?: number | null;
  unit_price?: number | null;
  tax?: number | null;
  line_total?: number | null;
  field_evidence?: Record<string, any> | null;
  field_confidence?: Record<string, any> | null;
  created_at: string;
}

export interface ValidationIssueDetail {
  id: string;
  invoice_id: string;
  line_item_id?: string | null;
  field_name: string;
  issue_type: string;
  severity: string;
  description: string;
  expected_value?: string | null;
  observed_value?: string | null;
  resolved: boolean;
  resolved_at?: string | null;
  resolved_by?: string | null;
  resolution_notes?: string | null;
  related_invoice_id?: string | null;
  related_document_id?: string | null;
  created_at: string;
}

export interface DuplicateMatchDetail {
  invoice_id: string;
  document_id: string;
  invoice_number?: string | null;
  supplier_name?: string | null;
  invoice_date?: string | null;
  total?: number | null;
  currency?: string | null;
  match_type: 'exact_duplicate' | 'likely_duplicate' | string;
  match_reasons: string[];
}

export interface ValidationSummaryResponse {
  invoice_id: string;
  total_issues: number;
  unresolved_errors: number;
  unresolved_warnings: number;
  unresolved_info: number;
  resolved_issues: number;
  needs_manual_review: boolean;
  is_valid: boolean;
  issues: ValidationIssueDetail[];
  duplicates_detected: DuplicateMatchDetail[];
}

export interface ValidationIssueListResponse {
  total: number;
  skip: number;
  limit: number;
  items: ValidationIssueDetail[];
}

export interface IssueResolvePayload {
  resolved_by?: string;
  resolution_notes?: string;
}

export interface IssueReopenPayload {
  reopened_by?: string;
  reopen_notes?: string;
}

export interface InvoiceDetail {
  id: string;
  document_id: string;
  extraction_run_id?: string | null;
  source_context_id?: string | null;
  invoice_number?: string | null;
  invoice_date?: string | null;
  supplier_name?: string | null;
  customer_name?: string | null;
  subtotal?: number | null;
  tax?: number | null;
  total?: number | null;
  currency?: string | null;
  extraction_method?: string | null;
  field_evidence?: Record<string, any> | null;
  field_confidence?: Record<string, any> | null;
  extraction_metadata?: Record<string, any> | null;
  needs_manual_review: boolean;
  is_manually_corrected: boolean;
  document_page_start?: number | null;
  document_page_end?: number | null;
  created_at: string;
  updated_at: string;
  line_items: InvoiceLineItemDetail[];
  validation_issues: ValidationIssueDetail[];
}

export interface InvoiceListResponse {
  total: number;
  skip: number;
  limit: number;
  items: InvoiceDetail[];
}

export interface InvoiceCorrectionAudit {
  id: string;
  invoice_id: string;
  correction_type: string;
  changed_fields: string[];
  previous_values: Record<string, any>;
  new_values: Record<string, any>;
  reason?: string | null;
  corrected_by?: string | null;
  corrected_at: string;
}

export interface ExtractionRunItem {
  id: string;
  document_id: string;
  provider: string;
  model_name: string;
  prompt_version: string;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  processing_time_ms?: number | null;
  input_token_count?: number | null;
  output_token_count?: number | null;
  total_contexts: number;
  successful_contexts: number;
  skipped_contexts: number;
  failed_contexts: number;
  error_message?: string | null;
  created_at: string;
}

export interface DashboardMetrics {
  total_documents: number;
  processed_documents: number;
  processing_documents: number;
  failed_documents: number;
  total_invoices: number;
  needs_review_invoices: number;
  manually_corrected_invoices: number;
  recent_extraction_runs: ExtractionRunItem[];
  recent_corrections: InvoiceCorrectionAudit[];
}

export interface ExtractionInitiationResponse {
  extraction_run_id: string;
  document_id: string;
  status: string;
  processing_mode: string;
  message: string;
}

export interface DocumentInvoicesResponse {
  document_id: string;
  extraction_run_id?: string | null;
  total_invoices: number;
  invoices: InvoiceDetail[];
}

export interface ExtractionHistoryResponse {
  document_id: string;
  total_runs: number;
  runs: ExtractionRunItem[];
}

export type SearchMode = 'hybrid' | 'keyword' | 'semantic' | 'invoice';

export interface SearchResultItem {
  chunk_id?: string | null;
  document_id: string;
  document_filename: string;
  file_type: string;
  chunk_index?: number | null;
  source_type?: string | null;
  page_number?: number | null;
  sheet_name?: string | null;
  row_start?: number | null;
  row_end?: number | null;
  content: string;
  highlighted_snippet: string;
  score: number;
  match_type: string;
  keyword_rank?: number | null;
  semantic_rank?: number | null;
  invoice_id?: string | null;
  invoice_number?: string | null;
  supplier_name?: string | null;
  invoice_total?: number | null;
  currency?: string | null;
  invoice_date?: string | null;
  needs_manual_review?: boolean | null;
}

export interface SearchResponse {
  query: string;
  mode: string;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: SearchResultItem[];
  fallback_mode: boolean;
  fallback_reason?: string | null;
  execution_time_ms: number;
}

export interface InvoiceSearchResultItem {
  invoice_id: string;
  document_id: string;
  document_filename: string;
  invoice_number?: string | null;
  invoice_date?: string | null;
  supplier_name?: string | null;
  customer_name?: string | null;
  subtotal?: number | null;
  tax?: number | null;
  total?: number | null;
  currency?: string | null;
  needs_manual_review: boolean;
  is_manually_corrected: boolean;
  is_valid: boolean;
  has_duplicates: boolean;
  unresolved_issue_count: number;
  line_items_count: number;
  matched_fields: string[];
  highlighted_snippet?: string | null;
  created_at: string;
}

export interface InvoiceSearchResponse {
  query?: string | null;
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  items: InvoiceSearchResultItem[];
  execution_time_ms: number;
}

export interface SearchCapabilitiesResponse {
  keyword_search_available: boolean;
  semantic_search_available: boolean;
  hybrid_search_available: boolean;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimension: number;
  total_chunks: number;
  embedded_chunks: number;
  unembedded_chunks: number;
  status_message: string;
}

export interface EmbeddingBackfillResponse {
  total_chunks_processed: number;
  embedded_count: number;
  skipped_count: number;
  failed_count: number;
  status: string;
  message: string;
}


