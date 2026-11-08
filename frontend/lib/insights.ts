export type InsightStatus = 'draft' | 'verified' | 'outdated' | 'rejected';
export type Evidence = Array<Record<string, unknown>>;
export interface InsightSummary {
  id: number; title: string; status: InsightStatus; revision: number; work_revision: number;
  owner_id: number | null; reviewer_id: number | null; priority: number; due_at: string | null;
  created_by_id: number; version_state: string; needs_review: boolean; evidence_count: number;
}
export interface InsightDetail extends InsightSummary {
  content: string; evidence: Evidence; current_versions: Evidence; version_bindings: Evidence | null;
  review_history: Array<Record<string, unknown>>; workflow_history: Array<Record<string, unknown>>;
  history_truncated?: boolean; outdated_source_ids: number[];
}
export interface InsightPage {
  items: InsightSummary[]; total: number; offset: number; limit: number; has_more: boolean;
  counts: Partial<Record<InsightStatus, number>>;
}
export interface InsightAssignees {
  items: Array<{ id: number; name: string; can_review: boolean }>; can_manage: boolean; truncated: boolean;
}
export interface InsightInboxData {
  unread_count: number; has_more: boolean;
  items: Array<{ id: number; insight_id: number; title: string; kind: string; created_at: string }>;
}
export interface InsightAssignment {
  expected_revision: number; expected_work_revision: number; owner_id: number | null;
  reviewer_id: number | null; priority: number; due_at: string | null;
}
