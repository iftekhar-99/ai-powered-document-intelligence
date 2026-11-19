import React, { useRef, useState } from 'react';
import { UploadBatchResponse } from '../types';
import { uploadDocuments } from '../services/api';
import {
  UploadCloud,
  AlertTriangle,
  FileUp,
  X,
  CheckCircle2,
  File,
} from 'lucide-react';

interface DocumentUploadZoneProps {
  onUploadSuccess: (batch: UploadBatchResponse) => void;
}

export const DocumentUploadZone: React.FC<DocumentUploadZoneProps> = ({
  onUploadSuccess,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState<UploadBatchResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const supportedFormats = [
    { label: 'PDF', ext: '.pdf' },
    { label: 'Images', ext: '.jpg, .png, .tiff' },
    { label: 'Spreadsheets', ext: '.xlsx, .xls, .csv' },
  ];

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(Array.from(e.target.files));
    }
  };

  const addFiles = (newFiles: File[]) => {
    setSelectedFiles((prev) => [...prev, ...newFiles]);
    setUploadResult(null);
    setErrorMessage(null);
  };

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setUploading(true);
    setUploadProgress(0);
    setErrorMessage(null);

    try {
      const result = await uploadDocuments(selectedFiles, (percent) => {
        setUploadProgress(percent);
      });
      setUploadResult(result);
      setSelectedFiles([]);
      onUploadSuccess(result);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Failed to upload files.');
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-100 gap-2">
        <div>
          <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
            <UploadCloud className="w-5 h-5 text-sky-600" />
            Upload Financial Documents
          </h2>
          <p className="text-xs text-slate-500">
            Batch upload invoices, bills, and spreadsheets for extraction and indexing
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {supportedFormats.map((f) => (
            <span
              key={f.label}
              className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-700"
            >
              <strong className="mr-1">{f.label}:</strong> {f.ext}
            </span>
          ))}
        </div>
      </div>

      {/* Drag & Drop Target */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          isDragging
            ? 'border-sky-500 bg-sky-50/50'
            : 'border-slate-300 hover:border-sky-400 bg-slate-50/60'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.jpg,.jpeg,.png,.tiff,.tif,.xls,.xlsx,.csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        <div className="flex flex-col items-center justify-center space-y-2">
          <div className="p-3 bg-sky-100 text-sky-600 rounded-full">
            <FileUp className="w-6 h-6" />
          </div>
          <p className="text-sm font-medium text-slate-800">
            Drag & drop financial documents here, or{' '}
            <span className="text-sky-600 underline">browse files</span>
          </p>
          <p className="text-xs text-slate-400">
            Supports multi-page PDF (~1,000 pages), JPG, PNG, TIFF, XLS, XLSX, CSV (Max 100MB per file)
          </p>
        </div>
      </div>

      {/* Selected Files Queue */}
      {selectedFiles.length > 0 && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between text-xs text-slate-600">
            <span className="font-medium">
              Files ready to upload ({selectedFiles.length})
            </span>
            <span>
              Total size:{' '}
              {formatFileSize(
                selectedFiles.reduce((acc, f) => acc + f.size, 0)
              )}
            </span>
          </div>

          <div className="max-h-48 overflow-y-auto divide-y divide-slate-100 border border-slate-200 rounded-lg">
            {selectedFiles.map((file, idx) => (
              <div
                key={`${file.name}-${idx}`}
                className="flex items-center justify-between p-2.5 text-xs bg-slate-50 hover:bg-slate-100 transition"
              >
                <div className="flex items-center space-x-2 truncate pr-2">
                  <File className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  <span className="font-medium text-slate-800 truncate">
                    {file.name}
                  </span>
                  <span className="text-slate-400 font-mono">
                    ({formatFileSize(file.size)})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(idx);
                  }}
                  disabled={uploading}
                  className="text-slate-400 hover:text-rose-500 p-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          {/* Upload Progress Bar */}
          {uploading && (
            <div className="space-y-1.5 pt-1">
              <div className="flex justify-between text-xs text-slate-600">
                <span>Uploading batch...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                <div
                  className="bg-sky-600 h-2 rounded-full transition-all duration-200"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setSelectedFiles([])}
              disabled={uploading}
              className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition disabled:opacity-50"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={uploading}
              className="px-4 py-1.5 text-xs font-medium text-white bg-sky-600 hover:bg-sky-700 rounded-lg transition disabled:opacity-50 flex items-center gap-1.5"
            >
              {uploading ? 'Processing...' : `Upload ${selectedFiles.length} File(s)`}
            </button>
          </div>
        </div>
      )}

      {/* Error Message */}
      {errorMessage && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-700 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Upload Error</p>
            <p className="mt-0.5">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Batch Feedback */}
      {uploadResult && (
        <div className="space-y-3 pt-2">
          {uploadResult.total_accepted > 0 && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800">
              <div className="flex items-center gap-1.5 font-semibold text-emerald-900 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                Successfully accepted {uploadResult.total_accepted} document(s)
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-emerald-700">
                {uploadResult.accepted.map((doc) => (
                  <li key={doc.id} className="truncate">
                    <span className="font-medium">{doc.original_filename}</span>{' '}
                    <span className="text-[11px] opacity-80">
                      ({formatFileSize(doc.file_size)} • {doc.status})
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {uploadResult.total_rejected > 0 && (
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
              <div className="flex items-center gap-1.5 font-semibold text-amber-900 mb-1">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                Rejected {uploadResult.total_rejected} document(s)
              </div>
              <ul className="divide-y divide-amber-100">
                {uploadResult.rejected.map((r, i) => (
                  <li key={i} className="py-1">
                    <span className="font-medium text-amber-900">{r.filename}</span>:{' '}
                    <span className="text-amber-700">{r.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
