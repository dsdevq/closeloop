import { useState } from 'react';
import type { Account, Contact } from '../../types';
import { TextField } from '../../components/ui/TextField';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

export function ContactModal({ accounts, onClose, onSubmit }: { accounts: Account[]; onClose: () => void; onSubmit: (body: Partial<Contact> & { name: string }) => Promise<void> }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [company, setCompany] = useState('');
  const [accountId, setAccountId] = useState('');
  return (
    <ModalShell title="New Contact" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          const body: Partial<Contact> & { name: string } = { name: name.trim() };
          if (email.trim()) body.email = email.trim();
          if (phone.trim()) body.phone = phone.trim();
          if (company.trim()) body.company = company.trim();
          if (accountId) body.account_id = Number(accountId);
          void onSubmit(body);
        }}
      >
        <TextField label="Name" value={name} onChange={setName} required />
        <TextField label="Email" value={email} onChange={setEmail} type="email" />
        <TextField label="Phone" value={phone} onChange={setPhone} />
        <TextField label="Company" value={company} onChange={setCompany} />
        <label className="block">
          <span className="field-label">Account</span>
          <select className="field-input" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">None</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>
        <ModalActions onClose={onClose} submitLabel="Create" />
      </form>
    </ModalShell>
  );
}
