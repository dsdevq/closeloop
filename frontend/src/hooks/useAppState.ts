import { useState, useCallback, useEffect } from 'react';
import type { Tab, PipelineStage, Reminder, StatsData, SavedView } from '../types';
import { apiFetch } from '../lib/api';
import { useAuth } from './useAuth';
import { useDeals } from './useDeals';
import { useContacts } from './useContacts';
import { useAccounts } from './useAccounts';
import { useActivities } from './useActivities';

export function useAppState() {
  const [toast, setToast] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('pipeline');
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [today, setToday] = useState<Reminder[]>([]);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [activeSavedView, setActiveSavedView] = useState<{ contacts?: string; deals?: string }>({});
  const [stats, setStats] = useState<StatsData | null>(null);
  const [forecastTotal, setForecastTotal] = useState<number | null>(null);
  const [modal, setModal] = useState<'deal' | 'contact' | 'account' | null>(null);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(''), 3200);
  }, []);

  const auth = useAuth();
  const dealsState = useDeals(showToast);
  const contactsState = useContacts(showToast);
  const accountsState = useAccounts(showToast);
  const activitiesState = useActivities(showToast);

  const { loadDeals } = dealsState;
  const { loadContacts, setFilteredContacts, setShowImportModal } = contactsState;
  const { loadAccounts } = accountsState;
  const { loadActivities } = activitiesState;
  const { setFilteredDeals } = dealsState;

  const refreshCore = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadDeals(),
        loadContacts(),
        loadAccounts(),
        loadActivities(),
        apiFetch('/pipeline/stages').then(async (r) => { if (r.ok) setStages(await r.json()); }),
        apiFetch('/reminders/today').then(async (r) => { if (r.ok) setToday(await r.json()); }),
        apiFetch('/saved-views').then(async (r) => { if (r.ok) setSavedViews(await r.json()); }),
        apiFetch('/forecast').then(async (r) => {
          if (r.ok) {
            const data = await r.json();
            setForecastTotal(Number(data.total || 0));
          }
        }),
      ]);
    } catch {
      showToast('Could not load CloseLoop data');
    } finally {
      setLoading(false);
    }
  }, [showToast, loadDeals, loadContacts, loadAccounts, loadActivities]);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    void refreshCore();
  }, [auth.isAuthenticated, refreshCore]);

  useEffect(() => {
    if (activeTab !== 'stats' || !auth.isAuthenticated) return;
    apiFetch('/stats')
      .then((res) => (res.ok ? res.json() : null))
      .then((data: StatsData | null) => data && setStats(data))
      .catch(() => showToast('Failed to load stats'));
  }, [activeTab, auth.isAuthenticated, showToast]);

  async function dismissReminder(id: number) {
    const res = await apiFetch(`/reminders/${id}/dismiss`, { method: 'PATCH' });
    if (!res.ok) { showToast('Failed to dismiss reminder'); return; }
    setToday((prev) => prev.filter((item) => item.id !== id));
  }

  async function applySavedView(id: number, entityType: 'contacts' | 'deals', name: string) {
    const res = await apiFetch(`/saved-views/${id}/apply`, { method: 'POST' });
    if (!res.ok) { showToast('Failed to apply view'); return; }
    const results = await res.json();
    setActiveSavedView((prev) => ({ ...prev, [entityType]: name }));
    if (entityType === 'contacts') setFilteredContacts(results);
    else setFilteredDeals(results);
  }

  function handleImportSuccess(count: number) {
    showToast(`Imported ${count} contact${count !== 1 ? 's' : ''}`);
    setShowImportModal(false);
    void refreshCore();
  }

  return {
    ...auth,
    ...dealsState,
    ...contactsState,
    ...accountsState,
    ...activitiesState,
    toast, loading, activeTab, setActiveTab,
    stages, today, savedViews, activeSavedView, setActiveSavedView,
    stats, forecastTotal, modal, setModal,
    dismissReminder, applySavedView, handleImportSuccess,
  };
}
