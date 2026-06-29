import { useState, useCallback } from 'react';
import type { Contact } from '../types';
import { apiFetch } from '../lib/api';

export function useContacts(showToast: (msg: string) => void) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [filteredContacts, setFilteredContacts] = useState<Contact[] | null>(null);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);
  const [contactToEdit, setContactToEdit] = useState<Contact | null>(null);
  const [showImportModal, setShowImportModal] = useState(false);

  const loadContacts = useCallback(async () => {
    const res = await apiFetch('/contacts');
    if (res.ok) setContacts(await res.json());
  }, []);

  async function createContact(body: Partial<Contact> & { name: string }) {
    const res = await apiFetch('/contacts', { method: 'POST', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to create contact'); return; }
    const contact = await res.json();
    setContacts((prev) => [...prev, contact]);
  }

  async function updateContact(id: number, body: Partial<Contact>) {
    const res = await apiFetch(`/contacts/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    if (!res.ok) { showToast('Failed to update contact'); return; }
    const updated = await res.json();
    setContacts((prev) => prev.map((c) => (c.id === id ? updated : c)));
    if (selectedContact?.id === id) setSelectedContact(updated);
  }

  async function deleteContact(id: number) {
    if (!window.confirm('Delete this contact?')) return;
    const res = await apiFetch(`/contacts/${id}`, { method: 'DELETE' });
    if (!res.ok) { showToast('Failed to delete contact'); return; }
    setContacts((prev) => prev.filter((c) => c.id !== id));
    setSelectedContact(null);
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

  return {
    contacts, filteredContacts, setFilteredContacts,
    selectedContact, setSelectedContact,
    contactToEdit, setContactToEdit,
    showImportModal, setShowImportModal,
    loadContacts, createContact, updateContact, deleteContact, exportContacts,
  };
}
