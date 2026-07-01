import { SectionHeader } from '../../components/ui/SectionHeader';
import { useInsights } from './useInsights';
import { TrendsSection } from './TrendsSection';
import { ConversionFunnel } from './ConversionFunnel';
import { RepLeaderboard } from './RepLeaderboard';
import { SourceCohorts } from './SourceCohorts';

export function InsightsView() {
  const { trends, funnel, leaderboard, cohorts } = useInsights();

  return (
    <>
      <SectionHeader title="Insights" />
      <div className="grid gap-4 lg:grid-cols-2">
        <TrendsSection data={trends} />
        <ConversionFunnel data={funnel} />
        <RepLeaderboard data={leaderboard} />
        <SourceCohorts data={cohorts} />
      </div>
    </>
  );
}
