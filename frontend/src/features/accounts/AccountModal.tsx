import { useState } from 'react';
import type { Account } from '../../types';
import { TextField } from '../../components/ui/TextField';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

export function AccountModal({ onClose, onSubmit }: { onClose: () => void; onSubmit: (body: Partial<Account> & { name: string }) => Promise<void> }) {
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [industry, setIndustry] = useState('');
  const [website, setWebsite] = useState('');
  const [phone, setPhone] = useState('');
  return (
    <ModalShell title="New Account" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          const body: Partial<Account> & { name: string } = { name: name.trim() };
          if (domain.trim()) body.domain = domain.trim();
          if (industry.trim()) body.industry = industry.trim();
          if (website.trim()) body.website = website.trim();
          if (phone.trim()) body.phone = phone.trim();
          void onSubmit(body);
        }}
      >
        <TextField label="Name" value={name} onChange={setName} required />
        <TextField label="Domain" value={domain} onChange={setDomain} />
        <TextField label="Industry" value={industry} onChange={setIndustry} />
        <TextField label="Website" value={website} onChange={setWebsite} />
        <TextField label="Phone" value={phone} onChange={setPhone} />
        <ModalActions onClose={onClose} submitLabel="Create" />
      </form>
    </ModalShell>
  );
}
