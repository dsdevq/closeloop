import {
  ArrowLeft,
  BarChart3,
  Bell,
  Building2,
  ContactRound,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserRound,
} from 'lucide-react';
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch, getToken } from './api';
import { ImportExportBar } from './components/ImportExportBar';

type Tab = 'pipeline' | 'contacts' | 'accounts' | 'today' | 'stats';

type User = {
  id?: number;
  email?: string;
  full_name?: string;
  role?: string;
};

type PipelineStage = {
  id: number;
  name: string;
  position: number;
  probability: number;
};

type Deal = {
  id: number;
  title: string;
  value?: number | null;
  probability?: number | null;
  stage_id?: number | null;
  stage?: string | null;
  contact_id?: number | null;
  contact_name?: string | null;
};

type Contact = {
  id: number;
  name: string;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  lead_score?: number | null;
  account_id?: number | null;
};

type Account = {
  id: number;
  name: string;
  domain?: string | null;
  industry?: string | null;
  website?: string | null;
  phone?: string | null;
  address?: string | null;
  owner_id?: number | null;
  contact_count?: number | null;
  contacts?: Contact[];
};

type Reminder = {
  id: number;
  activity_title?: string | null;
  activity_type?: string | null;
  deal_title?: string | null;
  contact_name?: string | null;
  remind_at?: string | null;
};

type SavedView = {
  id: number;
  name: string;
  entity_type: 'contacts' | 'deals';
};

type Stats = {
  total_contacts: number;
  total_deals: number;
  total_activities: number;
  pipeline_value: number;
  weighted_forecast: number;
  activities_last_30_days: number;
  outbox_queued: number;
  deals_by_stage?: Record<string, number>;
};

const stagePalette = [
  'border-l-blue-600',
  'border-l-cyan-600',
  'border-l-amber-500',
  'border-l-orange-500',
  'border-l-emerald-600',
  'border-l-red-600',
  'border-l-violet-600',
  'border-l-pink-600',
];

function storedUser(): User {
  try {
    return JSON.parse(localStorage.getItem('current_user') || '{}') as User;
  } catch {
    return {};
  }
}

