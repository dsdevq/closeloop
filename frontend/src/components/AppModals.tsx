import type { Contact, Deal, Activity, Account } from '../types';
import { DealModal } from '../features/pipeline/DealModal';
import { DealEditModal } from '../features/pipeline/DealEditModal';
import { ContactModal } from '../features/contacts/ContactModal';
import { ContactEditModal } from '../features/contacts/ContactEditModal';
import { ImportModal } from '../features/contacts/ImportModal';
import { AccountModal } from '../features/accounts/AccountModal';
import { ActivityFormModal } from '../features/activities/ActivityFormModal';

interface AppModalsProps {
  contacts: Contact[];
  accounts: Account[];
  modal: 'deal' | 'contact' | 'account' | null;
  onCloseModal: () => void;
  contactToEdit: Contact | null;
  onCloseContactEdit: () => void;
  dealToEdit: Deal | null;
  onCloseDealEdit: () => void;
  activityToEdit: Activity | null;
  onCloseActivityEdit: () => void;
  showNewActivity: boolean;
  onCloseNewActivity: () => void;
  showImportModal: boolean;
  onImportSuccess: (count: number) => void;
  onCloseImportModal: () => void;
  onCreateDeal: (body: { title: string; contact_id: number; value: number }) => Promise<void>;
  onCreateContact: (body: Partial<Contact> & { name: string }) => Promise<void>;
  onCreateAccount: (body: Partial<Account> & { name: string }) => Promise<void>;
  onCreateActivity: (body: { title: string; type: string; body?: string; contact_id?: number }) => Promise<void>;
  onUpdateActivity: (id: number, body: Partial<Activity>) => Promise<void>;
  onUpdateContact: (id: number, body: Partial<Contact>) => Promise<void>;
  onUpdateDeal: (id: number, body: Partial<Deal>) => Promise<void>;
}

export function AppModals({
  contacts, accounts, modal, onCloseModal,
  contactToEdit, onCloseContactEdit,
  dealToEdit, onCloseDealEdit,
  activityToEdit, onCloseActivityEdit,
  showNewActivity, onCloseNewActivity,
  showImportModal, onImportSuccess, onCloseImportModal,
  onCreateDeal, onCreateContact, onCreateAccount, onCreateActivity,
  onUpdateActivity, onUpdateContact, onUpdateDeal,
}: AppModalsProps) {
  return (
    <>
      {modal === 'deal' && (
        <DealModal
          contacts={contacts}
          onClose={onCloseModal}
          onSubmit={async (body) => { await onCreateDeal(body); onCloseModal(); }}
        />
      )}
      {modal === 'contact' && (
        <ContactModal
          accounts={accounts}
          onClose={onCloseModal}
          onSubmit={async (body) => { await onCreateContact(body); onCloseModal(); }}
        />
      )}
      {modal === 'account' && (
        <AccountModal
          onClose={onCloseModal}
          onSubmit={async (body) => { await onCreateAccount(body); onCloseModal(); }}
        />
      )}
      {showNewActivity && (
        <ActivityFormModal
          contacts={contacts}
          onClose={onCloseNewActivity}
          onSubmit={async (body) => { await onCreateActivity(body); onCloseNewActivity(); }}
        />
      )}
      {activityToEdit && (
        <ActivityFormModal
          activity={activityToEdit}
          contacts={contacts}
          onClose={onCloseActivityEdit}
          onSubmit={async (body) => { await onUpdateActivity(activityToEdit.id, body); onCloseActivityEdit(); }}
        />
      )}
      {contactToEdit && (
        <ContactEditModal
          contact={contactToEdit}
          onClose={onCloseContactEdit}
          onSubmit={async (body) => { await onUpdateContact(contactToEdit.id, body); onCloseContactEdit(); }}
        />
      )}
      {dealToEdit && (
        <DealEditModal
          deal={dealToEdit}
          onClose={onCloseDealEdit}
          onSubmit={async (body) => { await onUpdateDeal(dealToEdit.id, body); onCloseDealEdit(); }}
        />
      )}
      {showImportModal && (
        <ImportModal
          onClose={onCloseImportModal}
          onSuccess={onImportSuccess}
        />
      )}
    </>
  );
}
