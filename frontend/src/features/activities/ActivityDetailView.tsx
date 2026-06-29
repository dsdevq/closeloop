import { ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import type { Activity, Contact } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';

export function ActivityDetailView({
  activity,
  contacts,
  onBack,
  onEdit,
  onDelete,
}: {
  activity: Activity;
  contacts: Contact[];
  onBack: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const contact = contacts.find((c) => c.id === activity.contact_id);
  return (
    <>
      <SectionHeader
        title={activity.title}
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
            ['Type', activity.type],
            ['Contact', contact?.name || 'None'],
            ['Due', activity.due_at ? new Date(activity.due_at).toLocaleString() : 'Not set'],
            ['Completed', activity.completed_at ? new Date(activity.completed_at).toLocaleString() : 'No'],
          ].map(([label, value]) => (
            <div key={label as string}>
              <div className="text-xs font-bold uppercase text-slate-500">{label as string}</div>
              <div className="mt-1 text-sm text-slate-800">{(value as string) || 'Not set'}</div>
            </div>
          ))}
        </div>
        {activity.body && (
          <div className="mt-4">
            <div className="text-xs font-bold uppercase text-slate-500">Notes</div>
            <div className="mt-1 text-sm text-slate-800 whitespace-pre-wrap">{activity.body}</div>
          </div>
        )}
      </div>
    </>
  );
}
