import { useAppState } from './hooks/useAppState';
import { AppHeader } from './components/AppHeader';
import { AppModals } from './components/AppModals';
import { PipelineView } from './features/pipeline/PipelineView';
import { DealDetailView } from './features/pipeline/DealDetailView';
import { ContactsView } from './features/contacts/ContactsView';
import { ContactDetailView } from './features/contacts/ContactDetailView';
import { AccountsView } from './features/accounts/AccountsView';
import { AccountDetailView } from './features/accounts/AccountDetailView';
import { ActivitiesView } from './features/activities/ActivitiesView';
import { ActivityDetailView } from './features/activities/ActivityDetailView';
import { TodayView } from './features/today/TodayView';
import { StatsView } from './features/stats/StatsView';
import { InsightsView } from './features/insights/InsightsView';
import { LoginView } from './features/auth/LoginView';

function isLoginPath() {
  return window.location.pathname.endsWith('/login.html');
}

export function App() {
  const {
    isAuthenticated, user, handleLogin, logout, activeTab, setActiveTab,
    stages, deals, contacts, accounts, activities, today, savedViews, loading,
    filteredDeals, setFilteredDeals, filteredContacts, setFilteredContacts,
    activeSavedView, setActiveSavedView, stats, forecastTotal,
    draggedDealId, setDraggedDealId,
    selectedAccount, setSelectedAccount, selectedContact, setSelectedContact,
    selectedDeal, setSelectedDeal, selectedActivity, setSelectedActivity,
    setSelectedAccountId,
    modal, setModal, contactToEdit, setContactToEdit,
    dealToEdit, setDealToEdit, activityToEdit, setActivityToEdit,
    showNewActivity, setShowNewActivity, showImportModal, setShowImportModal,
    toast, createDeal, updateDeal, deleteDeal, moveDeal,
    createContact, updateContact, deleteContact, createAccount, updateAccount, deleteAccount,
    createActivity, updateActivity, deleteActivity,
    isEditModalOpen, openAccountEdit, closeAccountEdit,
    dismissReminder, applySavedView, exportContacts, handleImportSuccess,
  } = useAppState();

  if (!isAuthenticated || isLoginPath()) {
    return <LoginView onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-paper text-ink">
      <AppHeader activeTab={activeTab} onTabChange={setActiveTab} user={user} onLogout={logout} />

      <main className="px-4 py-5 lg:px-6">
        {activeTab === 'pipeline' && (
          selectedDeal ? (
            <DealDetailView
              deal={selectedDeal}
              contacts={contacts}
              onBack={() => setSelectedDeal(null)}
              onEdit={() => setDealToEdit(selectedDeal)}
              onDelete={() => void deleteDeal(selectedDeal.id)}
            />
          ) : (
            <PipelineView
              activeSavedView={activeSavedView.deals}
              contacts={contacts}
              deals={filteredDeals ?? deals}
              forecastTotal={forecastTotal}
              loading={loading}
              onApplySavedView={(id, name) => applySavedView(id, 'deals', name)}
              onClearSavedView={() => {
                setFilteredDeals(null);
                setActiveSavedView((prev) => ({ ...prev, deals: undefined }));
              }}
              onMoveDeal={(dealId, stageId) => moveDeal(dealId, stageId)}
              onOpenModal={() => setModal('deal')}
              onOpenDeal={(d) => setSelectedDeal(d)}
              savedViews={savedViews.filter((view) => view.entity_type === 'deals')}
              setDraggedDealId={setDraggedDealId}
              draggedDealId={draggedDealId}
              stages={stages}
            />
          )
        )}
        {activeTab === 'contacts' && (
          selectedContact ? (
            <ContactDetailView
              contact={selectedContact}
              onBack={() => setSelectedContact(null)}
              onEdit={() => setContactToEdit(selectedContact)}
              onDelete={() => void deleteContact(selectedContact.id)}
            />
          ) : (
            <ContactsView
              accounts={accounts}
              activeSavedView={activeSavedView.contacts}
              contacts={filteredContacts ?? contacts}
              onApplySavedView={(id, name) => applySavedView(id, 'contacts', name)}
              onClearSavedView={() => {
                setFilteredContacts(null);
                setActiveSavedView((prev) => ({ ...prev, contacts: undefined }));
              }}
              onOpenAccount={(id) => {
                setActiveTab('accounts');
                setSelectedAccountId(id);
              }}
              onOpenContact={(contact) => setSelectedContact(contact)}
              onOpenModal={() => setModal('contact')}
              onImport={() => setShowImportModal(true)}
              onExport={() => void exportContacts()}
              savedViews={savedViews.filter((view) => view.entity_type === 'contacts')}
            />
          )
        )}
        {activeTab === 'accounts' && (
          selectedAccount ? (
            <AccountDetailView
              account={selectedAccount}
              onBack={() => {
                setSelectedAccountId(null);
                setSelectedAccount(null);
              }}
              onEdit={openAccountEdit}
              onDelete={() => void deleteAccount(selectedAccount.id)}
            />
          ) : (
            <AccountsView
              accounts={accounts}
              onOpenAccount={(id) => setSelectedAccountId(id)}
              onOpenModal={() => setModal('account')}
            />
          )
        )}
        {activeTab === 'activities' && (
          selectedActivity ? (
            <ActivityDetailView
              activity={selectedActivity}
              contacts={contacts}
              onBack={() => setSelectedActivity(null)}
              onEdit={() => setActivityToEdit(selectedActivity)}
              onDelete={() => void deleteActivity(selectedActivity.id)}
            />
          ) : (
            <ActivitiesView
              activities={activities}
              contacts={contacts}
              onOpenModal={() => setShowNewActivity(true)}
              onOpenActivity={(a) => setSelectedActivity(a)}
            />
          )
        )}
        {activeTab === 'today' && <TodayView reminders={today} onDismiss={dismissReminder} />}
        {activeTab === 'stats' && <StatsView stats={stats} />}
        {activeTab === 'insights' && <InsightsView />}
      </main>

      <AppModals
        contacts={contacts}
        accounts={accounts}
        modal={modal}
        onCloseModal={() => setModal(null)}
        accountToEdit={isEditModalOpen ? selectedAccount : null}
        onCloseAccountEdit={closeAccountEdit}
        contactToEdit={contactToEdit}
        onCloseContactEdit={() => setContactToEdit(null)}
        dealToEdit={dealToEdit}
        onCloseDealEdit={() => setDealToEdit(null)}
        activityToEdit={activityToEdit}
        onCloseActivityEdit={() => setActivityToEdit(null)}
        showNewActivity={showNewActivity}
        onCloseNewActivity={() => setShowNewActivity(false)}
        showImportModal={showImportModal}
        onImportSuccess={handleImportSuccess}
        onCloseImportModal={() => setShowImportModal(false)}
        onCreateDeal={createDeal}
        onCreateContact={createContact}
        onCreateAccount={createAccount}
        onCreateActivity={createActivity}
        onUpdateActivity={updateActivity}
        onUpdateAccount={updateAccount}
        onUpdateContact={updateContact}
        onUpdateDeal={updateDeal}
      />

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-md bg-slate-950 px-4 py-2 text-sm font-semibold text-white shadow-xl">
          {toast}
        </div>
      )}
    </div>
  );
}
