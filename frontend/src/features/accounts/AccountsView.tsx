import { Plus } from 'lucide-react';
import type { Account } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';

export function AccountsView({
  accounts,
  onOpenAccount,
  onOpenModal,
}: {
  accounts: Account[];
  onOpenAccount: (id: number) => void;
  onOpenModal: () => void;
}) {
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
                  <button
                    className="font-semibold text-blue-700 hover:underline"
                    onClick={() => onOpenAccount(item.id)}
                    type="button"
                  >
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
