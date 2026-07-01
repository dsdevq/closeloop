import { useState, useEffect } from 'react';
import { apiFetch } from '../../lib/api';
import type { InsightsFunnel, InsightsFunnelStage } from '../../types';
import { BarChart } from './charts/BarChart';
import type { BarChartPoint } from './charts/BarChart';

const STAGE_ORDER = ['lead', 'qualified', 'proposal', 'negotiation', 'won', 'lost'];

function sortedEntries(data: InsightsFunnel): [string, InsightsFunnelStage][] {
  return Object.entries(data).sort(([a], [b]) => {
    const ai = STAGE_ORDER.indexOf(a);
    const bi = STAGE_ORDER.indexOf(b);
    if (ai === -1 && bi === -1) return a.localeCompare(b);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

function funnelToBarPoints(data: InsightsFunnel): BarChartPoint[] {
  return sortedEntries(data).map(([label, stage]) => ({
    label,
    value: Math.round(stage.conversion_rate * 100),
  }));
}

type TimePoint = { label: string; days: number | null };

function funnelToTimePoints(data: InsightsFunnel): TimePoint[] {
  return sortedEntries(data).map(([label, stage]) => ({
    label,
    days: stage.avg_time_in_stage_days,
  }));
}

export function ConversionFunnel() {
  const [data, setData] = useState<InsightsFunnel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    void apiFetch('/insights/funnel')
      .then((res) => {
        if (!res.ok) {
          setError(true);
          return undefined;
        }
        return res.json() as Promise<InsightsFunnel>;
      })
      .then((d) => {
        if (d !== undefined) setData(d);
      })
      .finally(() => setLoading(false));
  }, []);

  const barPoints = data ? funnelToBarPoints(data) : [];
  const timePoints = data ? funnelToTimePoints(data) : [];

  return (
    <div className="panel p-4">
      <h2 className="mb-3 text-sm font-bold text-slate-900">Conversion Funnel</h2>

      {loading && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Loading…
        </div>
      )}

      {!loading && error && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Failed to load funnel data.
        </div>
      )}

      {!loading && !error && (
        <>
          <BarChart data={barPoints} formatValue={(v) => `${v}%`} />
          {timePoints.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              {timePoints.map(({ label, days }) => (
                <span key={label} className="text-xs text-slate-500">
                  <span className="font-medium text-slate-700">{label}</span>
                  {' '}{days !== null ? `${days.toFixed(1)}d avg` : '—'}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
