import { type FormEvent, useRef, useState } from 'react';
import { apiFetch } from '../../lib/api';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

export function ImportModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: (count: number) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState('');
  const [result, setResult] = useState<{ imported: number; errors: { row: number; reason: string }[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) { setError('Please select a CSV file'); return; }
    setBusy(true);
    setError('');
    try {
      const csv = await file.text();
      const res = await apiFetch('/contacts/import', {
        method: 'POST',
        body: JSON.stringify({ csv }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Import failed');
        return;
      }
      setResult(data);
      if (data.errors?.length === 0) {
        onSuccess(data.imported);
      }
    } catch {
      setError('Import failed');
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <ModalShell title="Import Complete" onClose={onClose}>
        <div className="space-y-3">
          <p className="text-sm text-slate-700">
            Imported {result.imported} contact{result.imported !== 1 ? 's' : ''}
            {result.errors.length > 0 ? ` with ${result.errors.length} error${result.errors.length !== 1 ? 's' : ''}` : ''}.
          </p>
          {result.errors.length > 0 && (
            <ul className="space-y-1 text-xs text-red-600">
              {result.errors.map((e) => (
                <li key={e.row}>Row {e.row}: {e.reason}</li>
              ))}
            </ul>
          )}
          <div className="flex justify-end pt-2">
            <button className="primary-button" onClick={onClose} type="button">Close</button>
          </div>
        </div>
      </ModalShell>
    );
  }

  return (
    <ModalShell title="Import Contacts" onClose={onClose}>
      <form className="space-y-4" onSubmit={(e) => void handleSubmit(e)}>
        <div>
          <p className="text-sm text-slate-600 mb-3">
            Upload a CSV file with columns: name, email, phone, company.
          </p>
          <label className="block">
            <span className="field-label">CSV File</span>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-blue-600 file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-white hover:file:bg-blue-700"
              onChange={(e) => setFileName(e.target.files?.[0]?.name ?? '')}
            />
          </label>
          {fileName && <p className="mt-1 text-xs text-slate-500">Selected: {fileName}</p>}
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <ModalActions onClose={onClose} submitLabel={busy ? 'Importing…' : 'Import'} />
      </form>
    </ModalShell>
  );
}
