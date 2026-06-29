import { useState, useCallback } from 'react';
import type { Activity } from '../types';
import { apiFetch } from '../lib/api';

export function useActivities(showToast: (msg: string) => void) {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [selectedActivity, setSelectedActivity] = useState<Activity | null>(null);
  const [activityToEdit, setActivityToEdit] = useState<Activity | null>(null);
  const [showNewActivity, setShowNewActivity] = useState(false);

  const loadActivities = useCallback(async () => {
    const res = await apiFetch('/activities');
    if (res.ok) setActivities(await res.json());
  }, []);

  async function createActivity(body: { title: string; type: string; body?: string; contact_id?: number }) {
    const res = await apiFetch('/activities', { method: 'POST', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to create activity'); return; }
    const activity = await res.json();
    setActivities((prev) => [...prev, activity]);
  }

  async function updateActivity(id: number, body: Partial<Activity>) {
    const res = await apiFetch(`/activities/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to update activity'); return; }
    const updated = await res.json();
    setActivities((prev) => prev.map((a) => (a.id === id ? updated : a)));
    if (selectedActivity?.id === id) setSelectedActivity(updated);
  }

  async function deleteActivity(id: number) {
    if (!window.confirm('Delete this activity?')) return;
    const res = await apiFetch(`/activities/${id}`, { method: 'DELETE' });
    if (!res.ok) { showToast('Failed to delete activity'); return; }
    setActivities((prev) => prev.filter((a) => a.id !== id));
    setSelectedActivity(null);
  }

  return {
    activities,
    selectedActivity, setSelectedActivity,
    activityToEdit, setActivityToEdit,
    showNewActivity, setShowNewActivity,
    loadActivities, createActivity, updateActivity, deleteActivity,
  };
}
