import { useState, useEffect } from 'react';
import { apiFetch } from '../../lib/api';
import type { InsightsTrends } from '../../types';
import { BarChart } from './charts/BarChart';
import type { BarChartPoint } from './charts/BarChart';

const WINDOWS = [30, 90, 365] as const;
type WindowDays = (typeof WINDOWS)[number];

const STAGE_ORDER = ['lead', 'qualified', 'proposal', 'negotiation', 'won', 'lost'];

function trendsToPoints(data: InsightsTrends): BarChartPoint[] {
  const entries = Object.entries(data);
  entries.sort(([a], [b]) => {
    const ai = STAGE_ORDER.indexOf(a);
    const bi = STAGE_ORDER.indexOf(b);
    if (ai === -1 && bi === -1) return a.localeCompare(b);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
  return entries.map(([label, value]) => ({ label, value }));
}

export function TrendsSection() {
  const [windowDays, setWindowDays] = useState<WindowDays>(30);
  const [data, setData] = useState<InsightsTrends | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    void apiFetch(`/insights/trends?window_days=${windowDays}`)
      .then((res) => {
        if (!res.ok) {
          setError(true);
          return undefined;
        }
        return res.json() as Promise<InsightsTrends>;
      })
      .then((d) => {
        if (d !== undefined) setData(d);
      })
      .finally(() => setLoading(false));
  }, [windowDays]);

  const points = data ? trendsToPoints(data) : [];

  return (
    <div className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-900">Deal Trends</h2>
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setWindowDays(w)}
              className={
                w === windowDays
                  ? 'rounded px-2 py-0.5 text-xs font-semibold bg-blue-600 text-white'
                  : 'rounded px-2 py-0.5 text-xs font-semibold text-slate-500 hover:bg-slate-100'
              }
            >
              {w}d
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Loading…
        </div>
      )}

      {!loading && error && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Failed to load trends data.
        </div>
      )}

      {!loading && !error && <BarChart data={points} />}
    </div>
  );
}
