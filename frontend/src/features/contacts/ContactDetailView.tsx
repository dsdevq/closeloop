import { ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import type { Contact } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { EntityTimeline } from '../../components/EntityTimeline';

export function ContactDetailView({
  contact,
  onBack,
  onEdit,
  onDelete,
}: {
  contact: Contact;
  onBack: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <>
      <SectionHeader
        title={contact.name}
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
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[
            ['Email', contact.email],
            ['Phone', contact.phone],
            ['Company', contact.company],
            ['Lead Score', Number(contact.lead_score || 0).toFixed(1)],
          ].map(([label, value]) => (
            <div key={label as string}>
              <div className="text-xs font-bold uppercase text-slate-500">{label as string}</div>
              <div className="mt-1 text-sm text-slate-800">{(value as string) || 'Not set'}</div>
            </div>
          ))}
        </div>
      </div>
      <EntityTimeline entityType="contact" entityId={contact.id} />
    </>
  );
}
