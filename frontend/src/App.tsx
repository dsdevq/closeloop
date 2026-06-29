import {
  BarChart3,
  Bell,
  Building2,
  Calendar,
  ContactRound,
  LogOut,
  RefreshCw,
  UserRound,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import type { Tab, User, Contact, Deal, Account, Activity, Reminder, PipelineStage, StatsData, SavedView } from './types';
import { apiFetch, getToken, storedUser } from './lib/api';
import { PipelineView } from './features/pipeline/PipelineView';
import { DealDetailView } from './features/pipeline/DealDetailView';
import { DealModal } from './features/pipeline/DealModal';
import { DealEditModal } from './features/pipeline/DealEditModal';
import { ContactsView } from './features/contacts/ContactsView';
import { ContactDetailView } from './features/contacts/ContactDetailView';
import { ContactModal } from './features/contacts/ContactModal';
import { ContactEditModal } from './features/contacts/ContactEditModal';
import { ImportModal } from './features/contacts/ImportModal';
import { AccountsView } from './features/accounts/AccountsView';
import { AccountModal } from './features/accounts/AccountModal';
import { ActivitiesView } from './features/activities/ActivitiesView';
import { ActivityDetailView } from './features/activities/ActivityDetailView';
import { ActivityModal } from './features/activities/ActivityModal';
import { TodayView } from './features/today/TodayView';
import { StatsView } from './features/stats/StatsView';
import { LoginView } from './features/auth/LoginView';

function isLoginPath() {
  return window.location.pathname.endsWith('/login.html');
}

export function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(Boolean(getToken()));
  const [user, setUser] = useState<User>(storedUser);
  const [activeTab, setActiveTab] = useState<Tab>('pipeline');
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [today, setToday] = useState<Reminder[]>([]);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [filteredDeals, setFilteredDeals] = useState<Deal[] | null>(null);
  const [filteredContacts, setFilteredContacts] = useState<Contact[] | null>(null);
  const [activeSavedView, setActiveSavedView] = useState<{ contacts?: string; deals?: string }>({});
  const [stats, setStats] = useState<StatsData | null>(null);
  const [forecastTotal, setForecastTotal] = useState<number | null>(null);
  const [draggedDealId, setDraggedDealId] = useState<number | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<Activity | null>(null);
  const [modal, setModal] = useState<'deal' | 'contact' | 'account' | null>(null);
  const [contactToEdit, setContactToEdit] = useState<Contact | null>(null);
  const [dealToEdit, setDealToEdit] = useState<Deal | null>(null);
  const [activityToEdit, setActivityToEdit] = useState<Activity | null>(null);
  const [showNewActivity, setShowNewActivity] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [toast, setToast] = useState('');
  const [loading, setLoading] = useState(false);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 3200);
  }, []);

  const refreshCore = useCallback(async () => {
    setLoading(true);
    try {
      const [stagesRes, dealsRes, contactsRes, accountsRes, todayRes, savedRes, forecastRes, activitiesRes] =
        await Promise.all([
          apiFetch('/pipeline/stages'),
          apiFetch('/deals'),
          apiFetch('/contacts'),
          apiFetch('/accounts'),
          apiFetch('/reminders/today'),
          apiFetch('/saved-views'),
          apiFetch('/forecast'),
          apiFetch('/activities'),
        ]);

      if (stagesRes.ok) setStages(await stagesRes.json());
      if (dealsRes.ok) setDeals(await dealsRes.json());
      if (contactsRes.ok) setContacts(await contactsRes.json());
      if (accountsRes.ok) setAccounts(await accountsRes.json());
      if (todayRes.ok) setToday(await todayRes.json());
      if (savedRes.ok) setSavedViews(await savedRes.json());
      if (forecastRes.ok) {
        const forecast = await forecastRes.json();
        setForecastTotal(Number(forecast.total || 0));
      }
      if (activitiesRes.ok) setActivities(await activitiesRes.json());
    } catch {
      showToast('Could not load CloseLoop data');
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (isLoginPath() && isAuthenticated) {
      window.history.replaceState(null, '', '/');
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) return;
    void refreshCore();
  }, [isAuthenticated, refreshCore]);

  useEffect(() => {
    if (activeTab !== 'stats' || !isAuthenticated) return;
    apiFetch('/stats')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => data && setStats(data))
      .catch(() => showToast('Failed to load stats'));
  }, [activeTab, isAuthenticated, showToast]);

  useEffect(() => {
    if (!selectedAccountId) return;
    apiFetch(`/accounts/${selectedAccountId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data) {
          showToast('Account not found');
          return;
        }
        setSelectedAccount(data);
      })
      .catch(() => showToast('Could not load account'));
  }, [selectedAccountId, showToast]);

  async function handleLogin(email: string, password: string) {
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Invalid email or password');
    }
    const data = await response.json();
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('current_user', JSON.stringify(data.user));
    setUser(data.user);
    setIsAuthenticated(true);
  }

  async function logout() {
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) {
      await fetch('/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      }).catch(() => undefined);
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('current_user');
    setIsAuthenticated(false);
    window.history.replaceState(null, '', '/login.html');
  }

  if (!isAuthenticated || isLoginPath()) {
    return <LoginView onLogin={handleLogin} />;
  }

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950 text-white shadow-lg">
        <div className="flex min-h-14 flex-wrap items-center gap-3 px-4 lg:flex-nowrap lg:px-6">
          <div className="flex items-center gap-2 pr-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600">
              <RefreshCw size={17} aria-hidden="true" />
            </div>
            <div className="whitespace-nowrap text-sm font-bold tracking-wide">CloseLoop CRM</div>
          </div>

          <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
            {[
              ['pipeline', BarChart3, 'Pipeline'],
              ['contacts', ContactRound, 'Contacts'],
              ['accounts', Building2, 'Accounts'],
              ['activities', Calendar, 'Activities'],
              ['today', Bell, 'Today'],
              ['stats', BarChart3, 'Stats'],
            ].map(([tab, Icon, label]) => (
              <button
                key={tab as string}
                className={`inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm transition ${
                  activeTab === tab
                    ? 'bg-white text-slate-950'
                    : 'text-slate-300 hover:bg-white/10 hover:text-white'
                }`}
                onClick={() => setActiveTab(tab as Tab)}
                type="button"
              >
                <Icon size={16} aria-hidden="true" />
                {label as string}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <div className="hidden items-center gap-2 rounded-md bg-white/10 px-2.5 py-1.5 text-xs text-slate-200 sm:flex">
              <UserRound size={14} aria-hidden="true" />
              <span className="max-w-48 truncate">{user.full_name || user.email}</span>
              <span className="rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-bold uppercase">
                {user.role || 'user'}
              </span>
            </div>
            <button className="icon-button border-white/25 bg-transparent text-slate-200 hover:text-white" onClick={logout} title="Sign out" type="button">
              <LogOut size={17} aria-hidden="true" />
            </button>
          </div>
        </div>
      </header>

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
          <AccountsView
            account={selectedAccount}
            accounts={accounts}
            onBack={() => {
              setSelectedAccountId(null);
              setSelectedAccount(null);
            }}
            onDeleteAccount={deleteAccount}
            onOpenAccount={(id) => setSelectedAccountId(id)}
            onOpenModal={() => setModal('account')}
          />
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
      </main>

      {modal === 'deal' && (
        <DealModal
          contacts={contacts}
          onClose={() => setModal(null)}
          onSubmit={async (body) => {
            await createDeal(body);
            setModal(null);
          }}
        />
      )}
      {modal === 'contact' && (
        <ContactModal
          accounts={accounts}
          onClose={() => setModal(null)}
          onSubmit={async (body) => {
            await createContact(body);
            setModal(null);
          }}
        />
      )}
      {modal === 'account' && (
        <AccountModal
          onClose={() => setModal(null)}
          onSubmit={async (body) => {
            await createAccount(body);
            setModal(null);
          }}
        />
      )}
      {showNewActivity && (
        <ActivityModal
          contacts={contacts}
          onClose={() => setShowNewActivity(false)}
          onSubmit={async (body) => {
            await createActivity(body);
            setShowNewActivity(false);
          }}
        />
      )}
      {activityToEdit && (
        <ActivityModal
          activity={activityToEdit}
          contacts={contacts}
          onClose={() => setActivityToEdit(null)}
          onSubmit={async (body) => {
            await updateActivity(activityToEdit.id, body);
            setActivityToEdit(null);
          }}
        />
      )}
      {contactToEdit && (
        <ContactEditModal
          contact={contactToEdit}
          onClose={() => setContactToEdit(null)}
          onSubmit={async (body) => {
            await updateContact(contactToEdit.id, body);
            setContactToEdit(null);
          }}
        />
      )}
      {dealToEdit && (
        <DealEditModal
          deal={dealToEdit}
          onClose={() => setDealToEdit(null)}
          onSubmit={async (body) => {
            await updateDeal(dealToEdit.id, body);
            setDealToEdit(null);
          }}
        />
      )}
      {showImportModal && (
        <ImportModal
          onClose={() => setShowImportModal(false)}
          onSuccess={(count) => {
            showToast(`Imported ${count} contact${count !== 1 ? 's' : ''}`);
            setShowImportModal(false);
            void refreshCore();
          }}
        />
      )}

      {toast && (
        <div className="fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-md bg-slate-950 px-4 py-2 text-sm font-semibold text-white shadow-xl">
          {toast}
        </div>
      )}
    </div>
  );

  async function createDeal(body: { title: string; contact_id: number; value: number }) {
    const response = await apiFetch('/deals', { method: 'POST', body: JSON.stringify(body) });
    if (!response.ok) {
      showToast('Failed to create deal');
      return;
    }
    const deal = await response.json();
    setDeals((prev) => [...prev, deal]);
  }

  async function updateDeal(id: number, body: Partial<Deal>) {
    const response = await apiFetch(`/deals/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (!response.ok) { showToast('Failed to update deal'); return; }
    const updated = await response.json();
    setDeals((prev) => prev.map((d) => (d.id === id ? updated : d)));
    if (selectedDeal?.id === id) setSelectedDeal(updated);
  }

  async function deleteDeal(id: number) {
    if (!window.confirm('Delete this deal?')) return;
    const response = await apiFetch(`/deals/${id}`, { method: 'DELETE' });
    if (!response.ok) { showToast('Failed to delete deal'); return; }
    setDeals((prev) => prev.filter((d) => d.id !== id));
    setSelectedDeal(null);
  }

  async function createContact(body: Partial<Contact> & { name: string }) {
    const response = await apiFetch('/contacts', { method: 'POST', body: JSON.stringify(body) });
    if (!response.ok) {
      showToast('Failed to create contact');
      return;
    }
    const contact = await response.json();
    setContacts((prev) => [...prev, contact]);
  }

  async function updateContact(id: number, body: Partial<Contact>) {
    const response = await apiFetch(`/contacts/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (!response.ok) { showToast('Failed to update contact'); return; }
    const updated = await response.json();
    setContacts((prev) => prev.map((c) => (c.id === id ? updated : c)));
    if (selectedContact?.id === id) setSelectedContact(updated);
  }

  async function deleteContact(id: number) {
    if (!window.confirm('Delete this contact?')) return;
    const response = await apiFetch(`/contacts/${id}`, { method: 'DELETE' });
    if (!response.ok) { showToast('Failed to delete contact'); return; }
    setContacts((prev) => prev.filter((c) => c.id !== id));
    setSelectedContact(null);
  }

  async function createAccount(body: Partial<Account> & { name: string }) {
    const response = await apiFetch('/accounts', { method: 'POST', body: JSON.stringify(body) });
    if (!response.ok) {
      showToast('Failed to create account');
      return;
    }
    const account = await response.json();
    setAccounts((prev) => [...prev, account]);
  }

  async function createActivity(body: { title: string; type: string; body?: string; contact_id?: number }) {
    const response = await apiFetch('/activities', { method: 'POST', body: JSON.stringify(body) });
    if (!response.ok) { showToast('Failed to create activity'); return; }
    const activity = await response.json();
    setActivities((prev) => [...prev, activity]);
  }

  async function updateActivity(id: number, body: Partial<Activity>) {
    const response = await apiFetch(`/activities/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (!response.ok) { showToast('Failed to update activity'); return; }
    const updated = await response.json();
    setActivities((prev) => prev.map((a) => (a.id === id ? updated : a)));
    if (selectedActivity?.id === id) setSelectedActivity(updated);
  }

  async function deleteActivity(id: number) {
    if (!window.confirm('Delete this activity?')) return;
    const response = await apiFetch(`/activities/${id}`, { method: 'DELETE' });
    if (!response.ok) { showToast('Failed to delete activity'); return; }
    setActivities((prev) => prev.filter((a) => a.id !== id));
    setSelectedActivity(null);
  }

  async function moveDeal(dealId: number, stageId: number) {
    const response = await apiFetch(`/deals/${dealId}`, {
      method: 'PATCH',
      body: JSON.stringify({ stage_id: stageId }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      showToast(data.detail || 'Could not move deal');
      return;
    }
    const updated = await response.json();
    setDeals((prev) => prev.map((deal) => (deal.id === updated.id ? updated : deal)));
    if (filteredDeals) setFilteredDeals((prev) => prev?.map((deal) => (deal.id === updated.id ? updated : deal)) ?? null);
  }

  async function dismissReminder(id: number) {
    const response = await apiFetch(`/reminders/${id}/dismiss`, { method: 'PATCH' });
    if (!response.ok) {
      showToast('Failed to dismiss reminder');
      return;
    }
    setToday((prev) => prev.filter((item) => item.id !== id));
  }

  async function applySavedView(id: number, entityType: 'contacts' | 'deals', name: string) {
    const response = await apiFetch(`/saved-views/${id}/apply`, { method: 'POST' });
    if (!response.ok) {
      showToast('Failed to apply view');
      return;
    }
    const results = await response.json();
    setActiveSavedView((prev) => ({ ...prev, [entityType]: name }));
    if (entityType === 'contacts') setFilteredContacts(results);
    else setFilteredDeals(results);
  }

  async function deleteAccount(id: number) {
    if (!window.confirm('Delete this account?')) return;
    const response = await apiFetch(`/accounts/${id}`, { method: 'DELETE' });
    if (!response.ok) {
      showToast('Failed to delete account');
      return;
    }
    setAccounts((prev) => prev.filter((account) => account.id !== id));
    setSelectedAccountId(null);
    setSelectedAccount(null);
  }

  async function exportContacts() {
    const res = await apiFetch('/contacts/export');
    if (!res.ok) { showToast('Export failed'); return; }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'contacts.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Contacts exported');
  }
}


