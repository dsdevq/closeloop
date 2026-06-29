import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-react';
import type { Account } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';

export function AccountsView({
  account,
  accounts,
  onBack,
  onDeleteAccount,
  onOpenAccount,
  onOpenModal,
}: {
  account: Account | null;
  accounts: Account[];
  onBack: () => void;
  onDeleteAccount: (id: number) => void;
  onOpenAccount: (id: number) => void;
  onOpenModal: () => void;
}) {
  if (account) {
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
              {/* TODO: Account edit form — follow-up goal (PATCH /accounts/:id API exists, UI not yet implemented) */}
              <button className="secondary-button" disabled type="button">
                <Pencil size={16} aria-hidden="true" />
                Edit
              </button>
              <button className="danger-button" onClick={() => onDeleteAccount(account.id)} type="button">
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

  return (
    <>
      <SectionHeader
        title="Accounts"
        action={
          <button className="primary-button" onClick={onOpenModal} type="button">
            <Plus size={16} aria-hidden="true" />
            New Account
          </button>
        }
      />
      <div className="panel overflow-hidden">
        <table className="w-full">
          <thead className="table-head">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Domain</th>
              <th className="px-4 py-3">Industry</th>
              <th className="px-4 py-3">Contacts</th>
              <th className="px-4 py-3">Owner ID</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((item) => (
              <tr key={item.id} className="hover:bg-slate-50">
                <td className="table-cell">
                  <button className="font-semibold text-blue-700 hover:underline" onClick={() => onOpenAccount(item.id)} type="button">
                    {item.name}
                  </button>
                </td>
                <td className="table-cell">{item.domain || ''}</td>
                <td className="table-cell">{item.industry || ''}</td>
                <td className="table-cell">{item.contact_count || 0}</td>
                <td className="table-cell">{item.owner_id || ''}</td>
              </tr>
            ))}
            {accounts.length === 0 && (
              <tr>
                <td className="px-4 py-10 text-center text-sm text-slate-500" colSpan={5}>
                  No accounts yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
