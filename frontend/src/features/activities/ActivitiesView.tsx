import { Plus } from 'lucide-react';
import { useMemo } from 'react';
import type { Activity, Contact } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';

export function ActivitiesView({
  activities,
  contacts,
  onOpenModal,
  onOpenActivity,
}: {
  activities: Activity[];
  contacts: Contact[];
  onOpenModal: () => void;
  onOpenActivity: (activity: Activity) => void;
}) {
  const contactById = useMemo(() => new Map(contacts.map((c) => [c.id, c])), [contacts]);
  return (
    <>
      <SectionHeader
        title="Activities"
        action={
          <button className="primary-button" onClick={onOpenModal} type="button">
            <Plus size={16} aria-hidden="true" />
            New Activity
          </button>
        }
      />
      <div className="panel overflow-hidden">
        <table className="w-full border-collapse">
          <thead className="table-head">
            <tr>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Contact</th>
              <th className="px-4 py-3">Due</th>
            </tr>
          </thead>
          <tbody>
            {activities.map((activity) => {
              const contact = activity.contact_id ? contactById.get(activity.contact_id) : null;
              return (
                <tr key={activity.id} className="hover:bg-slate-50">
                  <td className="table-cell font-semibold text-slate-900">
                    <button
                      className="font-semibold text-blue-700 hover:underline text-left"
                      onClick={() => onOpenActivity(activity)}
                      type="button"
                    >
                      {activity.title}
                    </button>
                  </td>
                  <td className="table-cell">
                    <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-bold text-blue-700 uppercase">{activity.type}</span>
                  </td>
                  <td className="table-cell">{contact?.name || ''}</td>
                  <td className="table-cell">{activity.due_at ? new Date(activity.due_at).toLocaleDateString() : ''}</td>
                </tr>
              );
            })}
            {activities.length === 0 && (
              <tr>
                <td className="px-4 py-10 text-center text-sm text-slate-500" colSpan={4}>
                  No activities yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
