import { useState, useCallback, useEffect } from 'react';
import type { Account } from '../types';
import { apiFetch } from '../lib/api';

export function useAccounts(showToast: (msg: string) => void) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);

  useEffect(() => {
    if (!selectedAccountId) return;
    apiFetch(`/accounts/${selectedAccountId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: Account | null) => {
        if (!data) { showToast('Account not found'); return; }
        setSelectedAccount(data);
      })
      .catch(() => showToast('Could not load account'));
  }, [selectedAccountId, showToast]);

  const loadAccounts = useCallback(async () => {
    const res = await apiFetch('/accounts');
    if (res.ok) setAccounts(await res.json());
  }, []);

  async function createAccount(body: Partial<Account> & { name: string }) {
    const res = await apiFetch('/accounts', { method: 'POST', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to create account'); return; }
    const account = await res.json();
    setAccounts((prev) => [...prev, account]);
  }

  async function updateAccount(id: number, body: Partial<Account>) {
    const res = await apiFetch(`/accounts/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to update account'); return; }
    const updated = await res.json();
    setAccounts((prev) => prev.map((a) => (a.id === id ? updated : a)));
    if (selectedAccount?.id === id) setSelectedAccount(updated);
  }

  async function deleteAccount(id: number) {
    if (!window.confirm('Delete this account?')) return;
    const res = await apiFetch(`/accounts/${id}`, { method: 'DELETE' });
    if (!res.ok) { showToast('Failed to delete account'); return; }
    setAccounts((prev) => prev.filter((a) => a.id !== id));
    setSelectedAccountId(null);
    setSelectedAccount(null);
  }

  return {
    accounts,
    selectedAccountId, setSelectedAccountId,
    selectedAccount, setSelectedAccount,
    loadAccounts, createAccount, updateAccount, deleteAccount,
  };
}
