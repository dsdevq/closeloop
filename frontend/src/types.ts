export type Tab = 'pipeline' | 'contacts' | 'accounts' | 'today' | 'stats' | 'activities';

export type User = {
  id?: number;
  email?: string;
  full_name?: string;
  role?: string;
};

export type PipelineStage = {
  id: number;
  name: string;
  position: number;
  probability: number;
};

export type Deal = {
  id: number;
  title: string;
  value?: number | null;
  probability?: number | null;
  stage_id?: number | null;
  stage?: string | null;
  contact_id?: number | null;
  contact_name?: string | null;
};

export type Contact = {
  id: number;
  name: string;
  email?: string | null;
  phone?: string | null;
  company?: string | null;
  lead_score?: number | null;
  account_id?: number | null;
};

export type Account = {
  id: number;
  name: string;
  domain?: string | null;
  industry?: string | null;
  website?: string | null;
  phone?: string | null;
  address?: string | null;
  owner_id?: number | null;
  contact_count?: number | null;
  contacts?: Contact[];
};

export type Activity = {
  id: number;
  title: string;
  type: string;
  body?: string | null;
  contact_id?: number | null;
  deal_id?: number | null;
  due_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type Reminder = {
  id: number;
  activity_title?: string | null;
  activity_type?: string | null;
  deal_title?: string | null;
  contact_name?: string | null;
  remind_at?: string | null;
};

export type SavedView = {
  id: number;
  name: string;
  entity_type: 'contacts' | 'deals';
};

export type StatsData = {
  total_contacts: number;
  total_deals: number;
  total_activities: number;
  pipeline_value: number;
  weighted_forecast: number;
  activities_last_30_days: number;
  outbox_queued: number;
  deals_by_stage?: Record<string, number>;
};
