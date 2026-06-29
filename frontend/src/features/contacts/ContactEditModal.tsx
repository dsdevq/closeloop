import { useState } from 'react';
import type { Contact } from '../../types';
import { TextField } from '../../components/ui/TextField';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

export function ContactEditModal({
  contact,
  onClose,
  onSubmit,
}: {
  contact: Contact;
  onClose: () => void;
  onSubmit: (body: Partial<Contact>) => Promise<void>;
}) {
  const [name, setName] = useState(contact.name);
  const [email, setEmail] = useState(contact.email ?? '');
  const [phone, setPhone] = useState(contact.phone ?? '');
  const [company, setCompany] = useState(contact.company ?? '');
  return (
    <ModalShell title="Edit Contact" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit({ name: name.trim(), email: email.trim() || undefined, phone: phone.trim() || undefined, company: company.trim() || undefined });
        }}
      >
        <TextField label="Name" value={name} onChange={setName} required />
        <TextField label="Email" value={email} onChange={setEmail} type="email" />
        <TextField label="Phone" value={phone} onChange={setPhone} />
        <TextField label="Company" value={company} onChange={setCompany} />
        <ModalActions onClose={onClose} submitLabel="Save" />
      </form>
    </ModalShell>
  );
}
