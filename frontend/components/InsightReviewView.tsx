"use client";

import type { Project, ProjectMember, User } from '@/types/domain';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Check, FileText, Link2, Loader2, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

type Insight = Awaited<ReturnType<typeof api.getInsights>>['data'][number];

export function InsightReviewView({ selectedProject, currentUser, theme }: { selectedProject: Project | null; currentUser: User | null; theme: string }) {
  const { t } = useLanguage();
  const [insights, setInsights] = useState<Insight[]>([]);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [linkCounts, setLinkCounts] = useState({ pending: 0, approved: 0, rejected: 0 });
  const [filter, setFilter] = useState<'all' | 'outdated' | 'draft' | 'verified'>('all');
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isDark = theme === 'dark';

  const load = useCallback(async () => {
    if (!selectedProject) return;
    setLoading(true);
    setError(null);
    try {
      const [insightResponse, memberResponse, linkResponse] = await Promise.all([
        api.getInsights(selectedProject.id), api.getProjectMembers(selectedProject.id),
        api.getLinkRecommendations(selectedProject.id),
      ]);
      setInsights([...insightResponse.data].sort((left, right) => {
        const priority = { outdated: 0, draft: 1, verified: 2 };
        return priority[left.status] - priority[right.status];
      }));
      setMembers(memberResponse.data);
      setLinkCounts(linkResponse.data.counts);
    } catch {
      setError(t('insightReview.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [selectedProject, t]);

  useEffect(() => {
    // Defer the initial fetch so React's effect compiler does not treat the
    // request's loading state as a synchronous render cascade.
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (!selectedProject) return <div className="p-5 text-sm text-ds-zinc-500">{t('insightReview.selectProject')}</div>;
  const canVerify = Boolean(currentUser?.is_admin || members.some(member => member.user_id === currentUser?.id && member.role === 'admin'));
  const insightCounts = insights.reduce((counts, insight) => ({ ...counts, [insight.status]: counts[insight.status] + 1 }), { outdated: 0, draft: 0, verified: 0 });
  const visibleInsights = filter === 'all' ? insights : insights.filter(insight => insight.status === filter);

  const verify = async (insight: Insight) => {
    setVerifying(insight.id);
    setError(null);
    try {
      await api.verifyInsight(selectedProject.id, insight.id);
      await load();
    } catch {
      setError(t('insightReview.verifyFailed'));
    } finally {
      setVerifying(null);
    }
  };

  return <div className={cn('h-full overflow-y-auto p-4', isDark ? 'bg-ds-zinc-950 text-ds-zinc-200' : 'bg-white text-ds-zinc-800')}>
    <div className="mb-4 flex items-center justify-between gap-3">
      <div><h2 className="text-sm font-bold">{t('insightReview.title')}</h2><p className="text-xs text-ds-zinc-500">{t('insightReview.description')}</p></div>
      <button type="button" onClick={() => void load()} title={t('insightReview.refresh')} className="rounded border border-ds-zinc-700 p-1.5 text-ds-zinc-400"><RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} /></button>
    </div>
    <div className="mb-4 flex flex-wrap gap-1.5">
      {(['all', 'outdated', 'draft', 'verified'] as const).map(status => <button key={status} type="button" onClick={() => setFilter(status)} className={cn('rounded border px-2 py-1 text-[10px] font-semibold', filter === status ? 'border-ds-indigo-500 bg-ds-indigo-500/15 text-ds-indigo-400' : 'border-ds-zinc-700 text-ds-zinc-500')}>
        {t(`insightReview.filter.${status}`)} · {status === 'all' ? insights.length : insightCounts[status]}
      </button>)}
    </div>
    <div className="mb-4 flex flex-wrap gap-2 text-[10px] text-ds-zinc-500"><span className="inline-flex items-center gap-1 rounded border border-ds-zinc-700 px-2 py-1"><Link2 className="h-3 w-3" />{t('insightReview.pendingLinks', { count: linkCounts.pending })}</span><span className="rounded border border-ds-zinc-700 px-2 py-1">{t('insightReview.rejectedLinks', { count: linkCounts.rejected })}</span></div>
    {error && <p className="mb-3 text-xs text-ds-red-500">{error}</p>}
    {!loading && insights.length === 0 && <p className="text-sm text-ds-zinc-500">{t('insightReview.empty')}</p>}
    <div className="space-y-3">{visibleInsights.map(insight => {
      const canApproveThis = canVerify && insight.status === 'draft' && insight.created_by_id !== currentUser?.id;
      return <article key={insight.id} className={cn('rounded-lg border p-3', isDark ? 'border-ds-zinc-800 bg-ds-zinc-900/60' : 'border-ds-zinc-200 bg-ds-zinc-50')}>
        <div className="flex items-start justify-between gap-2"><div><h3 className="text-sm font-semibold">{insight.title}</h3><p className="mt-1 whitespace-pre-wrap text-xs">{insight.content}</p></div><span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold', insight.status === 'verified' ? 'bg-ds-emerald-500/15 text-ds-emerald-500' : 'bg-ds-amber-500/15 text-ds-amber-500')}>{t(`insightReview.status.${insight.status}`)}</span></div>
        <div className="mt-2 flex items-center gap-1 text-[10px] text-ds-zinc-500"><FileText className="h-3 w-3" />{t('insightReview.evidenceCount', { count: insight.evidence.length })} · {t(`insightReview.origin.${insight.origin_kind}`)}</div>
        {insight.status === 'outdated' && <p className="mt-1 text-[10px] text-ds-amber-500">{t('insightReview.sourceChanged', { count: insight.outdated_source_ids.length })}</p>}
        {insight.evidence.some(item => typeof item.source_last_synced_at === 'string') && <p className="mt-1 text-[10px] text-ds-zinc-500">{t('insightReview.provenanceSnapshot')}</p>}
        {canApproveThis && <button type="button" disabled={verifying === insight.id} onClick={() => void verify(insight)} className="mt-3 inline-flex items-center gap-1.5 rounded bg-ds-emerald-600 px-2 py-1 text-[10px] font-semibold text-white disabled:opacity-50"><>{verifying === insight.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}</>{t('insightReview.verify')}</button>}
      </article>;
    })}</div>
  </div>;
}
