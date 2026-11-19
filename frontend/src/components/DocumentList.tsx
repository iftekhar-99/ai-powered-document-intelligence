import React, { useState } from 'react';
import { DocumentItem } from '../types';
import {
  FileText,
  Search,
  Trash2,
  Eye,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Clock,
  Layers,
  Play,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  ExternalLink,
} from 'lucide-react';
import { getDocumentFileUrl } from '../services/api';

interface DocumentListProps {
  documents: DocumentItem[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  loading: boolean;
  onPageChange: (newPage: number) => void;
  onFilterChange: (filters: { status?: string; fileType?: string; search?: string }) => void;
  onViewDetails: (doc: DocumentItem) => void;
  onDeleteDocument: (id: string) => void;
  onRefresh: () => void;
  onTriggerProcess?: (id: string) => Promise<void>;
  onExtractInvoices?: (doc: DocumentItem) => void;
}

export const DocumentList: React.FC<DocumentListProps> = ({
  documents,
  total,
  page,
  pageSize: _pageSize,
  totalPages,
  loading,
  onPageChange,
  onFilterChange,
  onViewDetails,
  onDeleteDocument,
  onRefresh,
  onTriggerProcess,
  onExtractInvoices,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [fileTypeFilter, setFileTypeFilter] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onFilterChange({
      search: searchTerm.trim() || undefined,
      status: statusFilter || undefined,
      fileType: fileTypeFilter || undefined,
    });
  };

  const handleStatusSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setStatusFilter(val);
    onFilterChange({
      search: searchTerm.trim() || undefined,
      status: val || undefined,
      fileType: fileTypeFilter || undefined,
    });
  };

