import { useState } from 'react';
import type { Contact } from '../../types';
import { TextField } from '../../components/ui/TextField';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

export function DealModal({ contacts, onClose, onSubmit }: { contacts: Contact[]; onClose: () => void; onSubmit: (body: { title: string; contact_id: number; value: number }) => Promise<void> }) {
  const [title, setTitle] = useState('');
  const [contactId, setContactId] = useState('');
  const [value, setValue] = useState('');
  return (
    <ModalShell title="New Deal" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit({ title: title.trim(), contact_id: Number(contactId), value: Number(value || 0) });
        }}
      >
        <TextField label="Title" value={title} onChange={setTitle} required />
        <label className="block">
          <span className="field-label">Contact</span>
          <select className="field-input" value={contactId} onChange={(event) => setContactId(event.target.value)} required>
            <option value="">Select contact</option>
            {contacts.map((contact) => (
              <option key={contact.id} value={contact.id}>
                {contact.name}
                {contact.company ? ` (${contact.company})` : ''}
              </option>
            ))}
          </select>
        </label>
        <TextField label="Value" value={value} onChange={setValue} type="number" />
        <ModalActions onClose={onClose} submitLabel="Create" />
      </form>
    </ModalShell>
  );
}
