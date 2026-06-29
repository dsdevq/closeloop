import type { StatsData } from '../../types';
import { money, numberText } from '../../lib/formatters';
import { SectionHeader } from '../../components/ui/SectionHeader';

export function StatsView({ stats }: { stats: StatsData | null }) {
  const cards = stats
    ? [
        ['Total Contacts', numberText(stats.total_contacts)],
        ['Total Deals', numberText(stats.total_deals)],
        ['Total Activities', numberText(stats.total_activities)],
        ['Pipeline Value', money(stats.pipeline_value), 'open deals face value'],
        ['Weighted Forecast', money(stats.weighted_forecast), 'open deals probability weighted'],
        ['Activities (30d)', numberText(stats.activities_last_30_days), 'last 30 days'],
        ['Outbox Queued', numberText(stats.outbox_queued), 'unsent messages'],
      ]
    : [];
  return (
    <>
      <SectionHeader title="Stats" />
      {!stats && <div className="panel p-10 text-center text-sm text-slate-500">Loading stats.</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value, sub]) => (
          <div key={label} className="panel p-4">
            <div className="text-xs font-bold uppercase text-slate-500">{label}</div>
            <div className="mt-2 text-2xl font-bold text-slate-950">{value}</div>
            {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
          </div>
        ))}
      </div>
      {stats?.deals_by_stage && Object.keys(stats.deals_by_stage).length > 0 && (
        <div className="panel mt-4 p-4">
          <h2 className="mb-3 text-sm font-bold text-slate-900">Deals by Stage</h2>
          <div className="divide-y divide-slate-100">
            {Object.entries(stats.deals_by_stage).map(([stage, count]) => (
              <div key={stage} className="flex justify-between py-2 text-sm">
                <span>{stage}</span>
                <span className="font-semibold">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
