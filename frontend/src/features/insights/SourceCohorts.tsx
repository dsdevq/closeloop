import { useState, useEffect } from 'react';
import { apiFetch } from '../../lib/api';
import type { InsightsCohorts } from '../../types';
import { BarChart } from './charts/BarChart';
import type { BarChartPoint } from './charts/BarChart';

const SOURCE_ORDER = ['referral', 'inbound', 'outbound', 'event', 'other'];

function sortedSources(data: InsightsCohorts): [string, InsightsCohorts[string]][] {
  return Object.entries(data).sort(([a], [b]) => {
    const ai = SOURCE_ORDER.indexOf(a);
    const bi = SOURCE_ORDER.indexOf(b);
    if (ai === -1 && bi === -1) return a.localeCompare(b);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

function cohortsToBarPoints(data: InsightsCohorts): BarChartPoint[] {
  return sortedSources(data).map(([label, cohort]) => ({
    label,
    value: Math.round(cohort.avg_deal_value),
  }));
}

function formatCurrency(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

export function SourceCohorts() {
  const [data, setData] = useState<InsightsCohorts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    void apiFetch('/insights/cohorts')
      .then((res) => {
        if (!res.ok) {
          setError(true);
          return undefined;
        }
        return res.json() as Promise<InsightsCohorts>;
      })
      .then((d) => {
        if (d !== undefined) setData(d);
      })
      .finally(() => setLoading(false));
  }, []);

  const barPoints = data ? cohortsToBarPoints(data) : [];
  const rows = data ? sortedSources(data) : [];

  return (
    <div className="panel p-4">
      <h2 className="mb-3 text-sm font-bold text-slate-900">Source Cohorts</h2>

      {loading && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Loading…
        </div>
      )}

      {!loading && error && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Failed to load cohorts data.
        </div>
      )}

      {!loading && !error && (
        <>
          <BarChart data={barPoints} formatValue={formatCurrency} />
          {rows.length > 0 && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-400">
                    <th className="pb-1 pr-3 font-medium">Source</th>
                    <th className="pb-1 pr-3 text-right font-medium">Deals</th>
                    <th className="pb-1 pr-3 text-right font-medium">Avg Value</th>
                    <th className="pb-1 text-right font-medium">Win Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(([source, cohort]) => (
                    <tr key={source} className="border-t border-slate-100">
                      <td className="py-1 pr-3 text-slate-700 capitalize">{source}</td>
                      <td className="py-1 pr-3 text-right text-slate-700">{cohort.deal_count}</td>
                      <td className="py-1 pr-3 text-right font-medium text-slate-900">
                        {formatCurrency(cohort.avg_deal_value)}
                      </td>
                      <td className="py-1 text-right text-slate-500">
                        {(cohort.win_rate * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