function money(value: number | null | undefined) {
  return `$${Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

function numberText(value: number | null | undefined) {
  return Number(value || 0).toLocaleString('en-US');
}

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
  const [today, setToday] = useState<Reminder[]>([]);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [filteredDeals, setFilteredDeals] = useState<Deal[] | null>(null);
  const [filteredContacts, setFilteredContacts] = useState<Contact[] | null>(null);
  const [activeSavedView, setActiveSavedView] = useState<{ contacts?: string; deals?: string }>({});
  const [stats, setStats] = useState<Stats | null>(null);
  const [forecastTotal, setForecastTotal] = useState<number | null>(null);
  const [draggedDealId, setDraggedDealId] = useState<number | null>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [modal, setModal] = useState<'deal' | 'contact' | 'account' | null>(null);
  const [toast, setToast] = useState('');
  const [loading, setLoading] = useState(false);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 3200);
  }, []);

  const refreshCore = useCallback(async () => {
    setLoading(true);
    try {
      const [stagesRes, dealsRes, contactsRes, accountsRes, todayRes, savedRes, forecastRes] =
        await Promise.all([
          apiFetch('/pipeline/stages'),
          apiFetch('/deals'),
          apiFetch('/contacts'),
          apiFetch('/accounts'),
          apiFetch('/reminders/today'),
          apiFetch('/saved-views'),
          apiFetch('/forecast'),
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
            onCreateDeal={(body) => createDeal(body)}
            onImportDone={refreshCore}
            onMoveDeal={(dealId, stageId) => moveDeal(dealId, stageId)}
            onOpenModal={() => setModal('deal')}
            savedViews={savedViews.filter((view) => view.entity_type === 'deals')}
            setDraggedDealId={setDraggedDealId}
            draggedDealId={draggedDealId}
            stages={stages}
          />
        )}
        {activeTab === 'contacts' && (
          <ContactsView
            accounts={accounts}
            activeSavedView={activeSavedView.contacts}
            contacts={filteredContacts ?? contacts}
            onApplySavedView={(id, name) => applySavedView(id, 'contacts', name)}
            onClearSavedView={() => {
              setFilteredContacts(null);
              setActiveSavedView((prev) => ({ ...prev, contacts: undefined }));
            }}
            onImportDone={refreshCore}
            onOpenAccount={(id) => {
              setActiveTab('accounts');
              setSelectedAccountId(id);
            }}
            onOpenModal={() => setModal('contact')}
            savedViews={savedViews.filter((view) => view.entity_type === 'contacts')}
          />
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
        {activeTab === 'today' && <TodayView reminders={today} onDismiss={dismissReminder} onImportDone={refreshCore} />}
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

  async function createContact(body: Partial<Contact> & { name: string }) {
    const response = await apiFetch('/contacts', { method: 'POST', body: JSON.stringify(body) });
    if (!response.ok) {
      showToast('Failed to create contact');
      return;
    }
    const contact = await response.json();
    setContacts((prev) => [...prev, contact]);
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

function SectionHeader({
  title,
  action,
}: {
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3">
      <h1 className="text-base font-bold text-slate-950">{title}</h1>
      {action}
    </div>
  );
}

function SavedViewsBar({
  views,
  activeName,
  onApply,
  onClear,
}: {
  views: SavedView[];
  activeName?: string;
  onApply: (id: number, name: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="panel mb-4 flex flex-wrap items-center gap-2 px-3 py-2">
      <div className="flex items-center gap-2 pr-2 text-xs font-bold uppercase text-slate-500">
        <Search size={14} aria-hidden="true" />
        Saved Views
      </div>
      {views.length === 0 && <span className="text-sm text-slate-400">No saved views</span>}
      {views.map((view) => (
        <button key={view.id} className="secondary-button h-8 px-2.5 text-xs" onClick={() => onApply(view.id, view.name)} type="button">
          {view.name}
        </button>
      ))}
      {activeName && (
        <>
          <span className="ml-auto text-sm text-blue-700">Showing: {activeName}</span>
          <button className="secondary-button h-8 px-2.5 text-xs" onClick={onClear} type="button">
            Clear
          </button>
        </>
      )}
    </div>
  );
}

function PipelineView({
  activeSavedView,
  contacts,
  deals,
  draggedDealId,
  forecastTotal,
  loading,
  onApplySavedView,
  onClearSavedView,
  onImportDone,
  onMoveDeal,
  onOpenModal,
  savedViews,
  setDraggedDealId,
  stages,
}: {
  activeSavedView?: string;
  contacts: Contact[];
  deals: Deal[];
  draggedDealId: number | null;
  forecastTotal: number | null;
  loading: boolean;
  onApplySavedView: (id: number, name: string) => void;
  onClearSavedView: () => void;
  onCreateDeal: (body: { title: string; contact_id: number; value: number }) => Promise<void>;
  onImportDone: () => void;
  onMoveDeal: (dealId: number, stageId: number) => void;
  onOpenModal: () => void;
  savedViews: SavedView[];
  setDraggedDealId: (id: number | null) => void;
  stages: PipelineStage[];
}) {
  const contactById = useMemo(() => new Map(contacts.map((contact) => [contact.id, contact])), [contacts]);

  return (
    <>
      <SectionHeader
        title="Pipeline"
        action={
          <button className="primary-button" onClick={onOpenModal} type="button">
            <Plus size={16} aria-hidden="true" />
            New Deal
          </button>
        }
      />
      <ImportExportBar entity="deals" onImportDone={onImportDone} />
      <SavedViewsBar views={savedViews} activeName={activeSavedView} onApply={onApplySavedView} onClear={onClearSavedView} />

      <div className="flex gap-3 overflow-x-auto pb-3">
        {stages.length === 0 && <div className="panel w-full p-8 text-center text-sm text-slate-500">{loading ? 'Loading pipeline' : 'No pipeline stages configured.'}</div>}
        {stages.map((stage, index) => {
          const stageDeals = deals.filter((deal) => deal.stage_id === stage.id);
          return (
            <div key={stage.id} className={`flex min-h-[520px] min-w-64 flex-1 flex-col rounded-lg border border-slate-200 border-l-4 bg-slate-100 p-3 ${stagePalette[index % stagePalette.length]}`}>
              <div className="mb-3 flex items-center justify-between gap-2">
                <div>
                  <div className="text-xs font-bold uppercase text-slate-600">{stage.name}</div>
                  <div className="text-xs text-slate-500">{stage.probability}% probability</div>
                </div>
                <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-bold text-slate-600">{stageDeals.length}</span>
              </div>
              <div
                className={`flex flex-1 flex-col gap-2 rounded-md ${draggedDealId ? 'ring-1 ring-dashed ring-slate-300' : ''}`}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (draggedDealId) onMoveDeal(draggedDealId, stage.id);
                  setDraggedDealId(null);
                }}
              >
                {stageDeals.map((deal) => (
                  <DealCard key={deal.id} contact={deal.contact_id ? contactById.get(deal.contact_id) : undefined} deal={deal} onDragStart={setDraggedDealId} onDragEnd={() => setDraggedDealId(null)} />
                ))}
              </div>
              <button className="secondary-button mt-3 w-full justify-center border-dashed bg-white/70" onClick={onOpenModal} type="button">
                <Plus size={15} aria-hidden="true" />
                Add deal
              </button>
            </div>
          );
        })}
      </div>

      {forecastTotal !== null && (
        <div className="panel mt-2 inline-flex items-center gap-6 px-4 py-3">
          <div>
            <div className="text-xs font-bold uppercase text-slate-500">Weighted Forecast</div>
            <div className="text-xl font-bold text-blue-700">{money(forecastTotal)}</div>
            <div className="text-xs text-slate-500">open deals by stage probability</div>
          </div>
        </div>
      )}
    </>
  );
}

function DealCard({
  contact,
  deal,
  onDragEnd,
  onDragStart,
}: {
  contact?: Contact;
  deal: Deal;
  onDragEnd: () => void;
  onDragStart: (id: number) => void;
}) {
  return (
    <div
      className="cursor-grab rounded-md border border-slate-200 bg-white p-3 shadow-sm transition hover:border-blue-300 hover:shadow-md active:cursor-grabbing"
      draggable
      onDragEnd={onDragEnd}
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = 'move';
        onDragStart(deal.id);
      }}
    >
      <div className="text-sm font-semibold text-slate-950">{deal.title}</div>
      {(deal.contact_name || contact?.name) && <div className="mt-1 text-xs text-slate-500">{deal.contact_name || contact?.name}</div>}
      <div className="mt-3 flex items-center justify-between text-xs text-slate-600">
        <span>{money(deal.value)}</span>
        <span>{Math.round(Number(deal.probability || 0) * 100)}%</span>
      </div>
    </div>
  );
}

function ContactsView({
  accounts,
  activeSavedView,
  contacts,
  onApplySavedView,
  onClearSavedView,
  onImportDone,
  onOpenAccount,
  onOpenModal,
  savedViews,
}: {
  accounts: Account[];
  activeSavedView?: string;
  contacts: Contact[];
  onApplySavedView: (id: number, name: string) => void;
  onClearSavedView: () => void;
  onImportDone: () => void;
  onOpenAccount: (id: number) => void;
  onOpenModal: () => void;
  savedViews: SavedView[];
}) {
  const accountById = useMemo(() => new Map(accounts.map((account) => [account.id, account])), [accounts]);
  return (
    <>
      <SectionHeader
        title="Contacts"
        action={
          <button className="primary-button" onClick={onOpenModal} type="button">
            <Plus size={16} aria-hidden="true" />
            New Contact
          </button>
        }
      />
      <ImportExportBar entity="contacts" onImportDone={onImportDone} />
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
                  <td className="table-cell font-semibold text-slate-900">{contact.name}</td>
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

function TodayView({
  reminders,
  onDismiss,
  onImportDone,
}: {
  reminders: Reminder[];
  onDismiss: (id: number) => void;
  onImportDone: () => void;
}) {
  return (
    <>
      <SectionHeader title="Today" />
      <ImportExportBar entity="activities" onImportDone={onImportDone} />
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

function StatsView({ stats }: { stats: Stats | null }) {
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

function ModalShell({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/45 p-4" onMouseDown={onClose}>
      <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <h2 className="mb-4 text-base font-bold text-slate-950">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function DealModal({ contacts, onClose, onSubmit }: { contacts: Contact[]; onClose: () => void; onSubmit: (body: { title: string; contact_id: number; value: number }) => Promise<void> }) {
  const [title, setTitle] = useState('');
  const [contactId, setContactId] = useState('');
  const [value, setValue] = useState('');
  return (
    <ModalShell title="New Deal" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit({ title: title.trim(), contact_id: Number(contactId), value: Number(value || 0) });
        }}
      >
        <TextField label="Title" value={title} onChange={setTitle} required />
        <label className="block">
          <span className="field-label">Contact</span>
          <select className="field-input" value={contactId} onChange={(event) => setContactId(event.target.value)} required>
            <option value="">Select contact</option>
            {contacts.map((contact) => (
              <option key={contact.id} value={contact.id}>
                {contact.name}
                {contact.company ? ` (${contact.company})` : ''}
              </option>
            ))}
          </select>
        </label>
        <TextField label="Value" value={value} onChange={setValue} type="number" />
        <ModalActions onClose={onClose} submitLabel="Create" />
      </form>
    </ModalShell>
  );
}

function ContactModal({ accounts, onClose, onSubmit }: { accounts: Account[]; onClose: () => void; onSubmit: (body: Partial<Contact> & { name: string }) => Promise<void> }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [company, setCompany] = useState('');
  const [accountId, setAccountId] = useState('');
  return (
    <ModalShell title="New Contact" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          const body: Partial<Contact> & { name: string } = { name: name.trim() };
          if (email.trim()) body.email = email.trim();
          if (phone.trim()) body.phone = phone.trim();
          if (company.trim()) body.company = company.trim();
          if (accountId) body.account_id = Number(accountId);
          void onSubmit(body);
        }}
      >
        <TextField label="Name" value={name} onChange={setName} required />
        <TextField label="Email" value={email} onChange={setEmail} type="email" />
        <TextField label="Phone" value={phone} onChange={setPhone} />
        <TextField label="Company" value={company} onChange={setCompany} />
        <label className="block">
          <span className="field-label">Account</span>
          <select className="field-input" value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">None</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </select>
        </label>
        <ModalActions onClose={onClose} submitLabel="Create" />
      </form>
    </ModalShell>
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

function TextField({
  label,
  onChange,
  required,
  type = 'text',
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  required?: boolean;
  type?: string;
  value: string;
}) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <input className="field-input" value={value} onChange={(event) => onChange(event.target.value)} required={required} type={type} />
    </label>
  );
}

function ModalActions({ onClose, submitLabel }: { onClose: () => void; submitLabel: string }) {
  return (
    <div className="flex justify-end gap-2 pt-2">
      <button className="secondary-button" onClick={onClose} type="button">
        Cancel
      </button>
      <button className="primary-button" type="submit">
        {submitLabel}
      </button>
    </div>
  );
}
