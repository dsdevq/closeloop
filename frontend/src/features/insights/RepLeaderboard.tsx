import { useState, useEffect } from 'react';
import { apiFetch } from '../../lib/api';
import type { InsightsLeaderboardRow } from '../../types';
import { BarChart } from './charts/BarChart';
import type { BarChartPoint } from './charts/BarChart';

function repLabel(row: InsightsLeaderboardRow): string {
  return row.owner_name ?? `Rep ${row.owner_id}`;
}

function leaderboardToBarPoints(data: InsightsLeaderboardRow[]): BarChartPoint[] {
  return data.map((row) => ({
    label: repLabel(row),
    value: row.revenue,
  }));
}

function formatRevenue(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}k`;
  return `$${v.toFixed(0)}`;
}

export function RepLeaderboard() {
  const [data, setData] = useState<InsightsLeaderboardRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    void apiFetch('/insights/leaderboard')
      .then((res) => {
        if (!res.ok) {
          setError(true);
          return undefined;
        }
        return res.json() as Promise<InsightsLeaderboardRow[]>;
      })
      .then((d) => {
        if (d !== undefined) setData(d);
      })
      .finally(() => setLoading(false));
  }, []);

  const barPoints = data ? leaderboardToBarPoints(data) : [];

  return (
    <div className="panel p-4">
      <h2 className="mb-3 text-sm font-bold text-slate-900">Rep Leaderboard</h2>

      {loading && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Loading…
        </div>
      )}

      {!loading && error && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Failed to load leaderboard data.
        </div>
      )}

      {!loading && !error && (
        <>
          <BarChart data={barPoints} formatValue={formatRevenue} />
          {data && data.length > 0 && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-400">
                    <th className="pb-1 pr-3 font-medium">Rep</th>
                    <th className="pb-1 pr-3 text-right font-medium">Revenue</th>
                    <th className="pb-1 pr-3 text-right font-medium">Deals</th>
                    <th className="pb-1 text-right font-medium">Avg Cycle</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((row) => (
                    <tr key={row.owner_id} className="border-t border-slate-100">
                      <td className="py-1 pr-3 text-slate-700">{repLabel(row)}</td>
                      <td className="py-1 pr-3 text-right font-medium text-slate-900">
                        {formatRevenue(row.revenue)}
                      </td>
                      <td className="py-1 pr-3 text-right text-slate-700">{row.deals_closed}</td>
                      <td className="py-1 text-right text-slate-500">
                        {row.avg_cycle_days !== null ? `${row.avg_cycle_days.toFixed(1)}d` : '—'}
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
