"use client";

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Project, User } from '@/types/domain';
import type { InsightPage, InsightSummary, InsightDetail, InsightAssignees } from '@/lib/insights';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { InsightCommitCheck } from './InsightCommitCheck';
import { InsightDetailPanel } from './InsightDetailPanel';
import { InsightInbox } from './InsightInbox';

export function InsightReviewView(props: { selectedProject: Project | null; currentUser: User | null; theme: string; onOpenFile?: (path: string, line: number | null, sourceId: number | null) => void }) {
  const { t } = useLanguage();
  if (!props.selectedProject) return <p className="p-4 text-sm">{t('insightReview.selectProject')}</p>;
  return <InsightWorkspace key={`${props.selectedProject.id}:${props.currentUser?.id}`} {...props} projectId={props.selectedProject.id} />;
}

function InsightWorkspace({ projectId, currentUser, theme, onOpenFile }: {
  projectId: number; currentUser: User | null; theme: string;
  onOpenFile?: (path: string, line: number | null, sourceId: number | null) => void;
}) {
  const { t } = useLanguage();
  const [page, setPage] = useState<InsightPage | null>(null);
  const [assignees, setAssignees] = useState<InsightAssignees | null>(null);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [scope, setScope] = useState('all');
  const [needsReview, setNeedsReview] = useState(true);
  const [offset, setOffset] = useState(0);
  const [focus, setFocus] = useState<number | null>(null);
  const [loaded, setLoaded] = useState<Record<number, InsightDetail>>({});
  const [selected, setSelected] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [batchResult, setBatchResult] = useState('');
  const generation = useRef(0);
  const load = useCallback(async () => {
    const request = ++generation.current;
    setLoading(true); setError('');
    try {
      const [response, people] = await Promise.all([
        api.getInsightWorklist(projectId, { q: search, status: status === 'all' ? undefined : status, mine: scope === 'mine', unassigned: scope === 'unassigned', reviewer: scope === 'reviewer', needs_review: needsReview, offset, limit: 25 }),
        api.getInsightAssignees(projectId),
      ]);
      if (generation.current !== request) return;
      if (!response.data.items.length && offset > 0) { setOffset(Math.floor(Math.max(0, response.data.total - 1) / 25) * 25); return; }
      setPage(response.data); setAssignees(people.data);
    } catch { if (generation.current === request) setError(t('insightReview.loadFailed')); }
    finally { if (generation.current === request) setLoading(false); }
  }, [projectId, search, status, scope, needsReview, offset, t]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => { window.clearTimeout(timer); generation.current += 1; };
  }, [load]);
  useEffect(() => {
    const timer = window.setTimeout(() => { if (search !== query.trim()) { setSearch(query.trim()); setOffset(0); } }, 300);
    return () => window.clearTimeout(timer);
  }, [query, search]);
  const remember = useCallback((detail: InsightDetail) => setLoaded(previous => ({ ...previous, [detail.id]: detail })), []);
  const canManage = Boolean(assignees?.can_manage);
  const remove = async (row: InsightSummary) => {
    if (!window.confirm(t('insightReview.deleteConfirm', { title: row.title }))) return;
    const request = generation.current;
    try {
      await api.deleteInsight(projectId, row.id);
      if (generation.current !== request) return;
      setPage(previous => previous ? { ...previous, total: previous.total - 1, items: previous.items.filter(i => i.id !== row.id), counts: { ...previous.counts, [row.status]: Math.max(0, (previous.counts[row.status] || 0) - 1) } } : null);
      setSelected(ids => ids.filter(id => id !== row.id));
      if (focus === row.id) setFocus(null);
      if (page?.items.length === 1 && (page.has_more || offset > 0)) await load();
    } catch { if (generation.current === request) setError(t('insightReview.deleteFailed')); }
  };
  const batchApprove = async () => {
    if (!selected.length || !window.confirm(t('insightWork.batchConfirm', { count: selected.length }))) return;
    const request = generation.current;
    setLoading(true);
    try {
      const response = await api.batchApproveInsights(projectId, selected.map(id => ({ id, expected_revision: loaded[id].revision, expected_versions: loaded[id].current_versions })));
      if (generation.current !== request) return;
      const failures = response.data.items.filter(item => item.status === 'error');
      setBatchResult(t('insightWork.batchResult', { count: response.data.items.length - failures.length }) + failures.map(item => ` #${item.id}: ${item.detail}`).join('; '));
      setSelected([]); setLoaded({}); setFocus(null); await load();
    } catch { if (generation.current === request) { setError(t('insightWork.failed')); setLoading(false); } }
  };
  const names = new Map((assignees?.items || []).map(person => [person.id, person.name]));
  return <div className={cn('h-full overflow-y-auto p-4 text-sm', theme === 'dark' ? 'bg-ds-zinc-950 text-ds-zinc-200' : 'bg-ds-white text-ds-zinc-800')}>
    <header className="mb-4 flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-bold">{t('insightReview.title')}</h2><p className="mt-1 text-xs text-ds-zinc-500">{t('insightWork.orderHint')}</p></div><button type="button" onClick={() => void load()} className="rounded border border-ds-zinc-500/30 p-2 text-xs">{t('insightReview.refresh')}</button></header>
    <InsightInbox projectId={projectId} currentUser={currentUser} onOpen={setFocus} />
    <div className="my-4"><InsightCommitCheck projectId={projectId} canVerify={canManage} reviewerId={currentUser?.id} allowOwnReview={Boolean(currentUser?.is_admin)} theme={theme} onVerified={() => void load()} /></div>
    <div className="mb-3 flex flex-wrap gap-2 text-xs">
      <input aria-label={t('insightWork.search')} placeholder={t('insightWork.search')} value={query} onChange={e => setQuery(e.target.value)} className="min-w-0 flex-1 rounded border border-ds-zinc-500 bg-transparent p-2" />
      <select aria-label={t('insightWork.scope')} value={scope} onChange={e => { setScope(e.target.value); setOffset(0); }} className="rounded border border-ds-zinc-500 bg-card p-2">{['all','mine','reviewer','unassigned'].map(value => <option key={value} value={value}>{t(`insightWork.scopeValue.${value}`)}</option>)}</select>
      <label className="flex items-center gap-2"><input type="checkbox" checked={needsReview} onChange={e => { setNeedsReview(e.target.checked); setOffset(0); }} />{t('insightWork.onlyReview')}</label>
    </div>
    <div className="mb-3 flex flex-wrap gap-2 text-xs">{['all','outdated','draft','verified','rejected'].map(value => <button type="button" key={value} aria-pressed={status === value} onClick={() => { setStatus(value); setOffset(0); }} className={cn('rounded border p-2', status === value ? 'border-ds-indigo-500 text-ds-indigo-400' : 'border-ds-zinc-500/30')}>{t(`insightReview.filter.${value}`)} · {value === 'all' ? Object.values(page?.counts || {}).reduce((a,b) => a + (b || 0), 0) : page?.counts[value as keyof InsightPage['counts']] || 0}</button>)}</div>
    {selected.length > 0 && <button type="button" disabled={loading} onClick={() => void batchApprove()} className="mb-3 rounded bg-ds-emerald-600 p-2 text-xs text-ds-white">{t('insightWork.batchApprove', { count: selected.length })}</button>}
    {error && <p role="alert" className="mb-3 text-xs text-ds-red-500">{error}</p>}
    {batchResult && <p role="status" className="mb-3 text-xs">{batchResult}</p>}
    {focus != null && <div className="mb-4"><button type="button" onClick={() => setFocus(null)} className="mb-2 text-xs text-ds-indigo-400">{t('common.cancel')}</button><InsightDetailPanel key={focus} projectId={projectId} insightId={focus} currentUser={currentUser} onChanged={() => void load()} onLoaded={remember} onOpenFile={onOpenFile} /></div>}
    {loading && <p className="text-xs">{t('insightWork.loading')}</p>}
    {!loading && page?.items.length === 0 && <p>{t('insightReview.empty')}</p>}
    <div className="space-y-3">{page?.items.map(row => {
      const detail = loaded[row.id];
      const eligible = canManage && detail && detail.status !== 'rejected' && detail.version_state !== 'index_unavailable' && (detail.status !== 'verified' || !['current','project'].includes(detail.version_state)) && (currentUser?.is_admin || detail.created_by_id !== currentUser?.id);
      return <article key={row.id} className="rounded border border-ds-zinc-500/30 p-3">
        <div className="flex items-start justify-between gap-2"><h3 className="min-w-0 break-words font-semibold">{row.title}</h3><span className="text-xs">{t(`insightReview.status.${row.status}`)}</span></div>
        <p className="mt-2 text-xs">{t('insightWork.owner')}: {row.owner_id == null ? t('insightWork.unassigned') : names.get(row.owner_id) || `#${row.owner_id}`} · {t('insightWork.reviewer')}: {row.reviewer_id == null ? t('insightWork.unassigned') : names.get(row.reviewer_id) || `#${row.reviewer_id}`}</p>
        <p className="mt-1 text-xs">{t(`insightWork.priority.${row.priority ?? 1}`)}{row.due_at ? ` · ${new Date(row.due_at).toLocaleString()}` : ''} · {t(`insightCommit.versionState.${row.version_state}`)}</p>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs"><button type="button" onClick={() => setFocus(row.id)} className="text-ds-indigo-400">{t('insightWork.open')}</button>
          {canManage && <><label className="flex items-center gap-2"><input aria-label={`${t('insightWork.select')} ${row.title}`} type="checkbox" checked={selected.includes(row.id)} disabled={!eligible || (selected.length >= 20 && !selected.includes(row.id))} onChange={e => setSelected(ids => e.target.checked ? [...ids, row.id] : ids.filter(id => id !== row.id))} />{t('insightWork.selectHint')}</label><button type="button" onClick={() => void remove(row)} className="text-ds-red-500">{t('insightReview.delete')}</button></>}
        </div>
      </article>;
    })}</div>
    <footer className="mt-4 flex items-center justify-between gap-2 text-xs"><button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 25))} className="rounded border border-ds-zinc-500/30 p-2 disabled:opacity-50">{t('insightWork.previous')}</button><span>{t('insightWork.page', { from: page?.items.length ? offset + 1 : 0, to: offset + (page?.items.length || 0), total: page?.total || 0 })}</span><button disabled={!page?.has_more || loading} onClick={() => setOffset(offset + 25)} className="rounded border border-ds-zinc-500/30 p-2 disabled:opacity-50">{t('insightWork.next')}</button></footer>
  </div>;
}
