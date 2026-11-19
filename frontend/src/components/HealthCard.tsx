import React from 'react';
import { HealthResponse } from '../types';
import {
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Server,
  Database,
  Cpu,
  FileText,
  FileSpreadsheet,
  Scan,
} from 'lucide-react';

interface HealthCardProps {
  health: HealthResponse | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

export const HealthCard: React.FC<HealthCardProps> = ({
  health,
  loading,
  error,
  onRefresh,
}) => {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
      <div className="p-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center space-x-3">
            <div
              className={`p-2.5 rounded-lg ${
                error
                  ? 'bg-rose-50 text-rose-600'
                  : 'bg-emerald-50 text-emerald-600'
              }`}
            >
              {error ? (
                <AlertCircle className="w-6 h-6" />
              ) : (
                <CheckCircle2 className="w-6 h-6" />
              )}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900">
                Backend System Health & Capabilities
              </h2>
              <p className="text-sm text-slate-500">
                Live inspection of database, workers, OCR engine and document parsers
              </p>
            </div>
          </div>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition disabled:opacity-50"
            title="Refresh status"
          >
            <RefreshCw
              className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`}
            />
            Refresh
          </button>
        </div>

        {loading && !health && (
          <div className="py-8 text-center text-slate-500">
            <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin text-sky-500" />
            <p className="text-sm">Connecting to backend health endpoint...</p>
          </div>
        )}

        {error && (
          <div className="mt-4 p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-700">
            <p className="font-medium text-sm">Failed to connect to backend service</p>
            <p className="text-xs mt-1">{error}</p>
            <p className="text-xs mt-2 text-rose-600">
              Ensure FastAPI is running on{' '}
              <code className="bg-rose-100 px-1 py-0.5 rounded font-mono">
                http://localhost:8000
              </code>
              .
            </p>
          </div>
        )}

        {health && !error && (
          <div className="mt-5 space-y-4">
            {/* Top Metric Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-xs font-medium text-slate-500 block">
                  Overall Status
                </span>
                <span className="text-sm font-semibold text-emerald-600 uppercase tracking-wide">
                  {health.status}
                </span>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-xs font-medium text-slate-500 block">
                  Environment
                </span>
                <span className="text-sm font-semibold text-slate-800 capitalize">
                  {health.environment}
                </span>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-xs font-medium text-slate-500 block">
                  API Version
                </span>
                <span className="text-sm font-semibold text-slate-800 font-mono">
                  v{health.version}
                </span>
              </div>
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-xs font-medium text-slate-500 block">
                  Background Tasks
                </span>
                <span className="text-sm font-semibold text-sky-700 font-mono uppercase">
                  {health.capabilities?.background_processing_mode || 'inline'}
                </span>
              </div>
            </div>

            {/* Service Connectivity Grid */}
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                Live Service Connectivity
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div className="flex items-center space-x-2 text-xs text-slate-700 bg-slate-50 px-3 py-2 rounded-md border border-slate-100">
                  <Server className="w-4 h-4 text-sky-500 flex-shrink-0" />
                  <span className="font-semibold">FastAPI:</span>
                  <span className="text-emerald-600 font-medium">
                    {health.services.api || 'online'}
                  </span>
                </div>
                <div className="flex items-center space-x-2 text-xs text-slate-700 bg-slate-50 px-3 py-2 rounded-md border border-slate-100 truncate">
                  <Database className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                  <span className="font-semibold">Database:</span>
                  <span className="text-slate-800 font-mono truncate">
                    {health.services.database || 'active'}
                  </span>
                </div>
                <div className="flex items-center space-x-2 text-xs text-slate-700 bg-slate-50 px-3 py-2 rounded-md border border-slate-100 truncate">
                  <Cpu className="w-4 h-4 text-amber-500 flex-shrink-0" />
                  <span className="font-semibold">Redis:</span>
                  <span className="text-slate-700 font-mono truncate">
                    {health.services.redis || 'offline'}
                  </span>
                </div>
              </div>
            </div>

            {/* Document Processing Engine Capabilities */}
            {health.capabilities && (
              <div>
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  Document Engine Capabilities
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                  {/* PDF Digital Parser */}
                  <div className="p-2.5 rounded-lg border border-slate-200 bg-white flex items-start gap-2">
                    <FileText className="w-4 h-4 text-sky-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-slate-800">
                        PDF Digital Parser (PyMuPDF)
                      </div>
                      <div className="text-[11px] text-emerald-600 font-medium mt-0.5">
                        Active & Streaming (~1,000 pages ready)
                      </div>
                    </div>
                  </div>

                  {/* Tesseract OCR Engine */}
                  <div className="p-2.5 rounded-lg border border-slate-200 bg-white flex items-start gap-2">
                    <Scan className="w-4 h-4 text-purple-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-slate-800">
                        Tesseract OCR Engine
                      </div>
                      {health.capabilities.tesseract_available ? (
                        <div className="text-[11px] text-emerald-600 font-medium mt-0.5">
                          Binary detected ({health.capabilities.ocr_languages.join(', ') || 'eng'})
                        </div>
                      ) : (
                        <div className="text-[11px] text-amber-600 font-medium mt-0.5">
                          Binary absent (graceful fallback active)
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Spreadsheets & CSV */}
                  <div className="p-2.5 rounded-lg border border-slate-200 bg-white flex items-start gap-2">
                    <FileSpreadsheet className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-slate-800">
                        Spreadsheets & Tabular
                      </div>
                      <div className="text-[11px] text-emerald-600 font-medium mt-0.5">
                        XLSX, XLS, CSV (Hidden sheets: {health.capabilities.include_hidden_sheets ? 'Included' : 'Skipped'})
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="text-xs text-slate-400 text-right pt-2 border-t border-slate-100">
              Last check: {new Date(health.timestamp).toLocaleTimeString()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
