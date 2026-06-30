import { useState } from 'react';
import type { Account } from '../../types';
import { TextField } from '../../components/ui/TextField';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

export function AccountEditModal({
  account,
  onClose,
  onSubmit,
}: {
  account: Account;
  onClose: () => void;
  onSubmit: (payload: Partial<Account>) => void;
}) {
  const [name, setName] = useState(account.name);
  const [notes, setNotes] = useState(account.notes ?? '');
  const [address, setAddress] = useState(account.address ?? '');
  return (
    <ModalShell title="Edit Account" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          const payload: Partial<Account> = {};
          const trimmedName = name.trim();
          if (trimmedName !== account.name) payload.name = trimmedName;
          const trimmedNotes = notes.trim() || null;
          if (trimmedNotes !== (account.notes ?? null)) payload.notes = trimmedNotes;
          const trimmedAddress = address.trim() || null;
          if (trimmedAddress !== (account.address ?? null)) payload.address = trimmedAddress;
          onSubmit(payload);
        }}
      >
        <TextField label="Name" value={name} onChange={setName} required />
        <TextField label="Notes" value={notes} onChange={setNotes} />
        <TextField label="Address" value={address} onChange={setAddress} />
        <ModalActions onClose={onClose} submitLabel="Save" />
      </form>
    </ModalShell>
  );
}

export default AccountEditModal;
