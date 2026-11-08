"use client";

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import type { User } from '@/types/domain';
import type { Evidence, InsightAssignees, InsightDetail, InsightAssignment } from '@/lib/insights';
import { InsightEvidence } from './InsightEvidence';
import { InsightEvidenceEditor } from './InsightEvidenceEditor';
import { InsightAssignmentForm } from './InsightAssignmentForm';

export function InsightDetailPanel({ projectId, insightId, currentUser, onChanged, onLoaded, onOpenFile }: {
  projectId: number; insightId: number; currentUser: Partial<User> | null; onChanged: () => void;
  onLoaded?: (value: InsightDetail) => void;
  onOpenFile?: (path: string, line: number | null, sourceId: number | null) => void;
}) {
  const { t } = useLanguage();
  const [data, setData] = useState<InsightDetail | null>(null);
  const [assignees, setAssignees] = useState<InsightAssignees | null>(null);
  const [editing, setEditing] = useState<{ title: string; content: string; evidence: Evidence } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const load = useCallback(async () => {
    const request = ++generation.current;
    try {
      const [detail, people] = await Promise.all([api.getInsight(projectId, insightId), api.getInsightAssignees(projectId)]);
      if (generation.current !== request) return;
      setData(detail.data); setAssignees(people.data); setError(''); onLoaded?.(detail.data);
    } catch { if (generation.current === request) setError(t('insightWork.failed')); }
  }, [projectId, insightId, t, onLoaded]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => { window.clearTimeout(timer); generation.current += 1; };
  }, [load]);
  const act = async (operation: () => Promise<unknown>) => {
    const request = generation.current;
    setBusy(true); setError('');
    try { await operation(); if (generation.current === request) { setEditing(null); await load(); onChanged(); } }
    catch (exc) {
      if (generation.current !== request) return;
      const error = exc as { response?: { data?: { detail?: unknown } } };
      setError(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : t('insightWork.failed'));
    } finally { if (generation.current === request || generation.current === request + 1) setBusy(false); }
  };
  if (!data || !assignees) return <section className="rounded border border-ds-zinc-500/30 p-4 text-sm">{error || t('insightWork.loading')}</section>;
  const canEdit = assignees.can_manage || data.owner_id === currentUser?.id || (data.owner_id == null && data.created_by_id === currentUser?.id);
  const canApprove = assignees.can_manage && data.status !== 'rejected' && data.version_state !== 'index_unavailable' && (data.status !== 'verified' || !['current','project'].includes(data.version_state)) && (currentUser?.is_admin || data.created_by_id !== currentUser?.id);
  return <section aria-label={t('insightWork.detail')} className="space-y-3 rounded-lg border border-ds-indigo-500/40 p-4 text-sm">
    <h3 className="break-words font-semibold">{data.title}</h3>
    <p className="whitespace-pre-wrap break-words">{data.content}</p>
    <p className="text-xs">{t('insightWork.owner')}: {assignees.items.find(person => person.id === data.owner_id)?.name || (data.owner_id == null ? t('insightWork.unassigned') : `#${data.owner_id}`)} · {t('insightWork.reviewer')}: {assignees.items.find(person => person.id === data.reviewer_id)?.name || (data.reviewer_id == null ? t('insightWork.unassigned') : `#${data.reviewer_id}`)} · {t(`insightWork.priority.${data.priority}`)}</p>
    <p>{t(`insightReview.status.${data.status}`)} · {t(`insightCommit.versionState.${data.version_state}`)}</p>
    <InsightEvidence evidence={data.evidence} onOpenFile={onOpenFile} />
    <details className="text-xs"><summary>{t('insightCommit.bindings')}</summary><InsightEvidence evidence={data.current_versions || []} /></details>
    <div className="flex flex-wrap gap-3 text-xs">
      {canApprove && <button disabled={busy} onClick={() => void act(() => api.verifyInsight(projectId, data.id, data.revision, data.current_versions))} className="rounded bg-ds-emerald-600 px-3 py-2 text-ds-white disabled:opacity-50">{t('insightReview.verify')}</button>}
      {canEdit && <button disabled={busy} onClick={() => setEditing({ title: data.title, content: data.content, evidence: data.evidence.map(item => ({ ...item })) })} className="text-ds-indigo-400">{t('insightReview.revise')}</button>}
      {assignees.can_manage && <button disabled={busy} onClick={() => { if (window.confirm(t('insightReview.rejectConfirm'))) void act(() => api.reviewInsight(projectId, data.id, { action: 'reject', expected_revision: data.revision })); }} className="text-ds-red-500">{t('insightReview.reject')}</button>}
    </div>
    {editing && <form className="space-y-3" onSubmit={event => { event.preventDefault(); if (editing.title.trim() && editing.content.trim() && editing.evidence.length) void act(() => api.reviewInsight(projectId, data.id, { action: 'revise', expected_revision: data.revision, ...editing })); }}>
      <label className="block text-xs">{t('insightDraft.title')}<input value={editing.title} maxLength={240} onChange={e => setEditing({ ...editing, title: e.target.value })} className="mt-1 block w-full rounded border border-ds-zinc-500 bg-transparent p-2" /></label>
      <label className="block text-xs">{t('insightDraft.content')}<textarea value={editing.content} maxLength={32000} rows={5} onChange={e => setEditing({ ...editing, content: e.target.value })} className="mt-1 block w-full rounded border border-ds-zinc-500 bg-transparent p-2" /></label>
      <InsightEvidenceEditor projectId={projectId} value={editing.evidence} onChange={evidence => setEditing({ ...editing, evidence })} />
      <button disabled={busy || !editing.evidence.length} className="mr-3 rounded bg-ds-indigo-600 px-3 py-2 text-xs text-ds-white disabled:opacity-50">{t('insightDraft.saveDraft')}</button>
      <button type="button" onClick={() => setEditing(null)} className="text-xs">{t('common.cancel')}</button>
    </form>}
    {canEdit && <details><summary className="text-xs">{t('insightWork.assignment')}</summary><InsightAssignmentForm key={data.work_revision} insight={data} assignees={assignees} allowOwnReview={Boolean(currentUser?.is_admin)} busy={busy} save={(body: InsightAssignment) => void act(() => api.assignInsight(projectId, data.id, body))} /></details>}
    {data.review_history?.length > 0 && <details className="text-xs"><summary>{t('insightReview.history')}</summary>{data.review_history.map((entry, i) => <div key={i} className="mt-2 rounded border border-ds-zinc-500/30 p-2"><p>{String(entry.at)} · {String(entry.action)} · #{String(entry.user_id)}</p><p className="whitespace-pre-wrap break-words">{String(entry.content)}</p><InsightEvidence evidence={(entry.evidence || []) as Evidence} /></div>)}</details>}
    {data.history_truncated && <p className="text-xs text-ds-amber-500">{t('insightWork.historyLimit')}</p>}
    {error && <p role="alert" className="text-xs text-ds-red-500">{error}</p>}
  </section>;
}
