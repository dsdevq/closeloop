import { ChangeEvent, useRef, useState } from 'react';
import { apiFetch } from '../api';

type RowError = {
  row_index: number;
  field: string;
  value: string;
  rule: string;
};

type ImportResult = {
  total: number;
  inserted: number;
  skipped: number;
  failed: RowError[];
};

type Props = {
  entity: 'contacts' | 'deals' | 'activities';
  onImportDone?: () => void;
};

export function ImportExportBar({ entity, onImportDone }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    setSelectedFile(e.target.files?.[0] ?? null);
    setResult(null);
    setError(null);
  }

  async function handleImport() {
    if (!selectedFile) return;
    const formData = new FormData();
    formData.append('file', selectedFile);
    setImporting(true);
    setResult(null);
    setError(null);
    try {
      const response = await apiFetch(`/${entity}/import`, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { detail?: string };
        setError(data.detail ?? `Import failed (${response.status})`);
        return;
      }
      const importResult = (await response.json()) as ImportResult;
      setResult(importResult);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onImportDone?.();
    } catch {
      setError('Network error during import');
    } finally {
      setImporting(false);
    }
  }

  async function handleExport(format: 'csv' | 'xlsx') {
    setError(null);
    try {
      const response = await apiFetch(`/${entity}/export?format=${format}`);
      if (!response.ok) {
        setError(`Export failed (${response.status})`);
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${entity}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError('Export failed');
    }
  }

  return (
    <div className="panel mb-4 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx"
          className="text-sm text-slate-500 file:mr-2 file:cursor-pointer file:rounded file:border file:border-slate-300 file:bg-white file:px-2.5 file:py-1 file:text-xs file:font-semibold file:text-slate-700 file:transition file:hover:border-blue-500 file:hover:text-blue-700"
          onChange={handleFileChange}
        />
        <button
          className="primary-button"
          disabled={!selectedFile || importing}
          onClick={() => {
            void handleImport();
          }}
          type="button"
        >
          {importing ? 'Importing…' : 'Import'}
        </button>
        <div className="ml-auto flex gap-2">
          <button
            className="secondary-button"
            onClick={() => {
              void handleExport('csv');
            }}
            type="button"
          >
            Export CSV
          </button>
          <button
            className="secondary-button"
            onClick={() => {
              void handleExport('xlsx');
            }}
            type="button"
          >
            Export Excel
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-2">
          <p className="text-sm text-slate-700">
            Import complete — {result.total} rows: {result.inserted} inserted, {result.skipped} skipped
            {result.failed.length > 0 && `, ${result.failed.length} failed`}
          </p>
          {result.failed.length > 0 && (
            <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-2">
              <p className="mb-1 text-xs font-bold uppercase text-amber-700">Failed rows</p>
              <ul className="space-y-0.5">
                {result.failed.map((err) => (
                  <li key={`${err.row_index}-${err.field}`} className="text-xs text-amber-800">
                    Row {err.row_index}:{' '}
                    <span className="font-semibold">{err.field}</span> — {err.rule}
                    {err.value ? ` (got: ${err.value})` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
