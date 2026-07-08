import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';
import type { HistoryEntry } from '../types';

function capitalize(s: string): string {
  return s.length === 0 ? s : s.charAt(0).toUpperCase() + s.slice(1);
}

function renderLabel(kind: string, meta: Record<string, unknown>): string {
  switch (kind) {
    case 'deal_created':
      return `Deal created: ${String(meta.deal_title ?? '')}`;
    case 'deal_stage_changed': {
      const from = meta.from_stage ? ` from ${String(meta.from_stage)}` : '';
      return `Stage changed${from} → ${String(meta.to_stage ?? '')}`;
    }
    case 'deal_assigned':
      return 'Deal assigned to new owner';
    case 'deal_updated':
      return `Deal updated: ${String(meta.deal_title ?? '')}`;
    case 'deal_deleted':
      return `Deal deleted: ${String(meta.deal_title ?? '')}`;
    case 'contact_created':
      return `Contact created: ${String(meta.contact_name ?? '')}`;
    case 'contact_updated':
      return `Contact updated: ${String(meta.contact_name ?? '')}`;
    case 'contact_deleted':
      return `Contact deleted: ${String(meta.contact_name ?? '')}`;
    case 'activity_created': {
      const t = capitalize(String(meta.activity_type ?? 'activity'));
      return `${t} logged: ${String(meta.activity_title ?? '')}`;
    }
    case 'activity_updated': {
      const t = capitalize(String(meta.activity_type ?? 'activity'));
      return `${t} updated: ${String(meta.activity_title ?? '')}`;
    }
    case 'activity_completed': {
      const t = capitalize(String(meta.activity_type ?? 'activity'));
      return `${t} completed: ${String(meta.activity_title ?? '')}`;
    }
    case 'activity_deleted': {
      const t = capitalize(String(meta.activity_type ?? 'activity'));
      return `${t} deleted: ${String(meta.activity_title ?? '')}`;
    }
    default:
      return kind;
  }
}

export function EntityTimeline({
  entityType,
  entityId,
}: {
  entityType: 'deal' | 'contact' | 'activity';
  entityId: number;
}) {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    void apiFetch(`/history?entity_type=${entityType}&entity_id=${entityId}`)
      .then((res) => {
        if (!res.ok) {
          setError(true);
          return undefined;
        }
        return res.json() as Promise<HistoryEntry[]>;
      })
      .then((data) => {
        if (data !== undefined) setEntries(data);
      })
      .finally(() => setLoading(false));
  }, [entityType, entityId]);

  return (
    <div className="panel mt-4 p-4">
      <h2 className="mb-3 text-sm font-bold text-slate-900">History</h2>
      {loading && <p className="text-sm text-slate-400">Loading…</p>}
      {!loading && error && <p className="text-sm text-slate-400">Failed to load history.</p>}
      {!loading && !error && entries.length === 0 && (
        <p className="text-sm text-slate-400">No history yet.</p>
      )}
      {!loading && !error && entries.length > 0 && (
        <ol className="space-y-3">
          {entries.map((entry) => {
            let meta: Record<string, unknown> = {};
            try {
              meta = JSON.parse(entry.meta_json) as Record<string, unknown>;
            } catch {
              // malformed meta_json — fall back to empty meta, renderLabel uses kind as fallback
            }
            const label = renderLabel(entry.kind, meta);
            const by = entry.actor_name ?? (entry.actor_id != null ? `User #${entry.actor_id}` : 'System');
            const at = new Date(entry.occurred_at).toLocaleString();
            return (
              <li key={entry.id} className="flex items-start gap-3">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500" aria-hidden="true" />
                <div>
                  <p className="text-sm text-slate-800">{label}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {at} · {by}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
