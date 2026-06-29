import { Download, Plus, Upload } from 'lucide-react';
import { useMemo } from 'react';
import type { Account, Contact, SavedView } from '../../types';
import { SectionHeader } from '../../components/ui/SectionHeader';
import { SavedViewsBar } from '../../components/ui/SavedViewsBar';

export function ContactsView({
  accounts,
  activeSavedView,
  contacts,
  onApplySavedView,
  onClearSavedView,
  onOpenAccount,
  onOpenContact,
  onOpenModal,
  onImport,
  onExport,
  savedViews,
}: {
  accounts: Account[];
  activeSavedView?: string;
  contacts: Contact[];
  onApplySavedView: (id: number, name: string) => void;
  onClearSavedView: () => void;
  onOpenAccount: (id: number) => void;
  onOpenContact: (contact: Contact) => void;
  onOpenModal: () => void;
  onImport: () => void;
  onExport: () => void;
  savedViews: SavedView[];
}) {
  const accountById = useMemo(() => new Map(accounts.map((account) => [account.id, account])), [accounts]);
  return (
    <>
      <SectionHeader
        title="Contacts"
        action={
          <div className="flex gap-2">
            <button className="secondary-button" onClick={onImport} type="button">
              <Upload size={16} aria-hidden="true" />
              Import CSV
            </button>
            <button className="secondary-button" onClick={onExport} type="button">
              <Download size={16} aria-hidden="true" />
              Export CSV
            </button>
            <button className="primary-button" onClick={onOpenModal} type="button">
              <Plus size={16} aria-hidden="true" />
              New Contact
            </button>
          </div>
        }
      />
      <SavedViewsBar views={savedViews} activeName={activeSavedView} onApply={onApplySavedView} onClear={onClearSavedView} />
      <div className="panel overflow-hidden">
        <table className="w-full border-collapse">
          <thead className="table-head">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Phone</th>
              <th className="px-4 py-3">Company</th>
              <th className="px-4 py-3">Account</th>
              <th className="px-4 py-3">Lead Score</th>
            </tr>
          </thead>
          <tbody>
            {contacts.map((contact) => {
              const account = contact.account_id ? accountById.get(contact.account_id) : null;
              return (
                <tr key={contact.id} className="hover:bg-slate-50">
                  <td className="table-cell font-semibold text-slate-900">
                    <button
                      className="font-semibold text-blue-700 hover:underline"
                      onClick={() => onOpenContact(contact)}
                      type="button"
                    >
                      {contact.name}
                    </button>
                  </td>
                  <td className="table-cell">{contact.email || ''}</td>
                  <td className="table-cell">{contact.phone || ''}</td>
                  <td className="table-cell">{contact.company || ''}</td>
                  <td className="table-cell">
                    {account && (
                      <button className="font-semibold text-blue-700 hover:underline" onClick={() => onOpenAccount(account.id)} type="button">
                        {account.name}
                      </button>
                    )}
                  </td>
                  <td className="table-cell">
                    <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-bold text-blue-700">{Number(contact.lead_score || 0).toFixed(1)}</span>
                  </td>
                </tr>
              );
            })}
            {contacts.length === 0 && (
              <tr>
                <td className="px-4 py-10 text-center text-sm text-slate-500" colSpan={6}>
                  No contacts yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
