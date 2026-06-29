import { Plus } from 'lucide-react';
import { useMemo } from 'react';
import type { Contact, Deal, PipelineStage, SavedView } from '../../types';
import { money } from '../../lib/formatters';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { SavedViewsBar } from '../../components/ui/SavedViewsBar';
import { DealCard } from './DealCard';

const stagePalette = [
  'border-l-blue-600',
  'border-l-cyan-600',
  'border-l-amber-500',
  'border-l-orange-500',
  'border-l-emerald-600',
  'border-l-red-600',
  'border-l-violet-600',
  'border-l-pink-600',
];

export function PipelineView({
  activeSavedView,
  contacts,
  deals,
  draggedDealId,
  forecastTotal,
  loading,
  onApplySavedView,
  onClearSavedView,
  onMoveDeal,
  onOpenModal,
  onOpenDeal,
  savedViews,
  setDraggedDealId,
  stages,
}: {
  activeSavedView?: string;
  contacts: Contact[];
  deals: Deal[];
  draggedDealId: number | null;
  forecastTotal: number | null;
  loading: boolean;
  onApplySavedView: (id: number, name: string) => void;
  onClearSavedView: () => void;
  onMoveDeal: (dealId: number, stageId: number) => void;
  onOpenModal: () => void;
  onOpenDeal: (deal: Deal) => void;
  savedViews: SavedView[];
  setDraggedDealId: (id: number | null) => void;
  stages: PipelineStage[];
}) {
  const contactById = useMemo(() => new Map(contacts.map((contact) => [contact.id, contact])), [contacts]);

  return (
    <>
      <SectionHeader
        title="Pipeline"
        action={
          <button className="primary-button" onClick={onOpenModal} type="button">
            <Plus size={16} aria-hidden="true" />
            New Deal
          </button>
        }
      />
      <SavedViewsBar views={savedViews} activeName={activeSavedView} onApply={onApplySavedView} onClear={onClearSavedView} />

      <div className="flex gap-3 overflow-x-auto pb-3">
        {stages.length === 0 && <div className="panel w-full p-8 text-center text-sm text-slate-500">{loading ? 'Loading pipeline' : 'No pipeline stages configured.'}</div>}
        {stages.map((stage, index) => {
          const stageDeals = deals.filter((deal) => deal.stage_id === stage.id);
          return (
            <div key={stage.id} className={`flex min-h-[520px] min-w-64 flex-1 flex-col rounded-lg border border-slate-200 border-l-4 bg-slate-100 p-3 ${stagePalette[index % stagePalette.length]}`}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-bold uppercase text-slate-600">{stage.name}</div>
                  <div className="text-xs text-slate-500">{stage.probability}% probability</div>
                </div>
                <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-bold text-slate-600">{stageDeals.length}</span>
              </div>
              <div
                className={`flex flex-1 flex-col gap-2 rounded-md ${draggedDealId ? 'ring-1 ring-dashed ring-slate-300' : ''}`}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (draggedDealId) onMoveDeal(draggedDealId, stage.id);
                  setDraggedDealId(null);
                }}
              >
                {stageDeals.map((deal) => (
                  <DealCard key={deal.id} contact={deal.contact_id ? contactById.get(deal.contact_id) : undefined} deal={deal} onDragStart={setDraggedDealId} onDragEnd={() => setDraggedDealId(null)} onOpenDeal={onOpenDeal} />
                ))}
              </div>
              <button className="secondary-button mt-3 w-full justify-center border-dashed bg-white/70" onClick={onOpenModal} type="button">
                <Plus size={15} aria-hidden="true" />
                Add deal
              </button>
            </div>
          );
        })}
      </div>

      {forecastTotal !== null && (
        <div className="panel mt-2 inline-flex items-center gap-6 px-4 py-3">
          <div>
            <div className="text-xs font-bold uppercase text-slate-500">Weighted Forecast</div>
            <div className="text-xl font-bold text-blue-700">{money(forecastTotal)}</div>
            <div className="text-xs text-slate-500">open deals by stage probability</div>
          </div>
        </div>
      )}
    </>
  );
}
