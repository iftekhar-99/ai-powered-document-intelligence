import React, { useState, useEffect, useCallback } from 'react';
import {
  Search,
  Sparkles,
  FileText,
  RefreshCw,
  AlertCircle,
  ArrowRight,
  Receipt,
  CheckCircle,
  X,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
} from 'lucide-react';
import {
  executeSearch,
  executeInvoiceSearch,
  fetchSearchCapabilities,
  triggerEmbeddingBackfill,
} from '../services/api';
import {
  InvoiceSearchResponse,
  SearchCapabilitiesResponse,
  SearchMode,
  SearchResponse,
} from '../types';

interface SearchPageProps {
  onViewDocument?: (documentId: string) => void;
  onViewInvoice?: (invoiceId: string) => void;
}

export const SearchPage: React.FC<SearchPageProps> = ({
  onViewDocument,
  onViewInvoice,
}) => {
  // Query & Mode state
  const [query, setQuery] = useState<string>('');
  const [searchMode, setSearchMode] = useState<SearchMode>('hybrid');
  const [page, setPage] = useState<number>(1);
  const pageSize = 15;

  // Filters
  const [showFilters, setShowFilters] = useState<boolean>(false);
  const [fileType, setFileType] = useState<string>('');
  const [currency, setCurrency] = useState<string>('');
  const [supplierName, setSupplierName] = useState<string>('');
  const [customerName, setCustomerName] = useState<string>('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [amountMin, setAmountMin] = useState<string>('');
  const [amountMax, setAmountMax] = useState<string>('');
  const [needsReview, setNeedsReview] = useState<boolean | undefined>(undefined);
  const [isValid, setIsValid] = useState<boolean | undefined>(undefined);

  // Search Results state
  const [loading, setLoading] = useState<boolean>(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [chunkResponse, setChunkResponse] = useState<SearchResponse | null>(null);
  const [invoiceResponse, setInvoiceResponse] = useState<InvoiceSearchResponse | null>(null);

  // System capabilities & backfill
  const [capabilities, setCapabilities] = useState<SearchCapabilitiesResponse | null>(null);
  const [backfilling, setBackfilling] = useState<boolean>(false);
  const [backfillMessage, setBackfillMessage] = useState<string | null>(null);

  const loadCapabilities = useCallback(async () => {
    try {
      const caps = await fetchSearchCapabilities();
      setCapabilities(caps);
    } catch {
      // capabilities failed silently
    }
  }, []);


  useEffect(() => {
    loadCapabilities();
  }, [loadCapabilities]);

  const handleSearch = useCallback(
    async (targetPage: number = 1) => {
      setLoading(true);
      setSearchError(null);
      setPage(targetPage);

      const parsedMin = amountMin ? parseFloat(amountMin) : undefined;
      const parsedMax = amountMax ? parseFloat(amountMax) : undefined;

      try {
        if (searchMode === 'invoice') {
          const res = await executeInvoiceSearch({
            q: query,
            page: targetPage,
            page_size: pageSize,
            supplier_name: supplierName || undefined,
            customer_name: customerName || undefined,
            currency: currency || undefined,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            amount_min: parsedMin,
            amount_max: parsedMax,
            needs_review: needsReview,
            is_valid: isValid,
          });
          setInvoiceResponse(res);
          setChunkResponse(null);
        } else {
          const res = (await executeSearch({
            q: query,
            mode: searchMode,
            page: targetPage,
            page_size: pageSize,
            file_type: fileType || undefined,
            supplier_name: supplierName || undefined,
            customer_name: customerName || undefined,
            currency: currency || undefined,
            date_from: dateFrom || undefined,
            date_to: dateTo || undefined,
            amount_min: parsedMin,
            amount_max: parsedMax,
            needs_review: needsReview,
            is_valid: isValid,
          })) as SearchResponse;

          setChunkResponse(res);
          setInvoiceResponse(null);
        }
      } catch (err: unknown) {
        if (err instanceof Error) {
          setSearchError(err.message);
        } else {
          setSearchError('An unexpected search error occurred.');
        }
      } finally {
        setLoading(false);
      }
    },
    [
      query,
      searchMode,
      pageSize,
      fileType,
      supplierName,
      customerName,
      currency,
      dateFrom,
      dateTo,
      amountMin,
      amountMax,
      needsReview,
      isValid,
    ]
  );

  // Trigger search on mode switch or page switch
  const handleModeChange = (newMode: SearchMode) => {
    setSearchMode(newMode);
    setPage(1);
  };

  const handleBackfill = async () => {
    setBackfilling(true);
    setBackfillMessage(null);
    try {
      const res = await triggerEmbeddingBackfill(100);
      setBackfillMessage(res.message);
      await loadCapabilities();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setBackfillMessage(`Backfill failed: ${err.message}`);
      }
    } finally {
      setBackfilling(false);
    }
  };

  const renderHighlightedSnippet = (snippet: string) => {
    if (!snippet) return null;
    // Replace markdown bold **term** with highlighted span
    const parts = snippet.split(/(\*\*.*?\*\*)/g);
    return (
      <span>
        {parts.map((part, index) => {
          if (part.startsWith('**') && part.endsWith('**')) {
            const clean = part.slice(2, -2);
            return (
              <mark
                key={index}
                className="bg-amber-100 text-amber-950 font-semibold px-1 py-0.5 rounded"
              >
                {clean}
              </mark>
            );
          }
          return <span key={index}>{part}</span>;
        })}
      </span>
    );
  };

  const totalResults =
    searchMode === 'invoice'
      ? invoiceResponse?.total ?? 0
      : chunkResponse?.total ?? 0;
  const totalPages =
    searchMode === 'invoice'
      ? invoiceResponse?.total_pages ?? 1
      : chunkResponse?.total_pages ?? 1;
  const executionTimeMs =
    searchMode === 'invoice'
      ? invoiceResponse?.execution_time_ms
      : chunkResponse?.execution_time_ms;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="border-b border-slate-200 pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <Search className="w-5 h-5 text-indigo-600" />
              <span>Hybrid Document & Financial Search</span>
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Retrieve relevant document excerpts and structured invoice records with keyword, vector semantic, or fused RRF retrieval.
            </p>
          </div>

          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition ${
              showFilters
                ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
                : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'
            }`}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Filters</span>
          </button>
        </div>
      </div>

      {/* Capabilities Status Banner */}
      {capabilities && (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-700">Capabilities:</span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-medium border border-emerald-200">
                <CheckCircle className="w-3 h-3" /> Keyword Search
              </span>

              {capabilities.semantic_search_available ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 font-medium border border-indigo-200">
                  <Sparkles className="w-3 h-3" /> Semantic ({capabilities.embedding_model})
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-medium border border-amber-200" title={capabilities.status_message}>
                  <AlertCircle className="w-3 h-3" /> Semantic Offline (Keyword Fallback Active)
                </span>
              )}

              <span className="text-slate-500 font-mono">
                {capabilities.embedded_chunks} / {capabilities.total_chunks} Chunks Embedded ({capabilities.embedding_dimension}-dim)
              </span>
            </div>

            <div className="flex items-center gap-2">
              {capabilities.unembedded_chunks > 0 && (
                <button
                  onClick={handleBackfill}
                  disabled={backfilling}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-white border border-slate-300 hover:bg-slate-100 text-slate-700 font-medium transition shadow-2xs disabled:opacity-50"
                >
                  <RefreshCw className={`w-3 h-3 ${backfilling ? 'animate-spin' : ''}`} />
                  <span>{backfilling ? 'Generating...' : `Backfill (${capabilities.unembedded_chunks})`}</span>
                </button>
              )}
            </div>
          </div>

          {backfillMessage && (
            <div className="mt-2 text-[11px] text-indigo-700 font-medium bg-indigo-50/70 p-2 rounded border border-indigo-100">
              {backfillMessage}
            </div>
          )}
        </div>
      )}

      {/* Main Search Input & Mode Selector */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs space-y-4">
        {/* Search Bar */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSearch(1);
          }}
          className="flex items-center gap-2"
        >
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by keywords, invoice number, vendor, natural concepts, or line items..."
              className="w-full pl-9 pr-8 py-2.5 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
          >
            {loading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            <span>Search</span>
          </button>
        </form>

        {/* Mode Selector Tabs */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-100">
          <span className="text-xs font-semibold text-slate-500 mr-2">Search Mode:</span>
          {[
            { id: 'hybrid', label: 'Hybrid (RRF)', desc: 'Fused Keyword + Semantic' },
            { id: 'keyword', label: 'Keyword Only', desc: 'Exact multi-term SQL matching' },
            { id: 'semantic', label: 'Semantic Only', desc: 'Cosine similarity embeddings' },
            { id: 'invoice', label: 'Structured Invoices', desc: 'Invoice records & line items' },
          ].map((modeItem) => {
            const isSelected = searchMode === modeItem.id;
            return (
              <button
                key={modeItem.id}
                type="button"
                onClick={() => handleModeChange(modeItem.id as SearchMode)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition cursor-pointer border ${
                  isSelected
                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-xs'
                    : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                }`}
                title={modeItem.desc}
              >
                {modeItem.label}
              </button>
            );
          })}
        </div>

        {/* Expandable Filter Panel */}
        {showFilters && (
          <div className="pt-3 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs bg-slate-50/60 p-3 rounded-lg">
            <div>
              <label className="block font-medium text-slate-700 mb-1">File Format</label>
              <select
                value={fileType}
                onChange={(e) => setFileType(e.target.value)}
                className="w-full px-2.5 py-1.5 bg-white border border-slate-300 rounded text-slate-800"
              >
                <option value="">All Formats</option>
                <option value="pdf">PDF</option>
                <option value="xlsx">Excel (.xlsx)</option>
                <option value="xls">Excel (.xls)</option>
                <option value="csv">CSV</option>
                <option value="png">PNG Scan</option>
                <option value="jpg">JPG Scan</option>
              </select>
            </div>

            <div>
              <label className="block font-medium text-slate-700 mb-1">Currency</label>
              <select
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="w-full px-2.5 py-1.5 bg-white border border-slate-300 rounded text-slate-800"
              >
                <option value="">All Currencies</option>
                <option value="USD">USD ($)</option>
                <option value="EUR">EUR (€)</option>
                <option value="GBP">GBP (£)</option>
                <option value="CAD">CAD ($)</option>
              </select>
            </div>

            <div>
              <label className="block font-medium text-slate-700 mb-1">Supplier Filter</label>
              <input
                type="text"
                value={supplierName}
                onChange={(e) => setSupplierName(e.target.value)}
                placeholder="e.g. Acme Corp"
                className="w-full px-2.5 py-1.5 bg-white border border-slate-300 rounded text-slate-800"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-700 mb-1">Date Range</label>
              <div className="flex items-center gap-1">
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-1/2 px-1.5 py-1 bg-white border border-slate-300 rounded text-[11px]"
                />
                <span className="text-slate-400">-</span>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-1/2 px-1.5 py-1 bg-white border border-slate-300 rounded text-[11px]"
                />
              </div>
            </div>

            <div>
              <label className="block font-medium text-slate-700 mb-1">Amount Range</label>
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  placeholder="Min"
                  value={amountMin}
                  onChange={(e) => setAmountMin(e.target.value)}
                  className="w-1/2 px-2 py-1 bg-white border border-slate-300 rounded text-xs"
                />
                <span className="text-slate-400">-</span>
                <input
                  type="number"
                  placeholder="Max"
                  value={amountMax}
                  onChange={(e) => setAmountMax(e.target.value)}
                  className="w-1/2 px-2 py-1 bg-white border border-slate-300 rounded text-xs"
                />
              </div>
            </div>

            <div>
              <label className="block font-medium text-slate-700 mb-1">Review Status</label>
              <select
                value={needsReview === undefined ? '' : String(needsReview)}
                onChange={(e) =>
                  setNeedsReview(
                    e.target.value === '' ? undefined : e.target.value === 'true'
                  )
                }
                className="w-full px-2.5 py-1.5 bg-white border border-slate-300 rounded text-slate-800"
              >
                <option value="">All Invoices</option>
                <option value="true">Needs Manual Review</option>
                <option value="false">Review Clean</option>
              </select>
            </div>

            <div className="sm:col-span-2 flex items-end justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setFileType('');
                  setCurrency('');
                  setSupplierName('');
                  setCustomerName('');
                  setDateFrom('');
                  setDateTo('');
                  setAmountMin('');
                  setAmountMax('');
                  setNeedsReview(undefined);
                  setIsValid(undefined);
                }}
                className="px-3 py-1.5 rounded bg-white border border-slate-300 hover:bg-slate-100 text-slate-600 transition"
              >
                Reset Filters
              </button>
              <button
                type="button"
                onClick={() => handleSearch(1)}
                className="px-4 py-1.5 rounded bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition"
              >
                Apply Filters
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Fallback Mode Notification */}
      {chunkResponse?.fallback_mode && (
        <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3 text-amber-900 text-xs">
          <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold block">Fallback Retrieval Mode Active</span>
            <p className="mt-0.5 text-amber-800">
              {chunkResponse.fallback_reason ||
                'Semantic search is currently offline. Operating in deterministic keyword fallback mode.'}
            </p>
          </div>
        </div>
      )}

      {/* Error Notice */}
      {searchError && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-900 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <span>{searchError}</span>
        </div>
      )}

      {/* Results Header / Stats */}
      {(chunkResponse || invoiceResponse) && (
        <div className="flex items-center justify-between text-xs text-slate-500 px-1">
          <span>
            Found <strong className="text-slate-800">{totalResults}</strong> match(es) across documents
            {executionTimeMs !== undefined && ` in ${executionTimeMs}ms`}
          </span>
          {totalPages > 1 && (
            <span>
              Page {page} of {totalPages}
            </span>
          )}
        </div>
      )}

      {/* Chunk / Document Results List */}
      {chunkResponse && (
        <div className="space-y-3">
          {chunkResponse.items.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-xs">
              <Search className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="font-medium text-slate-700">No matching text chunks found.</p>
              <p className="mt-1">Try broadening your search terms or clearing specific filters.</p>
            </div>
          ) : (
            chunkResponse.items.map((item, idx) => {
              const isHybrid = item.match_type === 'hybrid';
              const isSemantic = item.match_type === 'semantic';
              const isKeyword = item.match_type === 'keyword';

              return (
                <div
                  key={item.chunk_id || idx}
                  className="bg-white border border-slate-200 hover:border-indigo-300 rounded-xl p-4 shadow-2xs transition space-y-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                    <div className="flex flex-wrap items-center gap-2">
                      {/* Match Type Badge */}
                      {isHybrid && (
                        <span className="px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 font-bold text-[10px] uppercase tracking-wide border border-indigo-200">
                          HYBRID MATCH (RRF)
                        </span>
                      )}
                      {isSemantic && (
                        <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 font-bold text-[10px] uppercase tracking-wide border border-blue-200">
                          SEMANTIC MATCH
                        </span>
                      )}
                      {isKeyword && (
                        <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-bold text-[10px] uppercase tracking-wide border border-emerald-200">
                          KEYWORD MATCH
                        </span>
                      )}

                      {/* File badge */}
                      <button
                        type="button"
                        onClick={() => onViewDocument && onViewDocument(item.document_id)}
                        className={`flex items-center gap-1 text-slate-800 font-semibold text-xs ${
                          onViewDocument ? 'hover:text-indigo-600 cursor-pointer' : ''
                        }`}
                      >
                        <FileText className="w-3.5 h-3.5 text-slate-500" />
                        <span>{item.document_filename}</span>
                      </button>

                      {/* Location badges */}
                      {item.page_number && (
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-mono">
                          Page {item.page_number}
                        </span>
                      )}
                      {item.sheet_name && (
                        <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-mono">
                          Sheet: {item.sheet_name}
                          {item.row_start && ` (Rows ${item.row_start}-${item.row_end})`}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-slate-500">
                      <span className="font-mono bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                        Score: {item.score}
                      </span>
                      {item.keyword_rank && (
                        <span className="text-[10px]">kw #{item.keyword_rank}</span>
                      )}
                      {item.semantic_rank && (
                        <span className="text-[10px]">sem #{item.semantic_rank}</span>
                      )}
                    </div>
                  </div>

                  {/* Excerpt Snippet */}
                  <div className="text-xs text-slate-700 leading-relaxed font-sans bg-slate-50/70 p-3 rounded-lg border border-slate-100">
                    {renderHighlightedSnippet(item.highlighted_snippet || item.content)}
                  </div>

                  {/* Linked Invoice Details Pill (if present) */}
                  {item.invoice_id && (
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px] text-slate-600 bg-indigo-50/40 p-2 rounded border border-indigo-100/60">
                      <div className="flex items-center gap-2">
                        <Receipt className="w-3.5 h-3.5 text-indigo-600" />
                        <span className="font-semibold text-slate-800">
                          Linked Invoice #{item.invoice_number || 'N/A'}
                        </span>
                        {item.supplier_name && <span>&bull; {item.supplier_name}</span>}
                        {item.invoice_total && (
                          <span className="font-mono font-semibold text-slate-900">
                            &bull; {item.currency} {Number(item.invoice_total).toFixed(2)}
                          </span>
                        )}
                        {item.needs_manual_review && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[9px] font-bold">
                            NEEDS REVIEW
                          </span>
                        )}
                      </div>

                      {onViewInvoice && item.invoice_id && (
                        <button
                          onClick={() => onViewInvoice(item.invoice_id!)}
                          className="text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1 cursor-pointer"
                        >
                          <span>Review Invoice</span>
                          <ArrowRight className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Structured Invoice Results List */}
      {invoiceResponse && (
        <div className="space-y-3">
          {invoiceResponse.items.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500 text-xs">
              <Receipt className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="font-medium text-slate-700">No matching invoices found.</p>
              <p className="mt-1">Try modifying your query or filter parameters.</p>
            </div>
          ) : (
            invoiceResponse.items.map((inv) => (
              <div
                key={inv.invoice_id}
                className="bg-white border border-slate-200 hover:border-indigo-300 rounded-xl p-4 shadow-2xs transition space-y-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono font-bold text-sm text-slate-900">
                      Invoice #{inv.invoice_number || 'UNKNOWN'}
                    </span>
                    <span className="text-xs text-slate-600 font-medium">
                      &bull; {inv.supplier_name || 'Unknown Supplier'}
                    </span>
                    {inv.customer_name && (
                      <span className="text-xs text-slate-400">&rarr; {inv.customer_name}</span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Status Badges */}
                    {inv.needs_manual_review ? (
                      <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold border border-amber-200">
                        NEEDS REVIEW
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold border border-emerald-200">
                        REVIEW COMPLETE
                      </span>
                    )}

                    {inv.is_manually_corrected && (
                      <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 text-[10px] font-bold border border-blue-200">
                        CORRECTED
                      </span>
                    )}

                    {!inv.is_valid && (
                      <span className="px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 text-[10px] font-bold border border-rose-200">
                        VALIDATION ERROR
                      </span>
                    )}

                    {inv.has_duplicates && (
                      <span className="px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 text-[10px] font-bold border border-purple-200">
                        DUPLICATE
                      </span>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs bg-slate-50/70 p-3 rounded-lg border border-slate-100">
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Total Amount</span>
                    <span className="font-mono font-bold text-slate-900 text-sm">
                      {inv.currency || '$'} {inv.total ? Number(inv.total).toFixed(2) : '0.00'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Invoice Date</span>
                    <span className="text-slate-700 font-medium">
                      {inv.invoice_date || 'N/A'}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Source File</span>
                    <button
                      type="button"
                      onClick={() => onViewDocument && onViewDocument(inv.document_id)}
                      className={`text-slate-700 truncate block max-w-[150px] text-left ${
                        onViewDocument ? 'hover:text-indigo-600 cursor-pointer' : ''
                      }`}
                      title={inv.document_filename}
                    >
                      {inv.document_filename}
                    </button>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">Line Items</span>
                    <span className="text-slate-700 font-mono">
                      {inv.line_items_count} item(s)
                    </span>
                  </div>
                </div>

                {inv.matched_fields && inv.matched_fields.length > 0 && (
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                    <span className="font-semibold text-slate-600">Matched in:</span>
                    {inv.matched_fields.map((mf) => (
                      <span key={mf} className="px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 font-mono text-[10px]">
                        {mf}
                      </span>
                    ))}
                  </div>
                )}

                {inv.highlighted_snippet && (
                  <div className="text-xs text-slate-700 bg-slate-50 p-2.5 rounded border border-slate-100">
                    {renderHighlightedSnippet(inv.highlighted_snippet)}
                  </div>
                )}

                {onViewInvoice && (
                  <div className="flex justify-end pt-1">
                    <button
                      onClick={() => onViewInvoice(inv.invoice_id)}
                      className="text-xs text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1 cursor-pointer"
                    >
                      <span>Open in Invoice Review</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-slate-200 pt-4">
          <button
            onClick={() => handleSearch(Math.max(1, page - 1))}
            disabled={page <= 1 || loading}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
          >
            <ChevronLeft className="w-4 h-4" />
            <span>Previous</span>
          </button>

          <span className="text-xs text-slate-600 font-medium">
            Page {page} of {totalPages}
          </span>

          <button
            onClick={() => handleSearch(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages || loading}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
          >
            <span>Next</span>
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};
