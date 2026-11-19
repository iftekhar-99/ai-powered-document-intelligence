import React, { useState, useEffect } from 'react';
import { DashboardMetrics, ExtractionRunItem } from '../types';
import { fetchDashboardMetrics } from '../services/api';
import {
  History,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';

export const ProcessingHistoryPage: React.FC = () => {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await fetchDashboardMetrics();
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load processing history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <History className="w-6 h-6 text-indigo-600" />
            Extraction Run History
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Historical trace of Gemini LLM extraction jobs, contexts segmented, latency, and tokens used.
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center px-3.5 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-semibold rounded-lg hover:bg-slate-50 transition shadow-xs disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
          <h3 className="font-bold text-xs text-slate-700 uppercase tracking-wider">Recent Extraction Runs</h3>
          <span className="text-xs text-slate-500 font-mono">
            {metrics?.recent_extraction_runs?.length || 0} runs recorded
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50/50 text-slate-600 font-semibold border-b border-slate-200">
              <tr>
                <th className="px-4 py-3">Run ID</th>
                <th className="px-4 py-3">Document ID</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3 text-center">Status</th>
                <th className="px-4 py-3 text-right">Contexts</th>
                <th className="px-4 py-3 text-right">Processing Time</th>
                <th className="px-4 py-3 text-right">Created At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto text-indigo-600 mb-2" />
                    Loading extraction runs...
                  </td>
                </tr>
              ) : !metrics?.recent_extraction_runs || metrics.recent_extraction_runs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-400 italic">
                    No extraction runs recorded yet.
                  </td>
                </tr>
              ) : (
                metrics.recent_extraction_runs.map((r: ExtractionRunItem) => (
                  <tr key={r.id} className="hover:bg-slate-50/70 transition">
                    <td className="px-4 py-3 font-mono font-medium text-slate-900">
                      {r.id.slice(0, 8)}...
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-600">
                      {r.document_id.slice(0, 8)}...
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-700">
                      {r.provider} • {r.model_name}
                    </td>
                    <td className="px-4 py-3 text-center whitespace-nowrap">
                      {r.status === 'completed' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3 mr-1" /> Completed
                        </span>
                      ) : r.status === 'failed' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                          <AlertTriangle className="w-3 h-3 mr-1" /> Failed
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">
                          <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> {r.status}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-800">
                      {r.successful_contexts} / {r.total_contexts}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-600">
                      {r.processing_time_ms ? `${(r.processing_time_ms / 1000).toFixed(2)}s` : '—'}
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500 whitespace-nowrap">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
