import { useState, useEffect, useCallback, useRef } from 'react';
import type { Notification } from '../types';
import { apiFetch } from '../lib/api';

const POLL_INTERVAL_MS = 30_000;

export function useNotifications(isAuthenticated: boolean) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchUnreadCount = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await apiFetch('/notifications/unread-count');
      if (res.ok) {
        const data = await res.json() as { unread_count: number };
        setUnreadCount(data.unread_count);
      }
    } catch {
      // network error — keep current count
    }
  }, [isAuthenticated]);

  const fetchNotifications = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    try {
      const res = await apiFetch('/notifications?limit=50');
      if (res.ok) {
        const data = await res.json() as Notification[];
        setNotifications(data);
        const unread = data.filter((n) => n.read_at === null).length;
        setUnreadCount(unread);
      }
    } catch {
      // network error — keep existing list
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  // Poll unread count on a 30 s interval while authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      setUnreadCount(0);
      setNotifications([]);
      return;
    }

    void fetchUnreadCount();
    intervalRef.current = setInterval(() => {
      void fetchUnreadCount();
    }, POLL_INTERVAL_MS);

    return () => {
      if (intervalRef.current !== null) clearInterval(intervalRef.current);
    };
  }, [isAuthenticated, fetchUnreadCount]);

  // Load the full list whenever the panel is opened
  useEffect(() => {
    if (isOpen) void fetchNotifications();
  }, [isOpen, fetchNotifications]);

  const openPanel = useCallback(() => setIsOpen(true), []);
  const closePanel = useCallback(() => setIsOpen(false), []);
  const togglePanel = useCallback(() => setIsOpen((prev) => !prev), []);

  const markRead = useCallback(async (id: number) => {
    const res = await apiFetch(`/notifications/${id}/read`, { method: 'POST' });
    if (!res.ok) return;
    const updated = await res.json() as Notification;
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? updated : n))
    );
    setUnreadCount((prev) => Math.max(0, prev - 1));
  }, []);

  const markAllRead = useCallback(async () => {
    const res = await apiFetch('/notifications/read-all', { method: 'POST' });
    if (!res.ok) return;
    const now = new Date().toISOString();
    setNotifications((prev) =>
      prev.map((n) => (n.read_at === null ? { ...n, read_at: now } : n))
    );
    setUnreadCount(0);
  }, []);

  return {
    unreadCount,
    notifications,
    isOpen,
    loading,
    openPanel,
    closePanel,
    togglePanel,
    markRead,
    markAllRead,
  };
}
