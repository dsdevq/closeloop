import { SectionHeader } from '../../components/ui/SectionHeader';
import { TrendsSection } from './TrendsSection';
import { ConversionFunnel } from './ConversionFunnel';
import { RepLeaderboard } from './RepLeaderboard';
import { SourceCohorts } from './SourceCohorts';

export function InsightsView() {
  return (
    <>
      <SectionHeader title="Insights" />
      <div className="grid gap-4 lg:grid-cols-2">
        <TrendsSection />
        <ConversionFunnel />
        <RepLeaderboard />
        <SourceCohorts />
      </div>
    </>
  );
}
