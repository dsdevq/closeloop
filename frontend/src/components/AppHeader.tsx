import { BarChart3, Bell, Building2, Calendar, ContactRound, LogOut, RefreshCw, TrendingUp, UserRound, Zap } from 'lucide-react';
import type { Tab, User } from '../types';
import { NotificationCenter } from '../features/notifications/NotificationCenter';

export function AppHeader({ activeTab, onTabChange, user, onLogout, isAuthenticated }: {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  user: User;
  onLogout: () => void;
  isAuthenticated: boolean;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-800 bg-slate-950 text-white shadow-lg">
      <div className="flex min-h-14 flex-wrap items-center gap-3 px-4 lg:flex-nowrap lg:px-6">
        <div className="flex items-center gap-2 pr-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600">
            <RefreshCw size={17} aria-hidden="true" />
          </div>
          <div className="whitespace-nowrap text-sm font-bold tracking-wide">CloseLoop CRM</div>
        </div>

        <nav className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
          {([
            ['pipeline', BarChart3, 'Pipeline'],
            ['contacts', ContactRound, 'Contacts'],
            ['accounts', Building2, 'Accounts'],
            ['activities', Calendar, 'Activities'],
            ['today', Bell, 'Today'],
            ['stats', BarChart3, 'Stats'],
            ['insights', TrendingUp, 'Insights'],
          ] as const).map(([tab, Icon, label]) => (
            <button
              key={tab}
              className={`inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm transition ${
                activeTab === tab
                  ? 'bg-white text-slate-950'
                  : 'text-slate-300 hover:bg-white/10 hover:text-white'
              }`}
              onClick={() => onTabChange(tab)}
              type="button"
            >
              <Icon size={16} aria-hidden="true" />
              {label}
            </button>
          ))}
          {(user.role === 'admin' || user.role === 'manager') && (
            <button
              className={`inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm transition ${
                activeTab === 'automations'
                  ? 'bg-white text-slate-950'
                  : 'text-slate-300 hover:bg-white/10 hover:text-white'
              }`}
              onClick={() => onTabChange('automations')}
              type="button"
            >
              <Zap size={16} aria-hidden="true" />
              Automations
            </button>
          )}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-md bg-white/10 px-2.5 py-1.5 text-xs text-slate-200 sm:flex">
            <UserRound size={14} aria-hidden="true" />
            <span className="max-w-48 truncate">{user.full_name || user.email}</span>
            <span className="rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-bold uppercase">
              {user.role || 'user'}
            </span>
          </div>
          <NotificationCenter isAuthenticated={isAuthenticated} />
          <button
            className="icon-button border-white/25 bg-transparent text-slate-200 hover:text-white"
            onClick={onLogout}
            title="Sign out"
            type="button"
          >
            <LogOut size={17} aria-hidden="true" />
          </button>
        </div>
      </div>
    </header>
  );
}
