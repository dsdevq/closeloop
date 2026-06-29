import { ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import type { Account } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';

export function AccountDetailView({
  account,
  onBack,
  onDelete,
}: {
  account: Account;
  onBack: () => void;
  onDelete: () => void;
}) {
  return (
    <>
      <SectionHeader
        title={account.name}
        action={
          <div className="flex gap-2">
            <button className="secondary-button" onClick={onBack} type="button">
              <ArrowLeft size={16} aria-hidden="true" />
              Back
            </button>
            {/* Account edit form is a follow-up goal — PATCH /accounts/:id exists but the UI form is not yet implemented */}
            <button className="secondary-button" disabled type="button">
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
      <div className="panel mb-4 grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-5">
        {[
          ['Domain', account.domain],
          ['Industry', account.industry],
          ['Website', account.website],
          ['Phone', account.phone],
          ['Address', account.address],
        ].map(([label, value]) => (
          <div key={label || ''}>
            <div className="text-xs font-bold uppercase text-slate-500">{label}</div>
            <div className="mt-1 text-sm text-slate-800">{value || 'Not set'}</div>
          </div>
        ))}
      </div>
      <h2 className="mb-2 text-sm font-bold text-slate-900">Linked Contacts</h2>
      <div className="panel overflow-hidden">
        <table className="w-full">
          <thead className="table-head">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">Company</th>
            </tr>
          </thead>
          <tbody>
            {(account.contacts || []).map((contact) => (
              <tr key={contact.id}>
                <td className="table-cell font-semibold">{contact.name}</td>
                <td className="table-cell">{contact.email || ''}</td>
                <td className="table-cell">{contact.phone || ''}</td>
                <td className="table-cell">{contact.company || ''}</td>
              </tr>
            ))}
            {(account.contacts || []).length === 0 && (
              <tr>
                <td className="px-4 py-8 text-center text-sm text-slate-500" colSpan={4}>
                  No linked contacts.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
