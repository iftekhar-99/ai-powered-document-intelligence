import React, { useState, useEffect } from 'react';
import { DashboardMetrics } from '../types';
import { fetchDashboardMetrics } from '../services/api';
import {
  FileText,
  AlertTriangle,
  Receipt,
  Edit3,
  RefreshCw,
  ArrowRight,
  Cpu,
  Layers,
} from 'lucide-react';

interface DashboardPageProps {
  onNavigate: (view: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ onNavigate }) => {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadMetrics = async () => {
    setLoading(true);
    try {
      const data = await fetchDashboardMetrics();
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load dashboard metrics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMetrics();
  }, []);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <Layers className="w-6 h-6 text-indigo-600" />
            Executive Intelligence Dashboard
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Real-time pipeline metrics, automated invoice extraction accuracy, and human-in-the-loop audit logs.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={loadMetrics}
            disabled={loading}
            className="inline-flex items-center px-3.5 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50 transition shadow-xs disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => onNavigate('documents')}
            className="inline-flex items-center px-3.5 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition shadow-xs"
          >
            <FileText className="w-3.5 h-3.5 mr-1.5" />
            Upload Document
          </button>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Documents */}
        <div
          onClick={() => onNavigate('documents')}
          className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-indigo-300 transition cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Documents</span>
            <div className="p-2 bg-slate-100 rounded-lg text-slate-600 group-hover:bg-indigo-50 group-hover:text-indigo-600 transition">
              <FileText className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-slate-900 font-mono">
              {metrics ? metrics.total_documents : '—'}
            </span>
            <span className="text-[11px] text-emerald-600 font-medium">
              {metrics ? `${metrics.processed_documents} processed` : ''}
            </span>
          </div>
        </div>

        {/* Total Invoices */}
        <div
          onClick={() => onNavigate('invoices')}
          className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-indigo-300 transition cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Invoices Extracted</span>
            <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600 transition">
              <Receipt className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-indigo-700 font-mono">
              {metrics ? metrics.total_invoices : '—'}
            </span>
            <span className="text-[11px] text-slate-500">Gemini Flash-Lite</span>
          </div>
        </div>

        {/* Needs Review */}
        <div
          onClick={() => onNavigate('review')}
          className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-amber-300 transition cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Needs Review</span>
            <div className="p-2 bg-amber-50 rounded-lg text-amber-600 transition">
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-amber-700 font-mono">
              {metrics ? metrics.needs_review_invoices : '—'}
            </span>
            <span className="text-[11px] text-amber-600 font-semibold flex items-center gap-1">
              Action Required <ArrowRight className="w-3 h-3" />
            </span>
          </div>
        </div>

        {/* Manually Corrected */}
        <div
          onClick={() => onNavigate('invoices')}
          className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs hover:border-indigo-300 transition cursor-pointer group"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Human Corrected</span>
            <div className="p-2 bg-blue-50 rounded-lg text-blue-600 transition">
              <Edit3 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-blue-800 font-mono">
              {metrics ? metrics.manually_corrected_invoices : '—'}
            </span>
            <span className="text-[11px] text-slate-500 font-medium">Audit verified</span>
          </div>
        </div>
      </div>

      {/* Two Column Grid: Recent Extraction Runs & Recent Manual Corrections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Extraction Runs */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <h3 className="font-bold text-xs text-slate-700 uppercase tracking-wider flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-600" />
              Recent AI Extraction Runs
            </h3>
            <button
              onClick={() => onNavigate('history')}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold"
            >
              View All History →
            </button>
          </div>
          <div className="divide-y divide-slate-100">
            {metrics?.recent_extraction_runs && metrics.recent_extraction_runs.length > 0 ? (
              metrics.recent_extraction_runs.slice(0, 5).map((r) => (
                <div key={r.id} className="p-4 text-xs flex items-center justify-between hover:bg-slate-50/50 transition">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold text-slate-900 font-mono">{r.model_name}</span>
                      {r.status === 'completed' ? (
                        <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          Completed
                        </span>
                      ) : r.status === 'failed' ? (
                        <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                          Failed
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">
                          {r.status}
                        </span>
                      )}
                    </div>
                    <div className="text-slate-500 text-[11px]">
                      Contexts: {r.successful_contexts} / {r.total_contexts} • Latency:{' '}
                      {r.processing_time_ms ? `${(r.processing_time_ms / 1000).toFixed(2)}s` : '—'}
                    </div>
                  </div>
                  <div className="text-right text-[11px] text-slate-400">
                    {new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-xs text-slate-400 italic">No extraction runs recorded yet.</div>
            )}
          </div>
        </div>

        {/* Recent Manual Corrections */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <h3 className="font-bold text-xs text-slate-700 uppercase tracking-wider flex items-center gap-2">
              <Edit3 className="w-4 h-4 text-indigo-600" />
              Recent Human Adjustments
            </h3>
            <button
              onClick={() => onNavigate('invoices')}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold"
            >
              Review Invoices →
            </button>
          </div>
          <div className="divide-y divide-slate-100">
            {metrics?.recent_corrections && metrics.recent_corrections.length > 0 ? (
              metrics.recent_corrections.slice(0, 5).map((c) => (
                <div key={c.id} className="p-4 text-xs space-y-1 hover:bg-slate-50/50 transition">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-900 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-600"></span>
                      {c.correction_type}
                    </span>
                    <span className="text-slate-400 text-[11px]">
                      {new Date(c.corrected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <div className="text-slate-600 text-[11px]">
                    <span className="font-semibold text-slate-700">Reason:</span> {c.reason || 'No justification logged'}
                  </div>
                  {c.corrected_by && (
                    <div className="text-[10px] text-slate-400">
                      by <span className="text-slate-600 font-medium">{c.corrected_by}</span>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-xs text-slate-400 italic">
                No manual corrections logged yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
