import type { Contact, Deal } from '../../types';
import { money } from '../../lib/formatters';

export function DealCard({
  contact,
  deal,
  onDragEnd,
  onDragStart,
  onOpenDeal,
}: {
  contact?: Contact;
  deal: Deal;
  onDragEnd: () => void;
  onDragStart: (id: number) => void;
  onOpenDeal: (deal: Deal) => void;
}) {
  return (
    <div
      className="cursor-pointer rounded-md border border-slate-200 bg-white p-3 shadow-sm transition hover:border-blue-300 hover:shadow-md"
      draggable
      onClick={() => onOpenDeal(deal)}
      onDragEnd={onDragEnd}
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = 'move';
        onDragStart(deal.id);
      }}
    >
      <div className="text-sm font-semibold text-slate-950">{deal.title}</div>
      {(deal.contact_name || contact?.name) && <div className="mt-1 text-xs text-slate-500">{deal.contact_name || contact?.name}</div>}
      <div className="mt-3 flex items-center justify-between text-xs text-slate-600">
        <span>{money(deal.value)}</span>
        <span>{Math.round(Number(deal.probability || 0) * 100)}%</span>
      </div>
    </div>
  );
}
