import { ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import type { Contact, Deal } from '../../types';
import { money } from '../../lib/formatters';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { EntityTimeline } from '../../components/EntityTimeline';

export function DealDetailView({
  deal,
  contacts,
  onBack,
  onEdit,
  onDelete,
}: {
  deal: Deal;
  contacts: Contact[];
  onBack: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const contact = contacts.find((c) => c.id === deal.contact_id);
  return (
    <>
      <SectionHeader
        title={deal.title}
        action={
          <div className="flex gap-2">
            <button className="secondary-button" onClick={onBack} type="button">
              <ArrowLeft size={16} aria-hidden="true" />
              Back
            </button>
            <button className="secondary-button" onClick={onEdit} type="button">
              <Pencil size={16} aria-hidden="true" />
              Edit
            </button>
            <button className="danger-button" onClick={onDelete} type="button">
              <Trash2 size={16} aria-hidden="true" />
              Delete
            </button>
          </div>
        }
      />
      <div className="panel p-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Value', money(deal.value)],
            ['Stage', deal.stage || 'Not set'],
            ['Probability', `${Math.round(Number(deal.probability || 0) * 100)}%`],
            ['Contact', contact?.name || deal.contact_name || 'Not set'],
          ].map(([label, value]) => (
            <div key={label as string}>
              <div className="text-xs font-bold uppercase text-slate-500">{label as string}</div>
              <div className="mt-1 text-sm text-slate-800">{value as string}</div>
            </div>
          ))}
        </div>
      </div>
      <EntityTimeline entityType="deal" entityId={deal.id} />
    </>
  );
}
