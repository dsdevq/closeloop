import type { InsightsLeaderboardRow } from '../../types';

export function RepLeaderboard({ data }: { data: InsightsLeaderboardRow[] | null }) {
  return (
    <div className="panel p-4">
      <h2 className="mb-3 text-sm font-bold text-slate-900">Rep Leaderboard</h2>
      {!data && (
        <div className="flex h-40 items-center justify-center text-sm text-slate-400">
          Loading…
        </div>
      )}
    </div>
  );
}
