import React, { useState, useEffect } from 'react';
import { DocumentItem, ExtractionRunItem } from '../types';
import {
  triggerInvoiceExtraction,
  fetchExtractionRun,
} from '../services/api';
import {
  X,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  ArrowRight,
} from 'lucide-react';

interface ExtractionRunModalProps {
  document: DocumentItem;
  onClose: () => void;
  onViewInvoices: (documentId: string) => void;
}

export const ExtractionRunModal: React.FC<ExtractionRunModalProps> = ({
  document,
  onClose,
  onViewInvoices,
}) => {
  const [run, setRun] = useState<ExtractionRunItem | null>(null);
  const [starting, setStarting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const startExtraction = async () => {
    setStarting(true);
    setErrorMessage(null);
    try {
      const response = await triggerInvoiceExtraction(document.id);
      const initialRun = await fetchExtractionRun(response.extraction_run_id);
      setRun(initialRun);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to initiate invoice extraction.');
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    startExtraction();
  }, [document.id]);

  useEffect(() => {
    if (!run || run.status === 'completed' || run.status === 'failed') {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const updated = await fetchExtractionRun(run.id);
        setRun(updated);
      } catch (err) {
        console.error('Error polling extraction run:', err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [run]);

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl border border-slate-200 w-full max-w-lg p-6 space-y-5 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-indigo-50 text-indigo-700 rounded-lg">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-slate-900">AI Invoice Extraction</h3>
              <p className="text-[11px] text-slate-500 truncate max-w-xs">{document.original_filename}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {errorMessage && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 text-xs flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 mt-0.5 flex-shrink-0" />
            <div>
              <div className="font-semibold">Extraction Failed to Dispatch</div>
              <div>{errorMessage}</div>
            </div>
          </div>
        )}

        {starting && !run && (
          <div className="py-8 text-center space-y-3">
            <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
            <p className="text-xs text-slate-600 font-medium">Contacting Gemini extraction orchestrator...</p>
          </div>
        )}

        {run && (
          <div className="space-y-4">
            {/* Status Indicator */}
            <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Run Status</span>
                {run.status === 'completed' ? (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                    <CheckCircle2 className="w-3.5 h-3.5 mr-1 text-emerald-600" /> Completed
                  </span>
                ) : run.status === 'failed' ? (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">
                    <AlertTriangle className="w-3.5 h-3.5 mr-1 text-rose-600" /> Failed
                  </span>
                ) : (
                  <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">
                    <RefreshCw className="w-3.5 h-3.5 mr-1 text-indigo-600 animate-spin" /> Processing
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs text-slate-600 pt-2 border-t border-slate-200/60">
                <div>
                  <span className="text-slate-400 block text-[10px]">Model Provider</span>
                  <span className="font-semibold text-slate-800 font-mono">{run.provider} ({run.model_name})</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Contexts Processed</span>
                  <span className="font-semibold text-slate-800 font-mono">
                    {run.successful_contexts} / {run.total_contexts}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Processing Latency</span>
                  <span className="font-semibold text-slate-800 font-mono">
                    {run.processing_time_ms ? `${(run.processing_time_ms / 1000).toFixed(2)}s` : 'Processing...'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Prompt Version</span>
                  <span className="font-semibold text-slate-800 font-mono">{run.prompt_version}</span>
                </div>
              </div>

              {run.error_message && (
                <div className="p-2.5 bg-rose-100/50 rounded border border-rose-200 text-rose-800 text-[11px]">
                  <span className="font-bold">Error:</span> {run.error_message}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end space-x-3 pt-2">
              <button
                onClick={onClose}
                className="px-4 py-2 border border-slate-300 text-slate-700 font-semibold rounded-lg text-xs hover:bg-slate-50 transition"
              >
                Close
              </button>
              {run.status === 'completed' && (
                <button
                  onClick={() => {
                    onClose();
                    onViewInvoices(document.id);
                  }}
                  className="inline-flex items-center px-4 py-2 bg-indigo-600 text-white font-semibold rounded-lg text-xs hover:bg-indigo-700 transition shadow-sm"
                >
                  View Extracted Invoices
                  <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
