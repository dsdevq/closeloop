import { useState } from 'react';
import type { Activity, Contact } from '../../types';
import { TextField } from '../../components/ui/TextField';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

const ACTIVITY_TYPES = ['call', 'email', 'meeting', 'note'] as const;

export function ActivityFormModal({
  activity,
  contacts,
  onClose,
  onSubmit,
}: {
  activity?: Activity;
  contacts: Contact[];
  onClose: () => void;
  onSubmit: (body: { title: string; type: string; body?: string; contact_id?: number }) => Promise<void>;
}) {
  const [title, setTitle] = useState(activity?.title ?? '');
  const [type, setType] = useState(activity?.type ?? 'call');
  const [body, setBody] = useState(activity?.body ?? '');
  const [contactId, setContactId] = useState(String(activity?.contact_id ?? ''));
  const isEdit = Boolean(activity);
  return (
    <ModalShell title={isEdit ? 'Edit Activity' : 'New Activity'} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit({
            title: title.trim(),
            type,
            body: body.trim() || undefined,
            contact_id: contactId ? Number(contactId) : undefined,
          });
        }}
      >
        <TextField label="Title" value={title} onChange={setTitle} required />
        <label className="block">
          <span className="field-label">Type</span>
          <select className="field-input" value={type} onChange={(e) => setType(e.target.value)}>
            {ACTIVITY_TYPES.map((t) => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="field-label">Contact</span>
          <select className="field-input" value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">None</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="field-label">Notes</span>
          <textarea
            className="field-input"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
          />
        </label>
        <ModalActions onClose={onClose} submitLabel={isEdit ? 'Save' : 'Create'} />
      </form>
    </ModalShell>
  );
}
