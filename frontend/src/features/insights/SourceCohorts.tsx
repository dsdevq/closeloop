import type { InsightsCohorts } from '../../types';

export function SourceCohorts({ data }: { data: InsightsCohorts | null }) {
  return (
    <div className="panel p-4">
      <h2 className="mb-3 text-sm font-bold text-slate-900">Source Cohorts</h2>
      {!data && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Loading…
        </div>
      )}
    </div>
  );
}