  const handleFileTypeSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    setFileTypeFilter(val);
    onFilterChange({
      search: searchTerm.trim() || undefined,
      status: statusFilter || undefined,
      fileType: val || undefined,
    });
  };

  const handleProcessClick = async (doc: DocumentItem) => {
    if (!onTriggerProcess) return;
    setProcessingId(doc.id);
    try {
      await onTriggerProcess(doc.id);
    } finally {
      setProcessingId(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-600" />
            Completed
          </span>
        );
      case 'processing':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-sky-100 text-sky-800 border border-sky-200 animate-pulse">
            <RefreshCw className="w-3 h-3 mr-1 text-sky-600 animate-spin" />
            Processing
          </span>
        );
      case 'queued':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
            <Clock className="w-3 h-3 mr-1 text-amber-600" />
            Queued
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-200">
            <AlertTriangle className="w-3 h-3 mr-1 text-rose-600" />
            Failed
          </span>
        );
      case 'needs_review':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-200">
            <AlertTriangle className="w-3 h-3 mr-1 text-purple-600" />
            Needs Review
          </span>
        );
      case 'uploaded':
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
            Uploaded
          </span>
        );
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const handleDeleteClick = async (doc: DocumentItem) => {
    if (window.confirm(`Are you sure you want to delete '${doc.original_filename}'? This will permanently remove the file, chunks and associated records.`)) {
      setDeletingId(doc.id);
      try {
        await onDeleteDocument(doc.id);
      } finally {
        setDeletingId(null);
      }
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden space-y-4 p-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            <Layers className="w-5 h-5 text-sky-600" />
            Document Repository ({total})
          </h2>
          <p className="text-xs text-slate-500">
            Browse and manage all uploaded financial documents, inspect OCR extraction and chunk data
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex items-center px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition disabled:opacity-50 self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 text-xs">
        <form onSubmit={handleSearchSubmit} className="sm:col-span-6 relative">
          <input
            type="text"
            placeholder="Search by filename..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-transparent text-xs"
          />
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
        </form>

        <div className="sm:col-span-3">
          <select
            value={statusFilter}
            onChange={handleStatusSelect}
            className="w-full py-2 px-3 border border-slate-300 rounded-lg text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500 text-xs bg-white"
          >
            <option value="">All Statuses</option>
            <option value="uploaded">Uploaded</option>
            <option value="queued">Queued</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="needs_review">Needs Review</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        <div className="sm:col-span-3">
          <select
            value={fileTypeFilter}
            onChange={handleFileTypeSelect}
            className="w-full py-2 px-3 border border-slate-300 rounded-lg text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500 text-xs bg-white"
          >
            <option value="">All File Types</option>
            <option value="pdf">PDF</option>
            <option value="png">PNG</option>
            <option value="jpg">JPG</option>
            <option value="tiff">TIFF</option>
            <option value="xlsx">XLSX</option>
            <option value="xls">XLS</option>
            <option value="csv">CSV</option>
          </select>
        </div>
      </div>

      {/* Table Container */}
      <div className="overflow-x-auto border border-slate-200 rounded-lg">
        <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
          <thead className="bg-slate-50 text-slate-500 font-semibold uppercase tracking-wider">
            <tr>
              <th scope="col" className="px-4 py-3">Document</th>
              <th scope="col" className="px-3 py-3">Type / Size</th>
              <th scope="col" className="px-3 py-3">Status</th>
              <th scope="col" className="px-3 py-3">Extraction Summary</th>
              <th scope="col" className="px-3 py-3">Uploaded</th>
              <th scope="col" className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {loading && documents.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto text-sky-500 mb-2" />
                  Loading document records...
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500">
                  <FileText className="w-8 h-8 mx-auto text-slate-300 mb-2" />
                  No documents found matching the filter criteria.
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50/70 transition">
                  {/* Document Name */}
                  <td className="px-4 py-3 font-medium text-slate-900 max-w-xs">
                    <div className="flex items-center space-x-2">
                      <FileText className="w-4 h-4 text-slate-400 flex-shrink-0" />
                      <div className="truncate">
                        <span className="truncate block font-semibold" title={doc.original_filename}>
                          {doc.original_filename}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono truncate block">
                          {doc.stored_filename}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Type / Size */}
                  <td className="px-3 py-3">
                    <div className="space-y-0.5">
                      <span className="inline-block px-1.5 py-0.5 font-mono text-[11px] rounded bg-slate-100 text-slate-700 uppercase font-semibold">
                        {doc.file_type}
                      </span>
                      <div className="font-mono text-[11px] text-slate-500">
                        {formatFileSize(doc.file_size)}
                      </div>
                    </div>
                  </td>

                  {/* Status */}
                  <td className="px-3 py-3">
                    {getStatusBadge(doc.status)}
                    {doc.error_message && (
                      <span
                        className="block text-[10px] text-rose-500 truncate max-w-[140px] mt-0.5"
                        title={doc.error_message}
                      >
                        {doc.error_message}
                      </span>
                    )}
                  </td>

                  {/* Extraction Summary */}
                  <td className="px-3 py-3">
                    {doc.total_chunks && doc.total_chunks > 0 ? (
                      <div className="space-y-1">
                        <div className="text-[11px] font-semibold text-slate-800">
                          {doc.total_chunks} chunks
                          {doc.page_count ? ` • ${doc.page_count} pages` : ''}
                          {doc.sheet_count ? ` • ${doc.sheet_count} sheets` : ''}
                        </div>
                        <div className="text-[10px] text-slate-500 flex items-center gap-1">
                          <span>{(doc.extracted_characters || 0).toLocaleString()} chars</span>
                          {doc.extraction_method_summary && (
                            <span className="px-1.5 py-0.2 rounded bg-sky-50 text-sky-700 font-mono text-[9px] border border-sky-100">
                              {doc.extraction_method_summary}
                            </span>
                          )}
                        </div>
                      </div>
                    ) : (
                      <span className="text-slate-400 text-[11px] italic">Not processed yet</span>
                    )}
                  </td>

                  {/* Uploaded */}
                  <td className="px-3 py-3 text-slate-500 whitespace-nowrap">
                    <div className="flex items-center space-x-1 text-[11px]">
                      <Clock className="w-3.5 h-3.5 text-slate-400" />
                      <span>
                        {new Date(doc.uploaded_at).toLocaleDateString()}{' '}
                        {new Date(doc.uploaded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </td>

                  {/* Actions */}
                  <td className="px-4 py-3 text-right space-x-1 whitespace-nowrap">
                    {/* Extract Invoices AI Button */}
                    <button
                      onClick={() => onExtractInvoices?.(doc)}
                      disabled={!doc.total_chunks || doc.total_chunks === 0}
                      className="inline-flex items-center p-1.5 text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 rounded-md transition disabled:opacity-30"
                      title={doc.total_chunks && doc.total_chunks > 0 ? 'Extract Invoices with Gemini AI' : 'Process document first to extract chunks'}
                    >
                      <Cpu className="w-4 h-4" />
                    </button>

                    {/* View Raw Document File */}
                    <a
                      href={getDocumentFileUrl(doc.id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-md transition"
                      title="View/Download Raw Document File"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>

                    {/* Process / Reprocess Button */}
                    <button
                      onClick={() => handleProcessClick(doc)}
                      disabled={processingId === doc.id || doc.status === 'processing'}
                      className="inline-flex items-center p-1.5 text-slate-600 hover:text-emerald-700 hover:bg-emerald-50 rounded-md transition disabled:opacity-40"
                      title={doc.status === 'completed' || doc.status === 'needs_review' ? 'Reprocess document' : 'Process document'}
                    >
                      {processingId === doc.id || doc.status === 'processing' ? (
                        <RefreshCw className="w-4 h-4 animate-spin text-emerald-600" />
                      ) : (
                        <Play className="w-4 h-4" />
                      )}
                    </button>

                    {/* View Details Modal Button */}
                    <button
                      onClick={() => onViewDetails(doc)}
                      className="inline-flex items-center p-1.5 text-slate-500 hover:text-sky-600 hover:bg-sky-50 rounded-md transition"
                      title="Inspect Chunks and Details"
                    >
                      <Eye className="w-4 h-4" />
                    </button>

                    {/* Delete Button */}
                    <button
                      onClick={() => handleDeleteClick(doc)}
                      disabled={deletingId === doc.id}
                      className="inline-flex items-center p-1.5 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-md transition disabled:opacity-50"
                      title="Delete document"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-600 pt-2 border-t border-slate-100">
          <div>
            Showing page <span className="font-semibold text-slate-900">{page}</span> of{' '}
            <span className="font-semibold text-slate-900">{totalPages}</span> ({total} items)
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              className="p-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-2 font-mono font-medium">{page}</span>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              className="p-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
