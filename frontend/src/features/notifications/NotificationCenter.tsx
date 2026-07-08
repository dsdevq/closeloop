/**
 * HubSpot-style notification centre: bell icon with unread badge, dropdown panel.
 *
 * Design rationale (notifications-engine.md §2–3):
 *   Borrowed: pull-model polling (HubSpot/Pipedrive), unread count badge (Pipedrive),
 *             flat list newest-first (all five), read_at timestamp (HubSpot/Attio),
 *             kind-based icon dispatch (Pipedrive closed enum).
 *   Rejected: Chatter/feed full-page view (over-engineered for CloseLoop's scope),
 *             pre-rendered message strings (stale on entity rename),
 *             day-grouping in panel (Zoho — frontend concern, backend returns flat).
 */
import { useEffect, useRef } from 'react';
import {
  ArrowRight,
  AtSign,
  Bell,
  CheckCheck,
  Clock,
  UserCheck,
} from 'lucide-react';
import type { Notification, NotificationKind } from '../../types';
import { useNotifications } from '../../hooks/useNotifications';

// ── Kind → icon mapping (Pipedrive closed-enum pattern) ───────────────────────

function KindIcon({ kind }: { kind: NotificationKind }) {
  const cls = 'shrink-0';
  switch (kind) {
    case 'deal_assigned':
      return <UserCheck size={15} className={cls} aria-hidden="true" />;
    case 'stage_changed':
      return <ArrowRight size={15} className={cls} aria-hidden="true" />;
    case 'task_overdue':
      return <Clock size={15} className={cls} aria-hidden="true" />;
    case 'mention':
      return <AtSign size={15} className={cls} aria-hidden="true" />;
  }
}

// ── Single notification row ────────────────────────────────────────────────────

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: Notification;
  onMarkRead: (id: number) => void;
}) {
  const isUnread = notification.read_at === null;

  function handleClick() {
    if (isUnread) onMarkRead(notification.id);
  }

  const timeLabel = new Date(notification.created_at).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <button
      className={`flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left transition hover:bg-slate-50 ${
        isUnread ? 'bg-blue-50/60' : ''
      }`}
      onClick={handleClick}
      type="button"
      aria-label={isUnread ? `Mark as read: ${notification.message}` : notification.message}
    >
      <span
        className={`mt-0.5 ${isUnread ? 'text-blue-600' : 'text-slate-400'}`}
        aria-hidden="true"
      >
        <KindIcon kind={notification.kind} />
      </span>
      <span className="min-w-0 flex-1">
        <span
          className={`block text-xs leading-snug ${
            isUnread ? 'font-semibold text-slate-900' : 'text-slate-600'
          }`}
        >
          {notification.message || '—'}
        </span>
        <span className="mt-0.5 block text-[10px] text-slate-400">{timeLabel}</span>
      </span>
      {isUnread && (
        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-blue-500" aria-hidden="true" />
      )}
    </button>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function NotificationCenter({ isAuthenticated }: { isAuthenticated: boolean }) {
  const {
    unreadCount,
    notifications,
    isOpen,
    loading,
    togglePanel,
    closePanel,
    markRead,
    markAllRead,
  } = useNotifications(isAuthenticated);

  const containerRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    if (!isOpen) return;
    function handleOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        closePanel();
      }
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [isOpen, closePanel]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') closePanel();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, closePanel]);

  const hasUnread = unreadCount > 0;

  return (
    <div ref={containerRef} className="relative">
      {/* Bell button */}
      <button
        type="button"
        aria-label={hasUnread ? `Notifications — ${unreadCount} unread` : 'Notifications'}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        className="icon-button relative border-white/25 bg-transparent text-slate-200 hover:text-white"
        onClick={togglePanel}
        data-testid="notification-bell"
      >
        <Bell size={17} aria-hidden="true" />
        {hasUnread && (
          <span
            className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-0.5 text-[9px] font-bold leading-none text-white"
            aria-hidden="true"
            data-testid="notification-badge"
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown panel */}
      {isOpen && (
        <div
          role="dialog"
          aria-label="Notifications"
          data-testid="notification-panel"
          className="absolute right-0 top-10 z-50 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl"
        >
          {/* Panel header */}
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-xs font-bold text-slate-700">Notifications</span>
            {hasUnread && (
              <button
                type="button"
                className="flex items-center gap-1 text-[11px] font-semibold text-blue-600 hover:text-blue-800"
                onClick={() => void markAllRead()}
                data-testid="mark-all-read-btn"
              >
                <CheckCheck size={13} aria-hidden="true" />
                Mark all read
              </button>
            )}
          </div>

          {/* Body */}
          <div className="max-h-96 overflow-y-auto">
            {loading && (
              <div className="flex items-center justify-center py-10 text-xs text-slate-400">
                Loading…
              </div>
            )}
            {!loading && notifications.length === 0 && (
              <div
                className="flex flex-col items-center justify-center gap-2 py-10"
                data-testid="notification-empty"
              >
                <Bell size={24} className="text-slate-300" aria-hidden="true" />
                <span className="text-xs text-slate-400">You are all caught up</span>
              </div>
            )}
            {!loading &&
              notifications.map((n) => (
                <NotificationRow
                  key={n.id}
                  notification={n}
                  onMarkRead={(id) => void markRead(id)}
                />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
