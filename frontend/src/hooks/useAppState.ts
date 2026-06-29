import { useState, useCallback, useEffect } from 'react';
import type { Tab, User, Contact, Deal, Account, Activity, Reminder, PipelineStage, StatsData, SavedView } from '../types';
import { apiFetch, getToken, storedUser } from '../lib/api';

export function useAppState() {
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
    if (window.location.pathname.endsWith('/login.html') && isAuthenticated) {
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
        if (!data) { showToast('Account not found'); return; }
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

  async function createDeal(body: { title: string; contact_id: number; value: number }) {
    const response = await apiFetch('/deals', { method: 'POST', body: JSON.stringify(body) });
    if (!response.ok) { showToast('Failed to create deal'); return; }
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
    if (!response.ok) { showToast('Failed to create contact'); return; }
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
    if (!response.ok) { showToast('Failed to create account'); return; }
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
    if (!response.ok) { showToast('Failed to dismiss reminder'); return; }
    setToday((prev) => prev.filter((item) => item.id !== id));
  }

  async function applySavedView(id: number, entityType: 'contacts' | 'deals', name: string) {
    const response = await apiFetch(`/saved-views/${id}/apply`, { method: 'POST' });
    if (!response.ok) { showToast('Failed to apply view'); return; }
    const results = await response.json();
    setActiveSavedView((prev) => ({ ...prev, [entityType]: name }));
    if (entityType === 'contacts') setFilteredContacts(results);
    else setFilteredDeals(results);
  }

  async function deleteAccount(id: number) {
    if (!window.confirm('Delete this account?')) return;
    const response = await apiFetch(`/accounts/${id}`, { method: 'DELETE' });
    if (!response.ok) { showToast('Failed to delete account'); return; }
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

  function handleImportSuccess(count: number) {
    showToast(`Imported ${count} contact${count !== 1 ? 's' : ''}`);
    setShowImportModal(false);
    void refreshCore();
  }

  return {
    isAuthenticated, user, handleLogin, logout, activeTab, setActiveTab,
    stages, deals, contacts, accounts, activities, today, savedViews, loading,
    filteredDeals, setFilteredDeals, filteredContacts, setFilteredContacts,
    activeSavedView, setActiveSavedView, stats, forecastTotal,
    draggedDealId, setDraggedDealId,
    selectedAccount, setSelectedAccount, selectedContact, setSelectedContact,
    selectedDeal, setSelectedDeal, selectedActivity, setSelectedActivity,
    selectedAccountId, setSelectedAccountId,
    modal, setModal, contactToEdit, setContactToEdit,
    dealToEdit, setDealToEdit, activityToEdit, setActivityToEdit,
    showNewActivity, setShowNewActivity, showImportModal, setShowImportModal,
    toast, createDeal, updateDeal, deleteDeal, moveDeal,
    createContact, updateContact, deleteContact, createAccount, deleteAccount,
    createActivity, updateActivity, deleteActivity,
    dismissReminder, applySavedView, exportContacts, handleImportSuccess,
  };
}
