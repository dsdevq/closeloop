import { useState, useEffect } from 'react';
import type { InsightsCohorts } from '../../types';
import { apiFetch } from '../../lib/api';

export type InsightsState = {
  cohorts: InsightsCohorts | null;
};

export function useInsights(): InsightsState {
  const [cohorts, setCohorts] = useState<InsightsCohorts | null>(null);

  useEffect(() => {
    void apiFetch('/insights/cohorts')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: InsightsCohorts | null) => {
        if (data) setCohorts(data);
      });
  }, []);

  return { cohorts };
}
