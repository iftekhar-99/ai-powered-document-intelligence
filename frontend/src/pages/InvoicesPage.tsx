import React, { useState, useEffect, useCallback } from 'react';
import { InvoiceDetail, InvoiceListResponse } from '../types';
import { fetchInvoices } from '../services/api';
import { InvoiceDetailModal } from '../components/InvoiceDetailModal';
import {
  Receipt,
  Search,
  AlertTriangle,
  CheckCircle2,
  Edit3,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from 'lucide-react';

interface InvoicesPageProps {
  initialNeedsReviewOnly?: boolean;
  onReviewCountChange?: (count: number) => void;
}

export const InvoicesPage: React.FC<InvoicesPageProps> = ({
  initialNeedsReviewOnly = false,
  onReviewCountChange,
}) => {
  const [invoices, setInvoices] = useState<InvoiceDetail[]>([]);
  const [totalInvoices, setTotalInvoices] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [skip, setSkip] = useState<number>(0);
  const [limit] = useState<number>(10);

  // Filters
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [currencyFilter, setCurrencyFilter] = useState<string>('');
  const [reviewFilter, setReviewFilter] = useState<string>(
    initialNeedsReviewOnly ? 'true' : ''
  );
  const [correctedFilter, setCorrectedFilter] = useState<string>('');

  // Selected invoice for detail/correction modal
  const [selectedInvoice, setSelectedInvoice] = useState<InvoiceDetail | null>(null);

  const loadInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const params: any = {
        skip,
        limit,
        search: searchTerm.trim() || undefined,
        currency: currencyFilter || undefined,
      };

      if (reviewFilter === 'true') params.needs_review = true;
      else if (reviewFilter === 'false') params.needs_review = false;

      if (correctedFilter === 'true') params.is_manually_corrected = true;
      else if (correctedFilter === 'false') params.is_manually_corrected = false;

      const response: InvoiceListResponse = await fetchInvoices(params);
      setInvoices(response.items);
      setTotalInvoices(response.total);

      // If initialNeedsReviewOnly, report count
      if (initialNeedsReviewOnly && onReviewCountChange) {
        onReviewCountChange(response.total);
      }
    } catch (err) {
      console.error('Failed to load invoices:', err);
    } finally {
      setLoading(false);
    }
  }, [skip, limit, searchTerm, currencyFilter, reviewFilter, correctedFilter, initialNeedsReviewOnly, onReviewCountChange]);

  useEffect(() => {
    loadInvoices();
  }, [loadInvoices]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSkip(0);
    loadInvoices();
  };

  const handleInvoiceUpdated = (updated: InvoiceDetail) => {
    setInvoices((prev) =>
      prev.map((inv) => (inv.id === updated.id ? updated : inv))
    );
    if (selectedInvoice && selectedInvoice.id === updated.id) {
      setSelectedInvoice(updated);
    }
  };

  const totalPages = Math.ceil(totalInvoices / limit) || 1;
  const currentPage = Math.floor(skip / limit) + 1;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Receipt className="w-6 h-6 text-indigo-600" />
            {initialNeedsReviewOnly ? 'Invoices Requiring Review' : 'Extracted Invoices & Review Dashboard'}
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Audit AI extraction outputs, verify field quotations, and make permanent manual corrections with justification logs.
          </p>
        </div>

        <button
          onClick={loadInvoices}
          disabled={loading}
          className="inline-flex items-center px-3.5 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50 transition shadow-xs disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs space-y-3">
        <form onSubmit={handleSearchSubmit} className="grid grid-cols-1 md:grid-cols-5 gap-3 text-xs">
          {/* Search Input */}
          <div className="relative md:col-span-2">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search by invoice #, supplier name, or customer name..."
              className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            />
          </div>

          {/* Currency Filter */}
          <div>
            <select
              value={currencyFilter}
              onChange={(e) => {
                setCurrencyFilter(e.target.value);
                setSkip(0);
              }}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            >
              <option value="">All Currencies</option>
              <option value="USD">USD ($)</option>
              <option value="EUR">EUR (€)</option>
              <option value="GBP">GBP (£)</option>
              <option value="CAD">CAD ($)</option>
            </select>
          </div>

          {/* Review Filter */}
          <div>
            <select
              value={reviewFilter}
              onChange={(e) => {
                setReviewFilter(e.target.value);
                setSkip(0);
              }}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            >
              <option value="">All Review Statuses</option>
              <option value="true">Needs Review Only</option>
              <option value="false">Clean / Verified Only</option>
            </select>
          </div>

          {/* Correction Filter */}
          <div>
            <select
              value={correctedFilter}
              onChange={(e) => {
                setCorrectedFilter(e.target.value);
                setSkip(0);
              }}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            >
              <option value="">All Correction States</option>
              <option value="true">Manually Corrected</option>
              <option value="false">Original AI Extraction</option>
            </select>
          </div>
        </form>
      </div>

      {/* Invoices Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Invoice Number</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Supplier</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3 text-right">Total Amount</th>
                <th className="px-4 py-3 text-center">Confidence</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-indigo-600 mb-2" />
                    Loading invoices...
                  </td>
                </tr>
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-400 italic">
                    No extracted invoices matching the current criteria.
                  </td>
                </tr>
              ) : (
                invoices.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-50/70 transition">
                    {/* Invoice # */}
                    <td className="px-4 py-3.5 font-semibold text-slate-900 whitespace-nowrap">
                      {inv.invoice_number || (
                        <span className="italic text-slate-400">Unassigned</span>
                      )}
                    </td>

                    {/* Date */}
                    <td className="px-4 py-3.5 text-slate-600 whitespace-nowrap">
                      {inv.invoice_date || '—'}
                    </td>

                    {/* Supplier */}
                    <td className="px-4 py-3.5 text-slate-900 max-w-xs truncate font-medium">
                      {inv.supplier_name || '—'}
                    </td>

                    {/* Customer */}
                    <td className="px-4 py-3.5 text-slate-600 max-w-xs truncate">
                      {inv.customer_name || '—'}
                    </td>

                    {/* Total Amount */}
                    <td className="px-4 py-3.5 text-right font-mono font-bold text-slate-900 whitespace-nowrap">
                      {inv.total !== null && inv.total !== undefined
                        ? `${inv.currency || '$'} ${Number(inv.total).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                        : '—'}
                    </td>

                    {/* Estimated Confidence */}
                    <td className="px-4 py-3.5 text-center whitespace-nowrap">
                      {inv.field_confidence?.overall_confidence !== undefined ? (
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${
                            inv.field_confidence.overall_confidence >= 0.85
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                              : inv.field_confidence.overall_confidence >= 0.7
                              ? 'bg-amber-50 text-amber-800 border-amber-200'
                              : 'bg-rose-50 text-rose-800 border-rose-200'
                          }`}
                          title="Estimated extraction confidence, not measured accuracy"
                        >
                          {Math.round(inv.field_confidence.overall_confidence * 100)}% (Est.)
                        </span>
                      ) : (
                        <span className="text-slate-400 text-[11px]">N/A</span>
                      )}
                    </td>

                    {/* Status Badges */}
                    <td className="px-4 py-3.5 text-center whitespace-nowrap space-y-1">
                      <div>
                        {inv.needs_manual_review ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                            <AlertTriangle className="w-3 h-3 mr-1" /> Needs Review
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                            <CheckCircle2 className="w-3 h-3 mr-1" /> Clean
                          </span>
                        )}
                      </div>
                      {inv.validation_issues && inv.validation_issues.filter((i) => !i.resolved).length > 0 && (
                        <div>
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                            {inv.validation_issues.filter((i) => !i.resolved).length} active issue(s)
                          </span>
                        </div>
                      )}
                      {inv.is_manually_corrected && (
                        <div>
                          <span className="inline-flex items-center px-2 py-0.2 rounded-full text-[9px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                            Corrected
                          </span>
                        </div>
                      )}
                    </td>

                    {/* Action */}
                    <td className="px-4 py-3.5 text-right whitespace-nowrap">
                      <button
                        onClick={() => setSelectedInvoice(inv)}
                        className="inline-flex items-center px-2.5 py-1 text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-md transition"
                      >
                        <Edit3 className="w-3.5 h-3.5 mr-1" /> Review & Edit
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        {totalInvoices > limit && (
          <div className="px-4 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
            <div>
              Showing <span className="font-semibold text-slate-900">{skip + 1}</span> to{' '}
              <span className="font-semibold text-slate-900">
                {Math.min(skip + limit, totalInvoices)}
              </span>{' '}
              of <span className="font-semibold text-slate-900">{totalInvoices}</span> invoices
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setSkip(Math.max(0, skip - limit))}
                disabled={skip === 0}
                className="p-1.5 border border-slate-300 rounded-lg hover:bg-slate-100 disabled:opacity-40 transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="font-semibold text-slate-900">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setSkip(skip + limit)}
                disabled={skip + limit >= totalInvoices}
                className="p-1.5 border border-slate-300 rounded-lg hover:bg-slate-100 disabled:opacity-40 transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Selected Invoice Detail & Correction Modal */}
      {selectedInvoice && (
        <InvoiceDetailModal
          invoice={selectedInvoice}
          onClose={() => setSelectedInvoice(null)}
          onInvoiceUpdated={handleInvoiceUpdated}
        />
      )}
    </div>
  );
};
