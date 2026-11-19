import React, { useState, useEffect } from 'react';
import {
  InvoiceDetail,
  InvoiceCorrectionAudit,
  InvoiceLineItemDetail,
  DuplicateMatchDetail,
} from '../types';
import {
  updateInvoice,
  updateLineItem,
  createLineItem,
  deleteLineItem,
  fetchInvoiceCorrections,
  fetchInvoice,
  revalidateInvoice,
  fetchInvoiceDuplicates,
  resolveValidationIssue,
  reopenValidationIssue,
} from '../services/api';
import {
  X,
  Edit3,
  CheckCircle2,
  AlertTriangle,
  History,
  FileText,
  Plus,
  Trash2,
  Building,
  User,
  ShieldAlert,
  Save,
  Check,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  AlertCircle,
  CheckCircle,
} from 'lucide-react';

interface InvoiceDetailModalProps {
  invoice: InvoiceDetail;
  onClose: () => void;
  onInvoiceUpdated?: (updatedInvoice: InvoiceDetail) => void;
}

export const InvoiceDetailModal: React.FC<InvoiceDetailModalProps> = ({
  invoice: initialInvoice,
  onClose,
  onInvoiceUpdated,
}) => {
  const [invoice, setInvoice] = useState<InvoiceDetail>(initialInvoice);
  const [activeTab, setActiveTab] = useState<'details' | 'lineItems' | 'evidence' | 'audit' | 'validation'>('details');
  const [isEditingHeader, setIsEditingHeader] = useState<boolean>(false);
  const [audits, setAudits] = useState<InvoiceCorrectionAudit[]>([]);
  const [loadingAudits, setLoadingAudits] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Validation & Duplicate states
  const [revalidating, setRevalidating] = useState<boolean>(false);
  const [duplicates, setDuplicates] = useState<DuplicateMatchDetail[]>([]);
  const [resolvingIssueId, setResolvingIssueId] = useState<string | null>(null);
  const [resolveNotes, setResolveNotes] = useState<string>('');
  const [resolveBy, setResolveBy] = useState<string>('');
  const [reopeningIssueId, setReopeningIssueId] = useState<string | null>(null);
  const [reopenNotes, setReopenNotes] = useState<string>('');
  const [reopenBy, setReopenBy] = useState<string>('');
  const [issueFilter, setIssueFilter] = useState<'all' | 'unresolved' | 'resolved'>('all');

  // Form states for Header Edit
  const [editInvoiceNumber, setEditInvoiceNumber] = useState(invoice.invoice_number || '');
  const [editInvoiceDate, setEditInvoiceDate] = useState(invoice.invoice_date || '');
  const [editSupplierName, setEditSupplierName] = useState(invoice.supplier_name || '');
  const [editCustomerName, setEditCustomerName] = useState(invoice.customer_name || '');
  const [editSubtotal, setEditSubtotal] = useState(invoice.subtotal !== null && invoice.subtotal !== undefined ? String(invoice.subtotal) : '');
  const [editTax, setEditTax] = useState(invoice.tax !== null && invoice.tax !== undefined ? String(invoice.tax) : '');
  const [editTotal, setEditTotal] = useState(invoice.total !== null && invoice.total !== undefined ? String(invoice.total) : '');
  const [editCurrency, setEditCurrency] = useState(invoice.currency || 'USD');
  const [editNeedsReview, setEditNeedsReview] = useState(invoice.needs_manual_review);
  const [editReason, setEditReason] = useState('');
  const [editCorrectedBy, setEditCorrectedBy] = useState('');

  // Line item editing states
  const [editingLineItemId, setEditingLineItemId] = useState<string | null>(null);
  const [liDescription, setLiDescription] = useState('');
  const [liQuantity, setLiQuantity] = useState('');
  const [liUnitPrice, setLiUnitPrice] = useState('');
  const [liTax, setLiTax] = useState('');
  const [liTotal, setLiTotal] = useState('');
  const [liReason, setLiReason] = useState('');
  const [liCorrectedBy, setLiCorrectedBy] = useState('');

  // Add line item state
  const [isAddingLineItem, setIsAddingLineItem] = useState<boolean>(false);
  const [newLiDescription, setNewLiDescription] = useState('');
  const [newLiQuantity, setNewLiQuantity] = useState('');
  const [newLiUnitPrice, setNewLiUnitPrice] = useState('');
  const [newLiTax, setNewLiTax] = useState('');
  const [newLiTotal, setNewLiTotal] = useState('');
  const [newLiReason, setNewLiReason] = useState('');
  const [newLiCorrectedBy, setNewLiCorrectedBy] = useState('');

  // Delete line item confirmation state
  const [deletingLineItem, setDeletingLineItem] = useState<InvoiceLineItemDetail | null>(null);
  const [deleteReason, setDeleteReason] = useState('');

  // Expanded evidence citation
  const [expandedCitationKey, setExpandedCitationKey] = useState<string | null>(null);

  const loadAudits = async () => {
    setLoadingAudits(true);
    try {
      const data = await fetchInvoiceCorrections(invoice.id);
      setAudits(data);
    } catch (err: any) {
      console.error('Failed to load audits:', err);
    } finally {
      setLoadingAudits(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'audit') {
      loadAudits();
    }
  }, [activeTab]);

  const refreshInvoice = async () => {
    try {
      const updated = await fetchInvoice(invoice.id);
      setInvoice(updated);
      if (onInvoiceUpdated) {
        onInvoiceUpdated(updated);
      }
    } catch (err) {
      console.error('Failed to re-fetch invoice:', err);
    }
  };

  const loadDuplicates = async () => {
    try {
      const data = await fetchInvoiceDuplicates(invoice.id);
      setDuplicates(data);
    } catch (err: any) {
      console.error('Failed to load duplicates:', err);
    }
  };

  useEffect(() => {
    loadDuplicates();
  }, [invoice.id]);

  const handleRevalidate = async () => {
    setRevalidating(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const summary = await revalidateInvoice(invoice.id);
      setDuplicates(summary.duplicates_detected || []);
      await refreshInvoice();
      setSuccessMessage(
        `Re-validation completed: ${summary.total_issues} issue(s) detected (${summary.unresolved_errors} error(s), ${summary.unresolved_warnings} warning(s)).`
      );
    } catch (err: any) {
      setErrorMessage(err.message || 'Validation failed');
    } finally {
      setRevalidating(false);
    }
  };

  const handleResolveIssue = async (issueId: string) => {
    try {
      await resolveValidationIssue(issueId, {
        resolved_by: resolveBy.trim() || undefined,
        resolution_notes: resolveNotes.trim() || undefined,
      });
      setResolvingIssueId(null);
      setResolveNotes('');
      setResolveBy('');
      await refreshInvoice();
      setSuccessMessage('Validation discrepancy successfully marked as resolved.');
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to resolve validation issue.');
    }
  };

  const handleReopenIssue = async (issueId: string) => {
    try {
      await reopenValidationIssue(issueId, {
        reopened_by: reopenBy.trim() || undefined,
        reopen_notes: reopenNotes.trim() || undefined,
      });
      setReopeningIssueId(null);
      setReopenNotes('');
      setReopenBy('');
      await refreshInvoice();
      setSuccessMessage('Validation issue reopened.');
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to reopen validation issue.');
    }
  };

  const handleSaveHeader = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editReason.trim()) {
      setErrorMessage('Correction reason is mandatory.');
      return;
    }

    setSaving(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const payload: any = {
        invoice_number: editInvoiceNumber.trim() || undefined,
        invoice_date: editInvoiceDate || undefined,
        supplier_name: editSupplierName.trim() || undefined,
        customer_name: editCustomerName.trim() || undefined,
        currency: editCurrency.trim().toUpperCase() || undefined,
        needs_manual_review: editNeedsReview,
        reason: editReason.trim(),
        corrected_by: editCorrectedBy.trim() || undefined,
      };

      if (editSubtotal !== '') payload.subtotal = parseFloat(editSubtotal);
      if (editTax !== '') payload.tax = parseFloat(editTax);
      if (editTotal !== '') payload.total = parseFloat(editTotal);

      const updated = await updateInvoice(invoice.id, payload);
      setInvoice(updated);
      setIsEditingHeader(false);
      setEditReason('');
      setSuccessMessage('Invoice headers and amounts successfully updated.');
      if (onInvoiceUpdated) onInvoiceUpdated(updated);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to update invoice.');
    } finally {
      setSaving(false);
    }
  };

  const handleStartEditLineItem = (li: InvoiceLineItemDetail) => {
    setEditingLineItemId(li.id);
    setLiDescription(li.description);
    setLiQuantity(li.quantity !== null && li.quantity !== undefined ? String(li.quantity) : '');
    setLiUnitPrice(li.unit_price !== null && li.unit_price !== undefined ? String(li.unit_price) : '');
    setLiTax(li.tax !== null && li.tax !== undefined ? String(li.tax) : '');
    setLiTotal(li.line_total !== null && li.line_total !== undefined ? String(li.line_total) : '');
    setLiReason('');
    setLiCorrectedBy('');
    setErrorMessage(null);
  };

  const handleSaveLineItem = async (liId: string) => {
    if (!liReason.trim()) {
      setErrorMessage('Line item correction reason is required.');
      return;
    }

    setSaving(true);
    setErrorMessage(null);
    try {
      const payload: any = {
        description: liDescription.trim() || undefined,
        reason: liReason.trim(),
        corrected_by: liCorrectedBy.trim() || undefined,
      };
      if (liQuantity !== '') payload.quantity = parseFloat(liQuantity);
      if (liUnitPrice !== '') payload.unit_price = parseFloat(liUnitPrice);
      if (liTax !== '') payload.tax = parseFloat(liTax);
      if (liTotal !== '') payload.line_total = parseFloat(liTotal);

      await updateLineItem(invoice.id, liId, payload);
      setEditingLineItemId(null);
      await refreshInvoice();
      setSuccessMessage('Line item updated successfully.');
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to update line item.');
    } finally {
      setSaving(false);
    }
  };

  const handleCreateLineItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newLiDescription.trim() || !newLiReason.trim()) {
      setErrorMessage('Line item description and justification reason are required.');
      return;
    }

    setSaving(true);
    setErrorMessage(null);
    try {
      const payload: any = {
        description: newLiDescription.trim(),
        reason: newLiReason.trim(),
        corrected_by: newLiCorrectedBy.trim() || undefined,
      };
      if (newLiQuantity !== '') payload.quantity = parseFloat(newLiQuantity);
      if (newLiUnitPrice !== '') payload.unit_price = parseFloat(newLiUnitPrice);
      if (newLiTax !== '') payload.tax = parseFloat(newLiTax);
      if (newLiTotal !== '') payload.line_total = parseFloat(newLiTotal);

      await createLineItem(invoice.id, payload);
      setIsAddingLineItem(false);
      setNewLiDescription('');
      setNewLiQuantity('');
      setNewLiUnitPrice('');
      setNewLiTax('');
      setNewLiTotal('');
      setNewLiReason('');
      setNewLiCorrectedBy('');
      await refreshInvoice();
      setSuccessMessage('Line item added successfully.');
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to add line item.');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteLineItem = async () => {
    if (!deletingLineItem) return;
    if (!deleteReason.trim()) {
      setErrorMessage('A reason for removing this line item is mandatory.');
      return;
    }

    setSaving(true);
    setErrorMessage(null);
    try {
      await deleteLineItem(invoice.id, deletingLineItem.id, deleteReason.trim());
      setDeletingLineItem(null);
      setDeleteReason('');
      await refreshInvoice();
      setSuccessMessage('Line item deleted.');
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to delete line item.');
    } finally {
      setSaving(false);
    }
  };

  // Helper for confidence badge
  const renderConfidenceBadge = (confidence?: number | null) => {
    if (confidence === null || confidence === undefined) {
      return <span className="text-slate-400 text-xs">Unspecified</span>;
    }
    const pct = Math.round(confidence * 100);
    let colorClass = 'bg-emerald-100 text-emerald-800 border-emerald-200';
    if (pct < 70) colorClass = 'bg-rose-100 text-rose-800 border-rose-200';
    else if (pct < 85) colorClass = 'bg-amber-100 text-amber-800 border-amber-200';

    return (
      <span
        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${colorClass}`}
        title="Estimated extraction confidence, not empirical accuracy"
      >
        {pct}% (Est. Confidence)
      </span>
    );
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl border border-slate-200 w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Top Header */}
        <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/80 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-indigo-50 text-indigo-700 rounded-lg border border-indigo-100">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-slate-900">
                  {invoice.invoice_number ? `Invoice #${invoice.invoice_number}` : 'Unnumbered Invoice'}
                </h2>
                {invoice.needs_manual_review ? (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                    <AlertTriangle className="w-3 h-3 mr-1" /> Needs Review
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                    <CheckCircle2 className="w-3 h-3 mr-1" /> Verified
                  </span>
                )}
                {invoice.is_manually_corrected && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800 border border-indigo-200">
                    <Edit3 className="w-3 h-3 mr-1" /> Manually Corrected
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                {invoice.supplier_name || 'Unknown Supplier'} • ID: {invoice.id}
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleRevalidate}
              disabled={revalidating}
              className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 rounded-lg transition disabled:opacity-50"
              title="Run deterministic financial rules and duplicate detection"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${revalidating ? 'animate-spin text-indigo-600' : 'text-slate-500'}`} />
              {revalidating ? 'Validating...' : 'Revalidate'}
            </button>
            {!isEditingHeader && (
              <button
                onClick={() => setIsEditingHeader(true)}
                className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 rounded-lg transition"
              >
                <Edit3 className="w-3.5 h-3.5 mr-1.5" />
                Edit Header & Totals
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Global Notifications */}
        {errorMessage && (
          <div className="px-6 py-2.5 bg-rose-50 border-b border-rose-200 text-rose-700 text-xs font-medium flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <button onClick={() => setErrorMessage(null)} className="text-rose-500 hover:text-rose-700">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
        {successMessage && (
          <div className="px-6 py-2.5 bg-emerald-50 border-b border-emerald-200 text-emerald-700 text-xs font-medium flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Check className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>{successMessage}</span>
            </div>
            <button onClick={() => setSuccessMessage(null)} className="text-emerald-500 hover:text-emerald-700">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Review Banner if Needs Review */}
        {invoice.needs_manual_review && (
          <div className="px-6 py-3 bg-amber-50 border-b border-amber-200">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <div className="text-xs text-amber-900">
                <span className="font-bold">Manual Review Required:</span> This invoice has flagged validation issues or uncertain evidence quotations.
                {invoice.validation_issues && invoice.validation_issues.length > 0 && (
                  <ul className="mt-1 list-disc list-inside space-y-0.5 text-amber-800">
                    {invoice.validation_issues.map((issue) => (
                      <li key={issue.id}>
                        <span className="font-semibold">{issue.field_name}:</span> {issue.description} ({issue.severity})
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Duplicate Invoices Warning Banner */}
        {duplicates.length > 0 && (
          <div className="px-6 py-3 bg-rose-50 border-b border-rose-200">
            <div className="flex items-start gap-2.5">
              <AlertCircle className="w-5 h-5 text-rose-600 mt-0.5 flex-shrink-0" />
              <div className="text-xs text-rose-950 flex-1">
                <div className="font-bold text-sm text-rose-850 flex items-center gap-2">
                  <span>Potential Duplicate Invoice Detected!</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-rose-200 text-rose-900">
                    {duplicates.some((d) => d.match_type === 'exact_duplicate') ? 'Exact Match' : 'Likely Match'}
                  </span>
                </div>
                <p className="mt-1 text-rose-800">
                  This invoice matches {duplicates.length} other record(s) across different documents in the system:
                </p>
                <div className="mt-2 space-y-1.5">
                  {duplicates.map((dup) => (
                    <div key={dup.invoice_id} className="p-2.5 bg-white rounded-lg border border-rose-200 text-xs shadow-sm">
                      <div className="flex items-center justify-between font-semibold text-rose-900">
                        <span>Invoice #{dup.invoice_number || 'UNKNOWN'} — {dup.supplier_name || 'Unknown Supplier'}</span>
                        <span className="font-mono">{dup.currency || '$'} {dup.total !== null && dup.total !== undefined ? Number(dup.total).toFixed(2) : '—'}</span>
                      </div>
                      <div className="text-[11px] text-rose-700 mt-0.5">
                        Document ID: {dup.document_id} • Invoice ID: {dup.invoice_id}
                      </div>
                      <ul className="mt-1 list-disc list-inside text-[11px] text-rose-800">
                        {dup.match_reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="px-6 border-b border-slate-200 bg-white flex space-x-6 text-xs font-semibold">
          <button
            onClick={() => setActiveTab('details')}
            className={`py-3 border-b-2 transition ${
              activeTab === 'details'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            Overview & Summary
          </button>
          <button
            onClick={() => setActiveTab('lineItems')}
            className={`py-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'lineItems'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            Line Items ({invoice.line_items?.length || 0})
          </button>
          <button
            onClick={() => setActiveTab('validation')}
            className={`py-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'validation'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" /> Validation & Issues ({invoice.validation_issues?.length || 0})
          </button>
          <button
            onClick={() => setActiveTab('evidence')}
            className={`py-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'evidence'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            Source Evidence Inspector
          </button>
          <button
            onClick={() => setActiveTab('audit')}
            className={`py-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'audit'
                ? 'border-indigo-600 text-indigo-700'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <History className="w-3.5 h-3.5" /> Correction History
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: DETAILS & SUMMARY */}
          {activeTab === 'details' && (
            <div className="space-y-6">
              {/* Header Edit Form (Conditional) */}
              {isEditingHeader ? (
                <form onSubmit={handleSaveHeader} className="bg-slate-50 p-5 rounded-xl border border-indigo-200 space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                    <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <Edit3 className="w-4 h-4 text-indigo-600" />
                      Edit Invoice Header & Financial Totals
                    </h3>
                    <span className="text-xs text-slate-500">Atomic database correction with mandatory audit reason</span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Invoice Number</label>
                      <input
                        type="text"
                        value={editInvoiceNumber}
                        onChange={(e) => setEditInvoiceNumber(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Invoice Date</label>
                      <input
                        type="date"
                        value={editInvoiceDate}
                        onChange={(e) => setEditInvoiceDate(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Currency</label>
                      <input
                        type="text"
                        value={editCurrency}
                        maxLength={10}
                        onChange={(e) => setEditCurrency(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg uppercase focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Supplier Name</label>
                      <input
                        type="text"
                        value={editSupplierName}
                        onChange={(e) => setEditSupplierName(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Customer Name</label>
                      <input
                        type="text"
                        value={editCustomerName}
                        onChange={(e) => setEditCustomerName(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Pre-Tax Subtotal</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={editSubtotal}
                        onChange={(e) => setEditSubtotal(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Tax Amount</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={editTax}
                        onChange={(e) => setEditTax(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Total Amount</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={editTotal}
                        onChange={(e) => setEditTotal(e.target.value)}
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg font-bold text-slate-900 focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                    <div className="flex items-center pt-5">
                      <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={editNeedsReview}
                          onChange={(e) => setEditNeedsReview(e.target.checked)}
                          className="rounded text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="font-semibold text-slate-700">Flag as Needs Review</span>
                      </label>
                    </div>
                  </div>

                  {/* Mandatory Justification */}
                  <div className="pt-2 border-t border-slate-200">
                    <label className="block font-semibold text-slate-800 text-xs mb-1">
                      Correction Reason <span className="text-rose-500">* (Required)</span>
                    </label>
                    <textarea
                      rows={2}
                      required
                      value={editReason}
                      onChange={(e) => setEditReason(e.target.value)}
                      placeholder="Explain what was incorrect and why this adjustment is required (e.g. OCR misread of invoice number, added missing freight tax)"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Corrected By (Optional)</label>
                      <input
                        type="text"
                        value={editCorrectedBy}
                        onChange={(e) => setEditCorrectedBy(e.target.value)}
                        placeholder="e.g. auditor_jane"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-end space-x-3 pt-3">
                    <button
                      type="button"
                      onClick={() => setIsEditingHeader(false)}
                      disabled={saving}
                      className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-100 transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={saving || !editReason.trim()}
                      className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition disabled:opacity-50"
                    >
                      <Save className="w-3.5 h-3.5 mr-1.5" />
                      {saving ? 'Saving...' : 'Save Correction'}
                    </button>
                  </div>
                </form>
              ) : (
                /* Header Summary Cards */
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Parties Card */}
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Counterparties</h4>
                    <div className="space-y-3">
                      <div>
                        <div className="flex items-center text-xs text-slate-400 gap-1.5">
                          <Building className="w-3.5 h-3.5" /> Supplier / Vendor
                        </div>
                        <div className="font-semibold text-sm text-slate-900 mt-0.5">
                          {invoice.supplier_name || <span className="text-slate-400 italic">Not extracted</span>}
                        </div>
                      </div>
                      <div>
                        <div className="flex items-center text-xs text-slate-400 gap-1.5">
                          <User className="w-3.5 h-3.5" /> Customer / Bill-To
                        </div>
                        <div className="font-semibold text-sm text-slate-900 mt-0.5">
                          {invoice.customer_name || <span className="text-slate-400 italic">Not extracted</span>}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Financials Card */}
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Financial Totals</h4>
                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between items-center text-slate-600">
                        <span>Pre-tax Subtotal:</span>
                        <span className="font-mono font-medium">
                          {invoice.subtotal !== null && invoice.subtotal !== undefined
                            ? `${invoice.currency || '$'} ${Number(invoice.subtotal).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                            : '—'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center text-slate-600">
                        <span>Tax / VAT:</span>
                        <span className="font-mono font-medium">
                          {invoice.tax !== null && invoice.tax !== undefined
                            ? `${invoice.currency || '$'} ${Number(invoice.tax).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                            : '—'}
                        </span>
                      </div>
                      <div className="pt-2 border-t border-slate-200 flex justify-between items-center">
                        <span className="font-bold text-slate-900">Total Balance:</span>
                        <span className="font-mono font-bold text-base text-indigo-700">
                          {invoice.total !== null && invoice.total !== undefined
                            ? `${invoice.currency || '$'} ${Number(invoice.total).toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                            : '—'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Extraction Metadata Card */}
                  <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">AI Extraction Details</h4>
                    <div className="space-y-2 text-xs text-slate-600">
                      <div className="flex justify-between">
                        <span>Invoice Date:</span>
                        <span className="font-medium text-slate-800">
                          {invoice.invoice_date || <span className="italic text-slate-400">None</span>}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span>Page Range:</span>
                        <span className="font-medium text-slate-800">
                          {invoice.document_page_start
                            ? `Page ${invoice.document_page_start}${invoice.document_page_end ? ` – ${invoice.document_page_end}` : ''}`
                            : 'All pages'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span>Confidence:</span>
                        {renderConfidenceBadge(invoice.field_confidence?.overall_confidence || invoice.field_confidence?.total)}
                      </div>
                      <div className="flex justify-between">
                        <span>Extracted At:</span>
                        <span className="text-slate-500 text-[11px]">
                          {new Date(invoice.created_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Quick Line Items Preview */}
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <div className="px-4 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Itemized Breakdown ({invoice.line_items?.length || 0} items)
                  </h4>
                  <button
                    onClick={() => setActiveTab('lineItems')}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold"
                  >
                    Manage Line Items →
                  </button>
                </div>
                <div className="divide-y divide-slate-100">
                  {invoice.line_items && invoice.line_items.length > 0 ? (
                    invoice.line_items.slice(0, 5).map((li, idx) => (
                      <div key={li.id} className="p-3 text-xs flex items-center justify-between hover:bg-slate-50/50">
                        <div className="max-w-[70%]">
                          <span className="font-mono text-slate-400 mr-2">#{idx + 1}</span>
                          <span className="font-medium text-slate-900">{li.description}</span>
                          {li.quantity && (
                            <span className="text-slate-500 text-[11px] ml-2">
                              Qty: {li.quantity} {li.unit_price ? `@ ${invoice.currency || '$'}${li.unit_price}` : ''}
                            </span>
                          )}
                        </div>
                        <div className="font-mono font-semibold text-slate-800">
                          {li.line_total !== null && li.line_total !== undefined
                            ? `${invoice.currency || '$'} ${Number(li.line_total).toFixed(2)}`
                            : '—'}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-4 text-center text-xs text-slate-400 italic">No line items extracted.</div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: LINE ITEMS FULL MANAGEMENT */}
          {activeTab === 'lineItems' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  Manage extracted item rows. You can update quantities, prices, descriptions, add missing rows, or remove hallucinations.
                </p>
                {!isAddingLineItem && (
                  <button
                    onClick={() => setIsAddingLineItem(true)}
                    className="inline-flex items-center px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition"
                  >
                    <Plus className="w-3.5 h-3.5 mr-1" /> Add Line Item
                  </button>
                )}
              </div>

              {/* Add Line Item Form */}
              {isAddingLineItem && (
                <form onSubmit={handleCreateLineItem} className="p-4 bg-slate-50 rounded-xl border border-indigo-200 space-y-3 text-xs">
                  <h4 className="font-bold text-slate-900 flex items-center gap-1.5">
                    <Plus className="w-4 h-4 text-indigo-600" /> Add New Itemized Row
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                    <div className="md:col-span-2">
                      <label className="block font-semibold text-slate-700 mb-1">Description *</label>
                      <input
                        type="text"
                        required
                        value={newLiDescription}
                        onChange={(e) => setNewLiDescription(e.target.value)}
                        placeholder="Item or service description"
                        className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Quantity</label>
                      <input
                        type="number"
                        step="0.0001"
                        min="0"
                        value={newLiQuantity}
                        onChange={(e) => setNewLiQuantity(e.target.value)}
                        placeholder="1.0"
                        className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Unit Price</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={newLiUnitPrice}
                        onChange={(e) => setNewLiUnitPrice(e.target.value)}
                        placeholder="0.00"
                        className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Line Total</label>
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        value={newLiTotal}
                        onChange={(e) => setNewLiTotal(e.target.value)}
                        placeholder="0.00"
                        className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">
                        Reason for adding * <span className="text-rose-500">(Required)</span>
                      </label>
                      <input
                        type="text"
                        required
                        value={newLiReason}
                        onChange={(e) => setNewLiReason(e.target.value)}
                        placeholder="e.g. Added row omitted by document segmentation"
                        className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-700 mb-1">Corrected By</label>
                      <input
                        type="text"
                        value={newLiCorrectedBy}
                        onChange={(e) => setNewLiCorrectedBy(e.target.value)}
                        placeholder="auditor_username"
                        className="w-full px-2.5 py-1.5 border border-slate-300 rounded-md focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setIsAddingLineItem(false)}
                      className="px-3 py-1.5 border border-slate-300 rounded-md hover:bg-slate-100"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={saving || !newLiDescription.trim() || !newLiReason.trim()}
                      className="px-3 py-1.5 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {saving ? 'Adding...' : 'Confirm Add Item'}
                    </button>
                  </div>
                </form>
              )}

              {/* Line Items Table */}
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="px-3 py-2.5 w-10">#</th>
                      <th className="px-3 py-2.5">Description</th>
                      <th className="px-3 py-2.5 w-20 text-right">Qty</th>
                      <th className="px-3 py-2.5 w-24 text-right">Unit Price</th>
                      <th className="px-3 py-2.5 w-20 text-right">Tax</th>
                      <th className="px-3 py-2.5 w-28 text-right">Total</th>
                      <th className="px-3 py-2.5 w-24 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {invoice.line_items && invoice.line_items.length > 0 ? (
                      invoice.line_items.map((li, idx) => {
                        const isEditingThis = editingLineItemId === li.id;
                        if (isEditingThis) {
                          return (
                            <tr key={li.id} className="bg-indigo-50/50">
                              <td className="px-3 py-3 font-mono text-slate-400">{idx + 1}</td>
                              <td className="px-3 py-3 space-y-2">
                                <input
                                  type="text"
                                  value={liDescription}
                                  onChange={(e) => setLiDescription(e.target.value)}
                                  className="w-full px-2 py-1 border border-slate-300 rounded focus:ring-1 focus:ring-indigo-500"
                                />
                                <input
                                  type="text"
                                  required
                                  value={liReason}
                                  onChange={(e) => setLiReason(e.target.value)}
                                  placeholder="Correction reason (required)"
                                  className="w-full px-2 py-1 text-[11px] border border-amber-300 rounded bg-white"
                                />
                              </td>
                              <td className="px-3 py-3 text-right">
                                <input
                                  type="number"
                                  step="0.0001"
                                  min="0"
                                  value={liQuantity}
                                  onChange={(e) => setLiQuantity(e.target.value)}
                                  className="w-20 px-2 py-1 border border-slate-300 rounded text-right"
                                />
                              </td>
                              <td className="px-3 py-3 text-right">
                                <input
                                  type="number"
                                  step="0.01"
                                  min="0"
                                  value={liUnitPrice}
                                  onChange={(e) => setLiUnitPrice(e.target.value)}
                                  className="w-24 px-2 py-1 border border-slate-300 rounded text-right"
                                />
                              </td>
                              <td className="px-3 py-3 text-right">
                                <input
                                  type="number"
                                  step="0.01"
                                  min="0"
                                  value={liTax}
                                  onChange={(e) => setLiTax(e.target.value)}
                                  className="w-20 px-2 py-1 border border-slate-300 rounded text-right"
                                />
                              </td>
                              <td className="px-3 py-3 text-right">
                                <input
                                  type="number"
                                  step="0.01"
                                  min="0"
                                  value={liTotal}
                                  onChange={(e) => setLiTotal(e.target.value)}
                                  className="w-24 px-2 py-1 border border-slate-300 rounded text-right font-bold"
                                />
                              </td>
                              <td className="px-3 py-3 text-right space-x-1 whitespace-nowrap">
                                <button
                                  onClick={() => handleSaveLineItem(li.id)}
                                  disabled={saving || !liReason.trim()}
                                  className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                                  title="Save Changes"
                                >
                                  <Save className="w-4 h-4" />
                                </button>
                                <button
                                  onClick={() => setEditingLineItemId(null)}
                                  className="p-1 text-slate-400 hover:bg-slate-100 rounded"
                                  title="Cancel"
                                >
                                  <X className="w-4 h-4" />
                                </button>
                              </td>
                            </tr>
                          );
                        }

                        return (
                          <tr key={li.id} className="hover:bg-slate-50/60 transition">
                            <td className="px-3 py-3 font-mono text-slate-400">{idx + 1}</td>
                            <td className="px-3 py-3">
                              <div className="font-semibold text-slate-900">{li.description}</div>
                              {li.field_evidence?.relevant_text && (
                                <div className="text-[10px] text-slate-400 italic truncate max-w-md mt-0.5">
                                  "{li.field_evidence.relevant_text}"
                                </div>
                              )}
                            </td>
                            <td className="px-3 py-3 text-right font-mono text-slate-700">
                              {li.quantity !== null && li.quantity !== undefined ? li.quantity : '—'}
                            </td>
                            <td className="px-3 py-3 text-right font-mono text-slate-700">
                              {li.unit_price !== null && li.unit_price !== undefined
                                ? `${invoice.currency || '$'}${Number(li.unit_price).toFixed(2)}`
                                : '—'}
                            </td>
                            <td className="px-3 py-3 text-right font-mono text-slate-500">
                              {li.tax !== null && li.tax !== undefined
                                ? `${invoice.currency || '$'}${Number(li.tax).toFixed(2)}`
                                : '—'}
                            </td>
                            <td className="px-3 py-3 text-right font-mono font-bold text-slate-900">
                              {li.line_total !== null && li.line_total !== undefined
                                ? `${invoice.currency || '$'}${Number(li.line_total).toFixed(2)}`
                                : '—'}
                            </td>
                            <td className="px-3 py-3 text-right space-x-1 whitespace-nowrap">
                              <button
                                onClick={() => handleStartEditLineItem(li)}
                                className="p-1 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition"
                                title="Edit Line Item"
                              >
                                <Edit3 className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => {
                                  setDeletingLineItem(li);
                                  setDeleteReason('');
                                }}
                                className="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition"
                                title="Delete Line Item"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-slate-400 italic">
                          No line items found. Click "Add Line Item" to insert one.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Delete Line Item Modal Dialog */}
              {deletingLineItem && (
                <div className="fixed inset-0 z-60 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
                  <div className="bg-white rounded-xl shadow-xl p-5 border border-slate-200 max-w-md w-full space-y-3">
                    <h4 className="font-bold text-sm text-slate-900 flex items-center gap-1.5">
                      <Trash2 className="w-4 h-4 text-rose-600" />
                      Delete Line Item
                    </h4>
                    <p className="text-xs text-slate-600">
                      Are you sure you want to remove item "{deletingLineItem.description}"? This action will be permanently recorded in the audit history.
                    </p>
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Reason for Deletion <span className="text-rose-500">* (Required)</span>
                      </label>
                      <input
                        type="text"
                        required
                        value={deleteReason}
                        onChange={(e) => setDeleteReason(e.target.value)}
                        placeholder="e.g. Hallucinated total duplicated from header"
                        className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs focus:ring-1 focus:ring-rose-500 focus:outline-none"
                      />
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        onClick={() => setDeletingLineItem(null)}
                        className="px-3 py-1.5 border border-slate-300 rounded-lg text-xs font-semibold hover:bg-slate-100"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleDeleteLineItem}
                        disabled={saving || !deleteReason.trim()}
                        className="px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-semibold hover:bg-rose-700 disabled:opacity-50"
                      >
                        {saving ? 'Deleting...' : 'Confirm Delete'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: EVIDENCE INSPECTOR */}
          {activeTab === 'evidence' && (
            <div className="space-y-4">
              <div className="p-3 bg-indigo-50/50 rounded-lg border border-indigo-100 text-xs text-indigo-900">
                <span className="font-bold">Provenance & Evidence Citations:</span> Every extracted field is traced back to its supporting chunk quotation.
              </div>

              {invoice.field_evidence && Object.keys(invoice.field_evidence).length > 0 ? (
                <div className="space-y-3">
                  {Object.entries(invoice.field_evidence).map(([fieldKey, ev]: [string, any]) => {
                    const isExpanded = expandedCitationKey === fieldKey;
                    const citations = Array.isArray(ev) ? ev : [ev];
                    return (
                      <div key={fieldKey} className="border border-slate-200 rounded-xl overflow-hidden bg-slate-50/30">
                        <button
                          onClick={() => setExpandedCitationKey(isExpanded ? null : fieldKey)}
                          className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-slate-50 transition"
                        >
                          <div className="flex items-center space-x-2">
                            <span className="font-mono text-xs font-bold text-slate-800 uppercase tracking-wider">
                              {fieldKey}
                            </span>
                            <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200 font-medium">
                              Verified in Document
                            </span>
                          </div>
                          <div className="flex items-center text-slate-400">
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </div>
                        </button>

                        {isExpanded && (
                          <div className="px-4 pb-4 pt-1 space-y-2 border-t border-slate-100 bg-white text-xs">
                            {citations.map((cite: any, cIdx: number) => (
                              <div key={cIdx} className="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-1.5">
                                <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                                  <span>Chunk ID: {cite.source_chunk_id || 'unassigned'}</span>
                                  <span>
                                    {cite.page_number !== undefined && cite.page_number !== null
                                      ? `Page ${cite.page_number}`
                                      : cite.sheet_name
                                      ? `Sheet: ${cite.sheet_name}`
                                      : 'Document Content'}
                                  </span>
                                </div>
                                <blockquote className="text-slate-800 bg-white p-2.5 rounded border border-slate-200 italic font-serif text-xs">
                                  "{cite.relevant_text || cite.raw_value || 'Exact quotation unavailable'}"
                                </blockquote>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-8 text-center text-slate-400 italic text-xs">
                  No individual field evidence recorded for this invoice extraction.
                </div>
              )}
            </div>
          )}

          {/* TAB 4: AUDIT HISTORY */}
          {activeTab === 'audit' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Audit Trail & Change History
                </h4>
                <button
                  onClick={loadAudits}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold"
                >
                  Refresh Log
                </button>
              </div>

              {loadingAudits ? (
                <div className="p-8 text-center text-xs text-slate-500">Loading audit history...</div>
              ) : audits.length > 0 ? (
                <div className="space-y-3">
                  {audits.map((a) => (
                    <div key={a.id} className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-900 flex items-center gap-1.5">
                          <History className="w-3.5 h-3.5 text-indigo-600" />
                          {a.correction_type}
                        </span>
                        <span className="text-slate-400 text-[11px]">
                          {new Date(a.corrected_at).toLocaleString()}
                        </span>
                      </div>

                      <div className="text-slate-600">
                        <span className="font-medium text-slate-800">Reason:</span> {a.reason || <span className="italic text-slate-400">None provided</span>}
                      </div>

                      {a.corrected_by && (
                        <div className="text-[11px] text-slate-500">
                          <span className="font-medium text-slate-700">Corrected By:</span> {a.corrected_by}
                        </div>
                      )}

                      {/* Changed values table */}
                      {a.changed_fields && a.changed_fields.length > 0 && (
                        <div className="pt-2 border-t border-slate-200/80">
                          <div className="text-[11px] font-semibold text-slate-500 mb-1">Modified Values:</div>
                          <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                            <div className="p-2 bg-rose-50/50 rounded border border-rose-100 text-rose-900 truncate">
                              <span className="font-semibold text-rose-700 block">Previous:</span>
                              {JSON.stringify(a.previous_values, null, 2)}
                            </div>
                            <div className="p-2 bg-emerald-50/50 rounded border border-emerald-100 text-emerald-900 truncate">
                              <span className="font-semibold text-emerald-700 block">New:</span>
                              {JSON.stringify(a.new_values, null, 2)}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-slate-400 italic">
                  No manual corrections have been recorded for this invoice yet.
                </div>
              )}
            </div>
          )}

          {/* TAB 5: VALIDATION & DUPLICATE DISCREPANCIES */}
          {activeTab === 'validation' && (
            <div className="space-y-4">
              {/* Summary Metric Cards */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-center">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase">Total Issues</div>
                  <div className="text-xl font-bold text-slate-800 mt-1">
                    {invoice.validation_issues?.length || 0}
                  </div>
                </div>
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-center">
                  <div className="text-[11px] font-semibold text-rose-700 uppercase">Errors</div>
                  <div className="text-xl font-bold text-rose-800 mt-1">
                    {invoice.validation_issues?.filter((i) => !i.resolved && i.severity === 'error').length || 0}
                  </div>
                </div>
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-center">
                  <div className="text-[11px] font-semibold text-amber-700 uppercase">Warnings</div>
                  <div className="text-xl font-bold text-amber-800 mt-1">
                    {invoice.validation_issues?.filter((i) => !i.resolved && i.severity === 'warning').length || 0}
                  </div>
                </div>
                <div className="p-3 bg-sky-50 border border-sky-200 rounded-xl text-center">
                  <div className="text-[11px] font-semibold text-sky-700 uppercase">Info</div>
                  <div className="text-xl font-bold text-sky-800 mt-1">
                    {invoice.validation_issues?.filter((i) => !i.resolved && i.severity === 'info').length || 0}
                  </div>
                </div>
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-center">
                  <div className="text-[11px] font-semibold text-emerald-700 uppercase">Resolved</div>
                  <div className="text-xl font-bold text-emerald-800 mt-1">
                    {invoice.validation_issues?.filter((i) => i.resolved).length || 0}
                  </div>
                </div>
              </div>

              {/* Controls bar */}
              <div className="flex items-center justify-between pt-2">
                <div className="flex items-center space-x-2 text-xs">
                  <span className="font-semibold text-slate-600">Filter:</span>
                  {(['all', 'unresolved', 'resolved'] as const).map((mode) => (
                    <button
                      key={mode}
                      onClick={() => setIssueFilter(mode)}
                      className={`px-3 py-1 rounded-lg text-xs font-semibold capitalize transition ${
                        issueFilter === mode
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
                <button
                  onClick={handleRevalidate}
                  disabled={revalidating}
                  className="inline-flex items-center px-3 py-1.5 text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 rounded-lg transition disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${revalidating ? 'animate-spin' : ''}`} />
                  Re-run Validation
                </button>
              </div>

              {/* Issues List */}
              {(() => {
                const filteredIssues = (invoice.validation_issues || []).filter((issue) => {
                  if (issueFilter === 'unresolved') return !issue.resolved;
                  if (issueFilter === 'resolved') return issue.resolved;
                  return true;
                });

                if (filteredIssues.length === 0) {
                  return (
                    <div className="p-8 text-center bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                      <CheckCircle className="w-8 h-8 text-emerald-500 mx-auto" />
                      <div className="text-sm font-semibold text-slate-800">
                        No {issueFilter !== 'all' ? issueFilter : ''} validation issues detected!
                      </div>
                      <p className="text-xs text-slate-500">
                        Deterministic financial arithmetic and field checks passed for this invoice.
                      </p>
                    </div>
                  );
                }

                return (
                  <div className="space-y-3">
                    {filteredIssues.map((issue) => (
                      <div
                        key={issue.id}
                        className={`p-4 rounded-xl border text-xs space-y-2 transition ${
                          issue.resolved
                            ? 'bg-slate-50/60 border-slate-200 opacity-75'
                            : issue.severity === 'error'
                            ? 'bg-rose-50/40 border-rose-200'
                            : issue.severity === 'warning'
                            ? 'bg-amber-50/40 border-amber-200'
                            : 'bg-sky-50/40 border-sky-200'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2">
                            <span
                              className={`px-2 py-0.5 rounded-full font-bold uppercase text-[10px] border ${
                                issue.severity === 'error'
                                  ? 'bg-rose-100 text-rose-800 border-rose-200'
                                  : issue.severity === 'warning'
                                  ? 'bg-amber-100 text-amber-800 border-amber-200'
                                  : 'bg-sky-100 text-sky-800 border-sky-200'
                              }`}
                            >
                              {issue.severity}
                            </span>
                            <span className="font-mono font-bold text-slate-900">
                              {issue.field_name}
                            </span>
                            <span className="font-mono text-[11px] text-slate-400">
                              [{issue.issue_type}]
                            </span>
                          </div>

                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                              issue.resolved
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-slate-200 text-slate-700'
                            }`}
                          >
                            {issue.resolved ? 'Resolved' : 'Active'}
                          </span>
                        </div>

                        <p className="text-slate-800 font-medium">{issue.description}</p>

                        {(issue.expected_value || issue.observed_value) && (
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 font-mono text-[11px] pt-1">
                            {issue.expected_value && (
                              <div className="p-2 bg-white rounded border border-slate-200">
                                <span className="font-semibold text-slate-500 block text-[10px]">Expected:</span>
                                <span className="text-emerald-700">{issue.expected_value}</span>
                              </div>
                            )}
                            {issue.observed_value && (
                              <div className="p-2 bg-white rounded border border-slate-200">
                                <span className="font-semibold text-slate-500 block text-[10px]">Observed:</span>
                                <span className="text-rose-700">{issue.observed_value}</span>
                              </div>
                            )}
                          </div>
                        )}

                        {issue.resolved && (
                          <div className="p-2 bg-emerald-50 rounded border border-emerald-200 text-[11px] text-emerald-900 space-y-0.5">
                            <div>
                              <span className="font-semibold">Resolved:</span>{' '}
                              {issue.resolved_at ? new Date(issue.resolved_at).toLocaleString() : ''}{' '}
                              {issue.resolved_by ? `by ${issue.resolved_by}` : ''}
                            </div>
                            {issue.resolution_notes && (
                              <div className="italic">"{issue.resolution_notes}"</div>
                            )}
                          </div>
                        )}

                        {/* Inline Actions */}
                        <div className="pt-2 border-t border-slate-200/60 flex items-center justify-end space-x-2">
                          {!issue.resolved ? (
                            resolvingIssueId === issue.id ? (
                              <div className="w-full bg-white p-3 rounded-lg border border-indigo-200 space-y-2">
                                <div className="font-semibold text-slate-800 text-xs">Resolve Discrepancy</div>
                                <input
                                  type="text"
                                  value={resolveBy}
                                  onChange={(e) => setResolveBy(e.target.value)}
                                  placeholder="Operator / Auditor name (optional)"
                                  className="w-full px-2.5 py-1.5 border border-slate-300 rounded text-xs"
                                />
                                <input
                                  type="text"
                                  value={resolveNotes}
                                  onChange={(e) => setResolveNotes(e.target.value)}
                                  placeholder="Resolution explanation (e.g. Verified legitimate fee)"
                                  className="w-full px-2.5 py-1.5 border border-slate-300 rounded text-xs"
                                />
                                <div className="flex justify-end gap-2">
                                  <button
                                    onClick={() => setResolvingIssueId(null)}
                                    className="px-2.5 py-1 border border-slate-300 rounded text-xs font-semibold hover:bg-slate-50"
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    onClick={() => handleResolveIssue(issue.id)}
                                    className="px-3 py-1 bg-emerald-600 text-white rounded text-xs font-semibold hover:bg-emerald-700"
                                  >
                                    Confirm Resolve
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <button
                                onClick={() => {
                                  setResolvingIssueId(issue.id);
                                  setResolveNotes('');
                                  setResolveBy('');
                                }}
                                className="px-3 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 rounded text-xs font-semibold transition"
                              >
                                Mark as Resolved
                              </button>
                            )
                          ) : (
                            reopeningIssueId === issue.id ? (
                              <div className="w-full bg-white p-3 rounded-lg border border-amber-200 space-y-2">
                                <div className="font-semibold text-slate-800 text-xs">Reopen Discrepancy</div>
                                <input
                                  type="text"
                                  value={reopenBy}
                                  onChange={(e) => setReopenBy(e.target.value)}
                                  placeholder="Operator / Auditor name (optional)"
                                  className="w-full px-2.5 py-1.5 border border-slate-300 rounded text-xs"
                                />
                                <input
                                  type="text"
                                  value={reopenNotes}
                                  onChange={(e) => setReopenNotes(e.target.value)}
                                  placeholder="Reason for reopening discrepancy"
                                  className="w-full px-2.5 py-1.5 border border-slate-300 rounded text-xs"
                                />
                                <div className="flex justify-end gap-2">
                                  <button
                                    onClick={() => setReopeningIssueId(null)}
                                    className="px-2.5 py-1 border border-slate-300 rounded text-xs font-semibold hover:bg-slate-50"
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    onClick={() => handleReopenIssue(issue.id)}
                                    className="px-3 py-1 bg-amber-600 text-white rounded text-xs font-semibold hover:bg-amber-700"
                                  >
                                    Confirm Reopen
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <button
                                onClick={() => {
                                  setReopeningIssueId(issue.id);
                                  setReopenNotes('');
                                  setReopenBy('');
                                }}
                                className="px-3 py-1 bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 rounded text-xs font-semibold transition"
                              >
                                Reopen Issue
                              </button>
                            )
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>
          )}
        </div>

        {/* Modal Bottom Footer */}
        <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
          <div>
            Document ID: <span className="font-mono text-slate-700">{invoice.document_id}</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-white border border-slate-300 text-slate-700 font-semibold rounded-lg hover:bg-slate-100 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
