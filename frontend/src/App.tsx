import {
  BarChart3,
  Bell,
  Building2,
  Calendar,
  ContactRound,
  ArrowLeft,
  LogOut,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  UserRound,
} from 'lucide-react';
import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import type { Tab, User, Contact, Deal, Account, Activity, Reminder, PipelineStage, StatsData, SavedView } from './types';
import { apiFetch, getToken, storedUser } from './lib/api';
import { money, numberText } from './lib/formatters';
import { TextField } from './components/ui/TextField';
import { ModalShell } from './components/ui/ModalShell';
import { ModalActions } from './components/ui/ModalActions';
import { SectionHeader } from './components/ui/SectionHeader';
import { PipelineView } from './features/pipeline/PipelineView';
import { DealDetailView } from './features/pipeline/DealDetailView';
import { DealModal } from './features/pipeline/DealModal';
import { DealEditModal } from './features/pipeline/DealEditModal';
import { ContactsView } from './features/contacts/ContactsView';
import { ContactDetailView } from './features/contacts/ContactDetailView';
import { ContactModal } from './features/contacts/ContactModal';
import { ContactEditModal } from './features/contacts/ContactEditModal';
import { ImportModal } from './features/contacts/ImportModal';

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

function LoginView({ onLogin }: { onLogin: (email: string, password: string) => Promise<void> }) {
  const [email, setEmail] = useState('admin@closeloop.com');
  const [password, setPassword] = useState('admin123');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onLogin(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <header className="flex h-14 items-center border-b border-slate-800 bg-slate-950 px-5 text-white">
        <div className="flex items-center gap-2 text-sm font-bold tracking-wide">
          <RefreshCw size={18} aria-hidden="true" />
          CloseLoop CRM
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <form className="panel w-full max-w-sm p-6" onSubmit={submit}>
          <h1 className="text-lg font-bold text-slate-950">Sign in</h1>
          <p className="mt-1 text-sm text-slate-500">Access your CRM workspace.</p>
          <div className="mt-5 space-y-4">
            <label className="block">
              <span className="field-label">Email</span>
              <input className="field-input" value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" required />
            </label>
            <label className="block">
              <span className="field-label">Password</span>
              <input className="field-input" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete="current-password" required />
            </label>
          </div>
          {error && <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
          <button className="primary-button mt-5 w-full justify-center" disabled={busy} type="submit">
            {busy ? 'Signing in' : 'Sign in'}
          </button>
          <div className="mt-4 text-center text-xs text-slate-400">v2.1 React</div>
        </form>
      </main>
    </div>
  );
}

function AccountsView({
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

function ActivitiesView({
  activities,
  contacts,
  onOpenModal,
  onOpenActivity,
}: {
  activities: Activity[];
  contacts: Contact[];
  onOpenModal: () => void;
  onOpenActivity: (activity: Activity) => void;
}) {
  const contactById = useMemo(() => new Map(contacts.map((c) => [c.id, c])), [contacts]);
  return (
    <>
      <SectionHeader
        title="Activities"
        action={
          <button className="primary-button" onClick={onOpenModal} type="button">
            <Plus size={16} aria-hidden="true" />
            New Activity
          </button>
        }
      />
      <div className="panel overflow-hidden">
        <table className="w-full border-collapse">
          <thead className="table-head">
            <tr>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Contact</th>
              <th className="px-4 py-3">Due</th>
            </tr>
          </thead>
          <tbody>
            {activities.map((activity) => {
              const contact = activity.contact_id ? contactById.get(activity.contact_id) : null;
              return (
                <tr key={activity.id} className="hover:bg-slate-50">
                  <td className="table-cell font-semibold text-slate-900">
                    <button
                      className="font-semibold text-blue-700 hover:underline text-left"
                      onClick={() => onOpenActivity(activity)}
                      type="button"
                    >
                      {activity.title}
                    </button>
                  </td>
                  <td className="table-cell">
                    <span className="rounded-full bg-blue-50 px-2 py-1 text-xs font-bold text-blue-700 uppercase">{activity.type}</span>
                  </td>
                  <td className="table-cell">{contact?.name || ''}</td>
                  <td className="table-cell">{activity.due_at ? new Date(activity.due_at).toLocaleDateString() : ''}</td>
                </tr>
              );
            })}
            {activities.length === 0 && (
              <tr>
                <td className="px-4 py-10 text-center text-sm text-slate-500" colSpan={4}>
                  No activities yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ActivityDetailView({
  activity,
  contacts,
  onBack,
  onEdit,
  onDelete,
}: {
  activity: Activity;
  contacts: Contact[];
  onBack: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const contact = contacts.find((c) => c.id === activity.contact_id);
  return (
    <>
      <SectionHeader
        title={activity.title}
        action={
          <div className="flex gap-2">
            <button className="secondary-button" onClick={onBack} type="button">
              <ArrowLeft size={16} aria-hidden="true" />
              Back
            </button>
            <button className="secondary-button" onClick={onEdit} type="button">
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
      <div className="panel p-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['Type', activity.type],
            ['Contact', contact?.name || 'None'],
            ['Due', activity.due_at ? new Date(activity.due_at).toLocaleString() : 'Not set'],
            ['Completed', activity.completed_at ? new Date(activity.completed_at).toLocaleString() : 'No'],
          ].map(([label, value]) => (
            <div key={label as string}>
              <div className="text-xs font-bold uppercase text-slate-500">{label as string}</div>
              <div className="mt-1 text-sm text-slate-800">{(value as string) || 'Not set'}</div>
            </div>
          ))}
        </div>
        {activity.body && (
          <div className="mt-4">
            <div className="text-xs font-bold uppercase text-slate-500">Notes</div>
            <div className="mt-1 text-sm text-slate-800 whitespace-pre-wrap">{activity.body}</div>
          </div>
        )}
      </div>
    </>
  );
}

function TodayView({ reminders, onDismiss }: { reminders: Reminder[]; onDismiss: (id: number) => void }) {
  return (
    <>
      <SectionHeader title="Today" />
      {reminders.length === 0 && <div className="panel p-10 text-center text-sm text-slate-500">No reminders due today. You are all caught up.</div>}
      <div className="space-y-2">
        {reminders.map((item) => (
          <div key={item.id} className="panel flex items-center gap-3 p-3">
            <span className="rounded-md bg-blue-50 px-2 py-1 text-xs font-bold uppercase text-blue-700">{item.activity_type || 'note'}</span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-slate-950">{item.activity_title || 'Reminder'}</div>
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                {item.deal_title && <span>{item.deal_title}</span>}
                {item.contact_name && <span>{item.contact_name}</span>}
                {item.remind_at && <span>{new Date(item.remind_at).toLocaleString()}</span>}
              </div>
            </div>
            <button className="secondary-button" onClick={() => onDismiss(item.id)} type="button">
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

function StatsView({ stats }: { stats: StatsData | null }) {
  const cards = stats
    ? [
        ['Total Contacts', numberText(stats.total_contacts)],
        ['Total Deals', numberText(stats.total_deals)],
        ['Total Activities', numberText(stats.total_activities)],
        ['Pipeline Value', money(stats.pipeline_value), 'open deals face value'],
        ['Weighted Forecast', money(stats.weighted_forecast), 'open deals probability weighted'],
        ['Activities (30d)', numberText(stats.activities_last_30_days), 'last 30 days'],
        ['Outbox Queued', numberText(stats.outbox_queued), 'unsent messages'],
      ]
    : [];
  return (
    <>
      <SectionHeader title="Stats" />
      {!stats && <div className="panel p-10 text-center text-sm text-slate-500">Loading stats.</div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value, sub]) => (
          <div key={label} className="panel p-4">
            <div className="text-xs font-bold uppercase text-slate-500">{label}</div>
            <div className="mt-2 text-2xl font-bold text-slate-950">{value}</div>
            {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
          </div>
        ))}
      </div>
      {stats?.deals_by_stage && Object.keys(stats.deals_by_stage).length > 0 && (
        <div className="panel mt-4 p-4">
          <h2 className="mb-3 text-sm font-bold text-slate-900">Deals by Stage</h2>
          <div className="divide-y divide-slate-100">
            {Object.entries(stats.deals_by_stage).map(([stage, count]) => (
              <div key={stage} className="flex justify-between py-2 text-sm">
                <span>{stage}</span>
                <span className="font-semibold">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function AccountModal({ onClose, onSubmit }: { onClose: () => void; onSubmit: (body: Partial<Account> & { name: string }) => Promise<void> }) {
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

const ACTIVITY_TYPES = ['call', 'email', 'meeting', 'note'] as const;

function ActivityModal({
  activity,
  contacts,
  onClose,
  onSubmit,
}: {
  activity?: Activity;
  contacts: Contact[];
  onClose: () => void;
  onSubmit: (body: { title: string; type: string; body?: string; contact_id?: number }) => Promise<void>;
}) {
  const [title, setTitle] = useState(activity?.title ?? '');
  const [type, setType] = useState(activity?.type ?? 'call');
  const [body, setBody] = useState(activity?.body ?? '');
  const [contactId, setContactId] = useState(String(activity?.contact_id ?? ''));
  const isEdit = Boolean(activity);
  return (
    <ModalShell title={isEdit ? 'Edit Activity' : 'New Activity'} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit({
            title: title.trim(),
            type,
            body: body.trim() || undefined,
            contact_id: contactId ? Number(contactId) : undefined,
          });
        }}
      >
        <TextField label="Title" value={title} onChange={setTitle} required />
        <label className="block">
          <span className="field-label">Type</span>
          <select className="field-input" value={type} onChange={(e) => setType(e.target.value)}>
            {ACTIVITY_TYPES.map((t) => (
              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="field-label">Contact</span>
          <select className="field-input" value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">None</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="field-label">Notes</span>
          <textarea
            className="field-input"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
          />
        </label>
        <ModalActions onClose={onClose} submitLabel={isEdit ? 'Save' : 'Create'} />
      </form>
    </ModalShell>
  );
}


