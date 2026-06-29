import { useState } from 'react';
import type { Deal } from '../../types';
import { TextField } from '../../components/ui/TextField';
import { ModalShell } from '../../components/ui/ModalShell';
import { ModalActions } from '../../components/ui/ModalActions';

export function DealEditModal({
  deal,
  onClose,
  onSubmit,
}: {
  deal: Deal;
  onClose: () => void;
  onSubmit: (body: Partial<Deal>) => Promise<void>;
}) {
  const [title, setTitle] = useState(deal.title);
  const [value, setValue] = useState(String(deal.value ?? ''));
  return (
    <ModalShell title="Edit Deal" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit({ title: title.trim(), value: Number(value || 0) });
        }}
      >
        <TextField label="Title" value={title} onChange={setTitle} required />
        <TextField label="Value" value={value} onChange={setValue} type="number" />
        <ModalActions onClose={onClose} submitLabel="Save" />
      </form>
    </ModalShell>
  );
}
