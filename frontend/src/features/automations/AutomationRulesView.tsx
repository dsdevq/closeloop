/**
 * Automation rules admin panel.
 *
 * Form-based list + create UI for AutomationRule records. Admin/manager only
 * (enforced server-side; this tab is hidden from reps in AppHeader).
 *
 * Design: trigger → conditions → action form, matching the declarative JSON
 * rule model documented in .devclaw/research/workflow-automation.md §6.
 * Not a visual canvas — simple HTML forms that produce JSON rule definitions.
 */
import { useState, useEffect, useCallback } from 'react';
import { Plus, Trash2, ToggleLeft, ToggleRight, ChevronUp } from 'lucide-react';
import type { AutomationRule } from '../../types';
import { apiFetch } from '../../lib/api';
import { SectionHeader } from '../../components/ui/SectionHeader';

const TRIGGER_EVENTS = [
  'deal_created',
  'deal_stage_changed',
  'deal_assigned',
  'deal_updated',
  'contact_created',
  'contact_updated',
  'activity_created',
  'activity_completed',
] as const;

const DEFAULT_FORM = {
  name: '',
  trigger_type: 'after_save' as 'after_save' | 'scheduled',
  trigger_event: 'deal_stage_changed',
  conditions_json: '',
  action_type: 'notify',
  action_config_json: '{"recipient_id": }',
  schedule_config_json: '',
  is_active: true,
};

type FormState = typeof DEFAULT_FORM;

function RuleBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
        active ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
      }`}
    >
      {active ? 'Active' : 'Inactive'}
    </span>
  );
}

function RuleRow({
  rule,
  onToggle,
  onDelete,
}: {
  rule: AutomationRule;
  onToggle: (id: number, active: boolean) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <tr className="border-b border-slate-100 text-sm last:border-0">
      <td className="py-3 pr-4 font-medium text-slate-900">{rule.name}</td>
      <td className="py-3 pr-4 text-slate-600">
        <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">{rule.trigger_type}</code>
      </td>
      <td className="py-3 pr-4 text-slate-600">
        {rule.trigger_event ? (
          <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">{rule.trigger_event}</code>
        ) : (
          <span className="text-slate-400">—</span>
        )}
      </td>
      <td className="py-3 pr-4 text-slate-600">
        <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">{rule.action_type}</code>
      </td>
      <td className="py-3 pr-4">
        <RuleBadge active={rule.is_active} />
      </td>
      <td className="py-3 text-right">
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            title={rule.is_active ? 'Deactivate rule' : 'Activate rule'}
            className="text-slate-400 hover:text-slate-700"
            onClick={() => onToggle(rule.id, !rule.is_active)}
          >
            {rule.is_active ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
          </button>
          <button
            type="button"
            title="Delete rule"
            className="text-slate-400 hover:text-red-600"
            onClick={() => onDelete(rule.id)}
          >
            <Trash2 size={15} />
          </button>
        </div>
      </td>
    </tr>
  );
}

function CreateRuleForm({
  onCreated,
  onCancel,
}: {
  onCreated: (rule: AutomationRule) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<FormState>({ ...DEFAULT_FORM });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        name: form.name.trim(),
        trigger_type: form.trigger_type,
        action_type: form.action_type,
        action_config_json: form.action_config_json.trim() || '{}',
        is_active: form.is_active,
      };
      if (form.trigger_type === 'after_save') {
        payload.trigger_event = form.trigger_event;
      }
      if (form.conditions_json.trim()) {
        payload.conditions_json = form.conditions_json.trim();
      }
      if (form.trigger_type === 'scheduled' && form.schedule_config_json.trim()) {
        payload.schedule_config_json = form.schedule_config_json.trim();
      }

      const resp = await apiFetch('/automation-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        setError(body.detail ?? `Error ${resp.status}`);
        return;
      }
      const created: AutomationRule = await resp.json();
      onCreated(created);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={(e) => void handleSubmit(e)}
      className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
    >
      <h2 className="mb-3 text-sm font-semibold text-slate-800">New automation rule</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="label-text block text-xs font-medium text-slate-600">
            Rule name *
          </label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="e.g. Notify owner on stage change"
            required
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600">Trigger type *</label>
          <select
            className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={form.trigger_type}
            onChange={(e) => set('trigger_type', e.target.value as 'after_save' | 'scheduled')}
          >
            <option value="after_save">After save (event-based)</option>
            <option value="scheduled">Scheduled (time-based)</option>
          </select>
        </div>

        {form.trigger_type === 'after_save' && (
          <div>
            <label className="block text-xs font-medium text-slate-600">Trigger event *</label>
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.trigger_event}
              onChange={(e) => set('trigger_event', e.target.value)}
            >
              {TRIGGER_EVENTS.map((ev) => (
                <option key={ev} value={ev}>
                  {ev}
                </option>
              ))}
            </select>
          </div>
        )}

        {form.trigger_type === 'scheduled' && (
          <div>
            <label className="block text-xs font-medium text-slate-600">
              Schedule config * <span className="font-normal text-slate-400">(JSON)</span>
            </label>
            <input
              className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.schedule_config_json}
              onChange={(e) => set('schedule_config_json', e.target.value)}
              placeholder='{"interval_minutes": 60}'
            />
          </div>
        )}

        <div className="sm:col-span-2">
          <label className="block text-xs font-medium text-slate-600">
            Conditions <span className="font-normal text-slate-400">(optional JSON array)</span>
          </label>
          <textarea
            className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={2}
            value={form.conditions_json}
            onChange={(e) => set('conditions_json', e.target.value)}
            placeholder='[{"field":"stage","op":"eq","value":"won"}]'
          />
          <p className="mt-0.5 text-[11px] text-slate-400">
            Supported ops: <code>eq</code>, <code>neq</code>, <code>in</code>. Leave blank to fire
            unconditionally.
          </p>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600">Action type *</label>
          <select
            className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={form.action_type}
            onChange={(e) => set('action_type', e.target.value)}
          >
            <option value="notify">notify (in-app notification)</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600">
            Action config * <span className="font-normal text-slate-400">(JSON)</span>
          </label>
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={form.action_config_json}
            onChange={(e) => set('action_config_json', e.target.value)}
            placeholder='{"recipient_id": 1}'
          />
          <p className="mt-0.5 text-[11px] text-slate-400">
            Use <code>recipient_id</code> (user ID) or{' '}
            <code>recipient_field</code> (context key, e.g. <code>"owner_id"</code>).
          </p>
        </div>

        <div className="sm:col-span-2 flex items-center gap-2">
          <input
            type="checkbox"
            id="is_active"
            checked={form.is_active}
            onChange={(e) => set('is_active', e.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          <label htmlFor="is_active" className="text-sm text-slate-700">
            Active (rule will fire when conditions match)
          </label>
        </div>
      </div>

      {error && (
        <p className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      <div className="mt-4 flex gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Create rule'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-slate-300 px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export function AutomationRulesView() {
  const [rules, setRules] = useState<AutomationRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const loadRules = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch('/automation-rules');
      if (!resp.ok) {
        setError(`Failed to load rules (${resp.status})`);
        return;
      }
      setRules(await resp.json());
    } catch {
      setError('Network error loading automation rules');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  async function handleToggle(id: number, active: boolean) {
    const resp = await apiFetch(`/automation-rules/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: active }),
    });
    if (resp.ok) {
      const updated: AutomationRule = await resp.json();
      setRules((prev) => prev.map((r) => (r.id === id ? updated : r)));
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm('Delete this automation rule?')) return;
    const resp = await apiFetch(`/automation-rules/${id}`, { method: 'DELETE' });
    if (resp.ok || resp.status === 204) {
      setRules((prev) => prev.filter((r) => r.id !== id));
    }
  }

  function handleCreated(rule: AutomationRule) {
    setRules((prev) => [rule, ...prev]);
    setShowCreate(false);
  }

  return (
    <>
      <SectionHeader
        title="Automation Rules"
        action={
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-700"
            onClick={() => setShowCreate((v) => !v)}
          >
            {showCreate ? <ChevronUp size={15} /> : <Plus size={15} />}
            {showCreate ? 'Cancel' : 'New rule'}
          </button>
        }
      />

      {showCreate && (
        <CreateRuleForm
          onCreated={handleCreated}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {loading && (
        <p className="mt-6 text-sm text-slate-500">Loading rules…</p>
      )}

      {error && (
        <p className="mt-4 rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      )}

      {!loading && !error && rules.length === 0 && (
        <div className="mt-8 text-center text-sm text-slate-500">
          No automation rules yet.{' '}
          <button
            type="button"
            className="text-blue-600 underline"
            onClick={() => setShowCreate(true)}
          >
            Create your first rule.
          </button>
        </div>
      )}

      {!loading && rules.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
                <th className="py-2.5 pr-4 pl-4">Name</th>
                <th className="py-2.5 pr-4">Type</th>
                <th className="py-2.5 pr-4">Trigger event</th>
                <th className="py-2.5 pr-4">Action</th>
                <th className="py-2.5 pr-4">Status</th>
                <th className="py-2.5 pr-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rules.map((rule) => (
                <RuleRow
                  key={rule.id}
                  rule={rule}
                  onToggle={(id, active) => void handleToggle(id, active)}
                  onDelete={(id) => void handleDelete(id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs text-slate-400">
        After-save rules fire inline when domain mutations occur. Scheduled rules poll every 60 s.
        Inactive rules are skipped at the query level.
      </p>
    </>
  );
}
