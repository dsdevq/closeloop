import { useState, useEffect } from 'react';
import type {
  InsightsCohorts,
  InsightsFunnel,
  InsightsLeaderboardRow,
  InsightsTrends,
} from '../../types';
import { apiFetch } from '../../lib/api';

export type InsightsState = {
  trends: InsightsTrends | null;
  funnel: InsightsFunnel | null;
  leaderboard: InsightsLeaderboardRow[] | null;
  cohorts: InsightsCohorts | null;
};

export function useInsights(): InsightsState {
  const [trends, setTrends] = useState<InsightsTrends | null>(null);
  const [funnel, setFunnel] = useState<InsightsFunnel | null>(null);
  const [leaderboard, setLeaderboard] = useState<InsightsLeaderboardRow[] | null>(null);
  const [cohorts, setCohorts] = useState<InsightsCohorts | null>(null);

  useEffect(() => {
    void Promise.all([
      apiFetch('/insights/trends')
        .then((res) => (res.ok ? res.json() : null))
        .then((data: InsightsTrends | null) => { if (data) setTrends(data); }),
      apiFetch('/insights/funnel')
        .then((res) => (res.ok ? res.json() : null))
        .then((data: InsightsFunnel | null) => { if (data) setFunnel(data); }),
      apiFetch('/insights/leaderboard')
        .then((res) => (res.ok ? res.json() : null))
        .then((data: InsightsLeaderboardRow[] | null) => { if (data) setLeaderboard(data); }),
      apiFetch('/insights/cohorts')
        .then((res) => (res.ok ? res.json() : null))
        .then((data: InsightsCohorts | null) => { if (data) setCohorts(data); }),
    ]);
  }, []);

  return { trends, funnel, leaderboard, cohorts };
}
