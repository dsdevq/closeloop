import type { Reminder } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';

export function TodayView({ reminders, onDismiss }: { reminders: Reminder[]; onDismiss: (id: number) => void }) {
  return (
    <>
      <SectionHeader title="Today" />
      {reminders.length === 0 && <div className="panel p-10 text-center text-sm text-slate-500">No reminders due today. You are all caught up.</div>}
      <div className="space-y-2">
        {reminders.map((item) => (
          <div key={item.id} className="panel flex items-center gap-3 p-3">
            <span className="rounded-md bg-blue-50 px-2 py-1 text-xs font-bold uppercase text-blue-700">{item.activity_type || 'note'}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-slate-950">{item.activity_title || 'Reminder'}</div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                {item.deal_title && <span>{item.deal_title}</span>}
                {item.contact_name && <span>{item.contact_name}</span>}
                {item.remind_at && <span>{new Date(item.remind_at).toLocaleString()}</span>}
              </div>
            </div>
            <button className="secondary-button" onClick={() => onDismiss(item.id)} type="button">
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </>
  );
}
