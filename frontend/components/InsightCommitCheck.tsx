"use client";

import { useEffect, useRef, useState } from 'react';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { InsightEvidence } from './InsightEvidence';

type Report = Awaited<ReturnType<typeof api.checkInsightCommit>>['data'];
type Source = Awaited<ReturnType<typeof api.getInsightCommitSources>>['data'][number];

export function InsightCommitCheck({ projectId, canVerify, onVerified, reviewerId, allowOwnReview, theme }: {
  projectId: number;
  reviewerId?: number;
  allowOwnReview?: boolean;
  theme: string;
  canVerify: boolean;
  onVerified: () => void;
}) {
  const { t } = useLanguage();
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [targetRef, setTargetRef] = useState('');
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);

  useEffect(() => {
    const request = ++generation.current;
    api.getInsightCommitSources(projectId).then(response => {
      if (generation.current !== request) return;
      setSources(response.data);
      if (response.data.length === 1) setSourceId(String(response.data[0].id));
    }).catch(() => {
      if (generation.current === request) setError(t('insightCommit.loadFailed'));
    });
    return () => { generation.current += 1; };
  }, [projectId, t]);

  const clearReport = () => {
    generation.current += 1;
    setReport(null);
    setError('');
    setLoading(false);
  };

  const check = async (afterId = 0) => {
    const request = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const response = await api.checkInsightCommit(projectId, Number(sourceId), targetRef, afterId);
      if (generation.current !== request) return;
      setReport(response.data);
    } catch {
      if (generation.current === request) setError(t('insightCommit.checkFailed'));
    } finally {
      if (generation.current === request) setLoading(false);
    }
  };

  const approve = async (item: Report['items'][number]) => {
    if (!window.confirm(t('insightCommit.confirm', { commit: report?.target_commit.slice(0, 12) ?? '' }))) return;
    const request = ++generation.current;
    setLoading(true);
    setError('');
    try {
      await api.verifyInsight(projectId, item.id, item.revision, item.current_versions);
      if (generation.current !== request) return;
      onVerified();
      await check();
    } catch {
      if (generation.current === request) setError(t('insightCommit.approveFailed'));
    } finally {
      if (generation.current === request) setLoading(false);
    }
  };

  return (
    <section className="mb-4 rounded-lg border border-ds-zinc-500/30 p-3">
      <h3 className="text-sm font-semibold">{t('insightCommit.title')}</h3>
      <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void check(); }}>
        <label className="text-xs">
          {t('insightCommit.source')}
          <select value={sourceId} required className={`mt-1 block rounded border border-ds-zinc-500 p-2 ${theme === 'dark' ? 'bg-ds-zinc-900' : 'bg-ds-white'}`} onChange={event => {
            clearReport();
            setSourceId(event.target.value);
          }}>
            <option value="">{t('insightCommit.selectSource')}</option>
            {sources.map(source => <option key={source.id} value={source.id}>{source.name} · {source.branch || t('insightCommit.noBranch')}</option>)}
          </select>
        </label>
        <label className="text-xs">
          {t('insightCommit.target')}
          <input value={targetRef} required maxLength={256} placeholder="HEAD"
            className="mt-1 block rounded border border-ds-zinc-500 bg-transparent p-2"
            onChange={event => { clearReport(); setTargetRef(event.target.value); }} />
        </label>
        <button type="submit" disabled={loading || !sourceId || !targetRef.trim()} className="rounded bg-ds-indigo-600 px-3 py-2 text-xs text-ds-white disabled:opacity-50">
          {t(loading ? 'insightCommit.loading' : 'insightCommit.check')}
        </button>
      </form>
      {error && <p role="alert" className="mt-2 text-xs text-ds-red-500">{error}</p>}
      {report && (
        <div className="mt-3 space-y-3">
          <p className="break-all text-xs">{report.branch || t('insightCommit.noBranch')} · {report.target_commit}</p>
          <p className="text-xs text-ds-zinc-500">{t('insightCommit.scopeNote')}</p>
          {!report.target_indexed && <p className="text-xs text-ds-amber-500">{t('insightCommit.notIndexed')}</p>}
          {report.items.length === 0 && <p className="text-xs">{t('insightCommit.empty')}</p>}
          {report.items.map(item => (
            <article key={item.id} className="rounded border border-ds-zinc-500/30 p-3 text-xs">
              <p className="font-semibold">{item.title}</p>
              <p className="mt-1">{t(`insightCommit.result.${item.result}`)} · {t(`insightReview.status.${item.status}`)}</p>
              <p className="mt-1 text-ds-zinc-500">{t(`insightCommit.reason.${item.reason}`)}</p>
              <p className="mt-2 whitespace-pre-wrap">{item.content}</p>
              {item.base_commit && <p className="mt-2 break-all">{item.base_commit} → {report.target_commit}</p>}
              {item.files.map(file => (
                <details key={file.file} className="mt-2">
                  <summary className="cursor-pointer break-all text-ds-indigo-400">{file.change} · {file.file} · {t(`insightCommit.fileKind.${file.kind}`)}</summary>
                  {file.diff?.text && <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap">{file.diff.text}</pre>}
                  {file.diff?.truncated && <p className="text-ds-amber-500">{t('insightCommit.previewTruncated')}</p>}
                </details>
              ))}
              <InsightEvidence evidence={item.evidence} />
              <details className="mt-2">
                <summary className="cursor-pointer">{t('insightCommit.bindings')}</summary>
                <InsightEvidence evidence={item.version_bindings || []} />
              </details>
              {canVerify && item.can_verify && (allowOwnReview || item.created_by_id !== reviewerId) && <button type="button" disabled={loading}
                onClick={() => void approve(item)} className="mt-3 rounded bg-ds-emerald-600 px-2 py-1 text-ds-white disabled:opacity-50">
                {t('insightCommit.approve')}
              </button>}
            </article>
          ))}
          {report.next_cursor !== null && <button type="button" disabled={loading} className="text-xs text-ds-indigo-400" onClick={() => void check(report.next_cursor ?? 0)}>{t('insightCommit.next')}</button>}
        </div>
      )}
    </section>
  );
}
