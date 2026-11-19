import React, { useEffect, useState, useCallback } from 'react';
import {
  DocumentChunk,
  DocumentDetail,
  DocumentItem,
  ProcessingSummaryResponse,
} from '../types';
import {
  fetchDocumentChunks,
  fetchDocumentDetails,
  triggerProcessing,
} from '../services/api';
import {
  X,
  FileText,
  Hash,
  HardDrive,
  Activity,
  AlertCircle,
  RefreshCw,
  Layers,
  Play,
  CheckCircle2,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Filter,
} from 'lucide-react';

interface DocumentDetailModalProps {
  document: DocumentItem | null;
  onClose: () => void;
  onProcessingComplete?: () => void;
}

export const DocumentDetailModal: React.FC<DocumentDetailModalProps> = ({
  document,
  onClose,
  onProcessingComplete,
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'chunks'>('overview');
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Processing trigger state
  const [isProcessing, setIsProcessing] = useState(false);
  const [processSuccessMsg, setProcessSuccessMsg] = useState<string | null>(null);

  // Chunks state
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [chunkPage, setChunkPage] = useState(1);
  const [chunkTotalPages, setChunkTotalPages] = useState(1);
  const [chunkTotalCount, setChunkTotalCount] = useState(0);
  const [chunkSourceType, setChunkSourceType] = useState<string>('');
  const [expandedChunkIndex, setExpandedChunkIndex] = useState<number | null>(null);

  const loadDocumentDetails = useCallback(async (docId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDocumentDetails(docId);
      setDetail(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to load document details.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const loadChunks = useCallback(async (docId: string, pageNum: number, sourceType?: string) => {
    setChunksLoading(true);
    try {
      const data = await fetchDocumentChunks(docId, {
        page: pageNum,
        page_size: 10,
        source_type: sourceType || undefined,
      });
      setChunks(data.items);
      setChunkTotalCount(data.total);
      setChunkTotalPages(data.total_pages);
    } catch (err: unknown) {
      console.error('Failed to load chunks:', err);
    } finally {
      setChunksLoading(false);
    }
  }, []);

  useEffect(() => {
    if (document) {
      loadDocumentDetails(document.id);
      loadChunks(document.id, 1);
      setChunkPage(1);
      setChunkSourceType('');
      setProcessSuccessMsg(null);
    } else {
      setDetail(null);
      setChunks([]);
    }
  }, [document, loadDocumentDetails, loadChunks]);

  const handleTriggerProcess = async () => {
    if (!document) return;
    setIsProcessing(true);
    setError(null);
    setProcessSuccessMsg(null);
    try {
      const summary: ProcessingSummaryResponse = await triggerProcessing(document.id);
      setProcessSuccessMsg(
        `Processing completed: ${summary.total_chunks} chunks extracted (${summary.extracted_characters.toLocaleString()} characters).`
      );
      // Reload both details and chunks
      await loadDocumentDetails(document.id);
      await loadChunks(document.id, 1, chunkSourceType);
      if (onProcessingComplete) {
        onProcessingComplete();
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Document processing failed.');
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSourceTypeFilter = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setChunkSourceType(val);
    setChunkPage(1);
    if (document) {
      loadChunks(document.id, 1, val);
    }
  };

  const handleChunkPageChange = (newPage: number) => {
    setChunkPage(newPage);
    if (document) {
      loadChunks(document.id, newPage, chunkSourceType);
    }
  };

  if (!document) return null;

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const getMethodBadge = (method: string) => {
    switch (method.toUpperCase()) {
      case 'DIGITAL_TEXT':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-100 text-sky-800 border border-sky-200">
            DIGITAL_TEXT
          </span>
        );
      case 'OCR':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-800 border border-purple-200">
            OCR
          </span>
        );
      case 'TABULAR_PARSER':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            TABULAR_PARSER
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            {method}
          </span>
        );
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in duration-150">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-100 bg-slate-50">
          <div className="flex items-center space-x-3 truncate">
            <div className="p-2.5 bg-sky-100 text-sky-600 rounded-xl flex-shrink-0">
              <FileText className="w-5 h-5" />
            </div>
            <div className="truncate">
              <h3 className="text-sm font-bold text-slate-900 truncate flex items-center gap-2">
                {document.original_filename}
                <span className="text-[10px] font-mono px-2 py-0.5 rounded uppercase font-semibold bg-slate-200 text-slate-700">
                  {document.file_type}
                </span>
              </h3>
              <p className="text-xs text-slate-400 font-mono">ID: {document.id}</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={handleTriggerProcess}
              disabled={isProcessing}
              className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 hover:bg-sky-700 rounded-lg shadow-sm transition disabled:opacity-50"
              title="Process or reprocess document"
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 mr-1.5" />
                  {detail?.status === 'completed' || detail?.status === 'needs_review'
                    ? 'Reprocess'
                    : 'Process'}
                </>
              )}
            </button>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-200/50 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-200 bg-white px-6 pt-2">
          <button
            onClick={() => setActiveTab('overview')}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'overview'
                ? 'border-sky-600 text-sky-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Activity className="w-4 h-4" />
            Overview & Events
          </button>
          <button
            onClick={() => setActiveTab('chunks')}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'chunks'
                ? 'border-sky-600 text-sky-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Layers className="w-4 h-4" />
            Extracted Chunks ({chunkTotalCount})
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-xs text-slate-700 flex-1">
          {processSuccessMsg && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-600" />
              <span>{processSuccessMsg}</span>
            </div>
          )}

          {error && (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {detail?.error_message && (
            <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg text-purple-800 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 text-purple-600 mt-0.5" />
              <div>
                <span className="font-semibold block">Processing Notes / Warnings:</span>
                <span className="text-[11px]">{detail.error_message}</span>
              </div>
            </div>
          )}

          {activeTab === 'overview' && (
            <>
              {loading && (
                <div className="py-12 text-center text-slate-500">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto text-sky-500 mb-2" />
                  Loading document metadata...
                </div>
              )}

              {detail && !loading && (
                <>
                  {/* Extraction Metrics Card */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase block">Status</span>
                      <span className="text-xs font-bold text-slate-900 uppercase">
                        {detail.status}
                      </span>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase block">Total Chunks</span>
                      <span className="text-xs font-bold text-slate-900">
                        {detail.total_chunks ?? 0}
                      </span>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase block">Characters</span>
                      <span className="text-xs font-bold text-slate-900">
                        {(detail.extracted_characters ?? 0).toLocaleString()}
                      </span>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase block">Methods</span>
                      <span className="text-xs font-bold text-slate-900 truncate block" title={detail.extraction_method_summary || 'None'}>
                        {detail.extraction_method_summary || 'N/A'}
                      </span>
                    </div>
                  </div>

                  {/* Hashes & File Info */}
                  <div className="space-y-2 border border-slate-200 rounded-lg p-3.5 bg-slate-50/50">
                    <div className="flex items-start gap-2">
                      <Hash className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
                      <div className="overflow-hidden">
                        <span className="font-semibold text-slate-600 block">SHA-256 Checksum</span>
                        <span className="font-mono text-[11px] text-slate-800 break-all select-all">
                          {detail.sha256_hash}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-start gap-2 pt-2 border-t border-slate-200/60">
                      <HardDrive className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />
                      <div className="overflow-hidden">
                        <span className="font-semibold text-slate-600 block">Stored Internal Filename</span>
                        <span className="font-mono text-[11px] text-slate-800">
                          {detail.stored_filename} ({formatFileSize(detail.file_size)})
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Processing Events Audit Log */}
                  <div className="space-y-2.5">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                      <Activity className="w-4 h-4 text-sky-600" />
                      Audit Trail & Processing Timeline ({detail.processing_events.length})
                    </h4>

                    {detail.processing_events.length === 0 ? (
                      <p className="text-slate-400 italic">No events recorded for this document yet.</p>
                    ) : (
                      <div className="border border-slate-200 rounded-lg divide-y divide-slate-100 max-h-56 overflow-y-auto">
                        {detail.processing_events.map((ev) => (
                          <div key={ev.id} className="p-3 space-y-1 bg-white hover:bg-slate-50/50 transition">
                            <div className="flex items-center justify-between text-[11px]">
                              <span className="font-semibold text-slate-800 uppercase px-1.5 py-0.5 bg-slate-100 rounded">
                                {ev.event_type}
                              </span>
                              <span className="text-slate-400 font-mono">
                                {new Date(ev.created_at).toLocaleString()}
                              </span>
                            </div>
                            <p className="text-slate-600">{ev.message}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          )}

          {activeTab === 'chunks' && (
            <div className="space-y-4">
              {/* Chunk Filters */}
              <div className="flex items-center justify-between gap-3 pb-2 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Filter className="w-4 h-4 text-slate-400" />
                  <span className="font-semibold text-slate-700">Filter by Source Type:</span>
                  <select
                    value={chunkSourceType}
                    onChange={handleSourceTypeFilter}
                    className="py-1 px-2 border border-slate-300 rounded text-xs text-slate-700 bg-white"
                  >
                    <option value="">All Sources</option>
                    <option value="PDF_PAGE">PDF Pages</option>
                    <option value="IMAGE">Images</option>
                    <option value="TIFF_PAGE">TIFF Pages</option>
                    <option value="SPREADSHEET_SHEET">Spreadsheets</option>
                    <option value="CSV">CSV</option>
                  </select>
                </div>
                <div className="text-slate-500 text-[11px]">
                  Total chunks: <span className="font-semibold text-slate-800">{chunkTotalCount}</span>
                </div>
              </div>

              {chunksLoading && (
                <div className="py-12 text-center text-slate-500">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto text-sky-500 mb-2" />
                  Loading document chunks...
                </div>
              )}

              {!chunksLoading && chunks.length === 0 && (
                <div className="py-12 text-center text-slate-400 space-y-2">
                  <Layers className="w-8 h-8 mx-auto text-slate-300" />
                  <p>No chunks found for this document.</p>
                  <button
                    onClick={handleTriggerProcess}
                    disabled={isProcessing}
                    className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-white bg-sky-600 rounded-lg hover:bg-sky-700 transition"
                  >
                    <Play className="w-3.5 h-3.5 mr-1.5" />
                    Trigger Processing Now
                  </button>
                </div>
              )}

              {!chunksLoading && chunks.length > 0 && (
                <div className="space-y-3">
                  {chunks.map((chk) => {
                    const isExpanded = expandedChunkIndex === chk.chunk_index;
                    return (
                      <div
                        key={chk.id}
                        className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-xs hover:border-slate-300 transition"
                      >
                        {/* Chunk Header */}
                        <div
                          onClick={() =>
                            setExpandedChunkIndex(isExpanded ? null : chk.chunk_index)
                          }
                          className="p-3 bg-slate-50 flex items-center justify-between cursor-pointer select-none"
                        >
                          <div className="flex items-center space-x-2">
                            <span className="font-mono font-bold text-slate-800 text-xs px-2 py-0.5 bg-white border border-slate-200 rounded">
                              #{chk.chunk_index}
                            </span>
                            <span className="font-mono text-[11px] text-slate-600 px-2 py-0.5 bg-slate-100 rounded">
                              {chk.source_type}
                              {chk.page_number ? ` (p. ${chk.page_number})` : ''}
                              {chk.sheet_name ? ` (sheet: ${chk.sheet_name})` : ''}
                              {chk.row_start !== null && chk.row_end !== null
                                ? ` [rows ${chk.row_start}-${chk.row_end}]`
                                : ''}
                            </span>
                            {getMethodBadge(chk.extraction_method)}
                            {chk.ocr_confidence !== null && chk.ocr_confidence !== undefined && (
                              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-50 text-purple-700 border border-purple-100">
                                OCR Conf: {chk.ocr_confidence.toFixed(1)}%
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-500 flex items-center gap-3">
                            <span>{chk.content.length.toLocaleString()} chars</span>
                            <span className="text-sky-600 font-semibold hover:underline">
                              {isExpanded ? 'Collapse' : 'Expand'}
                            </span>
                          </div>
                        </div>

                        {/* Chunk Content Preview */}
                        <div className="p-4">
                          <pre
                            className={`font-mono text-xs text-slate-800 bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap leading-relaxed ${
                              isExpanded ? 'max-h-96' : 'max-h-32'
                            }`}
                          >
                            {chk.content}
                          </pre>
                        </div>
                      </div>
                    );
                  })}

                  {/* Chunk Pagination Controls */}
                  {chunkTotalPages > 1 && (
                    <div className="flex items-center justify-between text-xs text-slate-600 pt-3 border-t border-slate-100">
                      <div>
                        Page <span className="font-semibold text-slate-900">{chunkPage}</span> of{' '}
                        <span className="font-semibold text-slate-900">{chunkTotalPages}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleChunkPageChange(chunkPage - 1)}
                          disabled={chunkPage <= 1}
                          className="p-1 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40"
                        >
                          <ChevronLeft className="w-4 h-4" />
                        </button>
                        <span className="px-2 font-mono font-medium">{chunkPage}</span>
                        <button
                          onClick={() => handleChunkPageChange(chunkPage + 1)}
                          disabled={chunkPage >= chunkTotalPages}
                          className="p-1 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40"
                        >
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
          <div className="text-[11px] text-slate-500">
            {detail?.processed_at ? (
              <span>Last processed: {new Date(detail.processed_at).toLocaleString()}</span>
            ) : (
              <span>Not yet processed</span>
            )}
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
