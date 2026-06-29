import { useState, useCallback } from 'react';
import type { Deal } from '../types';
import { apiFetch } from '../lib/api';

export function useDeals(showToast: (msg: string) => void) {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [filteredDeals, setFilteredDeals] = useState<Deal[] | null>(null);
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [dealToEdit, setDealToEdit] = useState<Deal | null>(null);
  const [draggedDealId, setDraggedDealId] = useState<number | null>(null);

  const loadDeals = useCallback(async () => {
    const res = await apiFetch('/deals');
    if (res.ok) setDeals(await res.json());
  }, []);

  async function createDeal(body: { title: string; contact_id: number; value: number }) {
    const res = await apiFetch('/deals', { method: 'POST', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to create deal'); return; }
    const deal = await res.json();
    setDeals((prev) => [...prev, deal]);
  }

  async function updateDeal(id: number, body: Partial<Deal>) {
    const res = await apiFetch(`/deals/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to update deal'); return; }
    const updated = await res.json();
    setDeals((prev) => prev.map((d) => (d.id === id ? updated : d)));
    if (selectedDeal?.id === id) setSelectedDeal(updated);
  }

  async function deleteDeal(id: number) {
    if (!window.confirm('Delete this deal?')) return;
    const res = await apiFetch(`/deals/${id}`, { method: 'DELETE' });
    if (!res.ok) { showToast('Failed to delete deal'); return; }
    setDeals((prev) => prev.filter((d) => d.id !== id));
    setSelectedDeal(null);
  }

  async function moveDeal(dealId: number, stageId: number) {
    const res = await apiFetch(`/deals/${dealId}`, {
      method: 'PATCH',
      body: JSON.stringify({ stage_id: stageId }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showToast(data.detail || 'Could not move deal');
      return;
    }
    const updated = await res.json();
    setDeals((prev) => prev.map((deal) => (deal.id === updated.id ? updated : deal)));
    if (filteredDeals) {
      setFilteredDeals((prev) => prev?.map((deal) => (deal.id === updated.id ? updated : deal)) ?? null);
    }
  }

  return {
    deals, filteredDeals, setFilteredDeals,
    selectedDeal, setSelectedDeal,
    dealToEdit, setDealToEdit,
    draggedDealId, setDraggedDealId,
    loadDeals, createDeal, updateDeal, deleteDeal, moveDeal,
  };
}
