"use client";

import { useEffect, useRef, useState } from 'react';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import type { Evidence } from '@/lib/insights';

export function InsightEvidenceEditor({ projectId, value, onChange }: { projectId: number; value: Evidence; onChange: (value: Evidence) => void }) {
  const { t } = useLanguage();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('code');
  const [results, setResults] = useState<Array<{ label: string; evidence: Record<string, unknown> }>>([]);
  const [error, setError] = useState('');
  const [truncated, setTruncated] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    const request = ++generation.current;
    const timer = window.setTimeout(() => {
      setResults([]); setError(''); setTruncated(false);
      if (query.trim().length < 2) return;
      api.getInsightEvidenceOptions(projectId, query.trim(), kind).then(response => {
        if (generation.current === request) { setResults(response.data.items); setTruncated(response.data.truncated); }
      }).catch(() => { if (generation.current === request) setError(t('insightWork.failed')); });
    }, 300);
    return () => { window.clearTimeout(timer); generation.current += 1; };
  }, [query, kind, projectId, t]);
  return <fieldset className="space-y-2 rounded border border-ds-zinc-500/30 p-3 text-xs">
    <legend>{t('insightWork.evidence')}</legend>
    {value.map((item, index) => <div key={index} className="flex flex-wrap items-center gap-2 rounded border border-ds-zinc-500/20 p-2">
      <span className="min-w-0 flex-1 break-words">{String(item.file || (item.insight_id ? `#${item.insight_id}` : JSON.stringify(item)))}</span>
      {item.file != null && <><label>{t('insightWork.fromLine')}<input aria-label={`${t('insightWork.fromLine')} ${index + 1}`} type="number" min={1} value={Number(item.start_line || (item.lines as number[] | undefined)?.[0] || 1)} onChange={event => { const { lines: _lines, ...base } = item; void _lines; onChange(value.map((row, i) => i === index ? { ...base, start_line: Number(event.target.value) } : row)); }} className="ml-1 w-16 rounded border border-ds-zinc-500 bg-transparent p-1" /></label>
        <label>{t('insightWork.toLine')}<input aria-label={`${t('insightWork.toLine')} ${index + 1}`} type="number" min={1} value={item.end_line == null ? '' : Number(item.end_line)} onChange={event => onChange(value.map((row, i) => i === index ? { ...row, end_line: event.target.value ? Number(event.target.value) : undefined } : row))} className="ml-1 w-16 rounded border border-ds-zinc-500 bg-transparent p-1" /></label></>}
      <button type="button" onClick={() => onChange(value.filter((_, i) => i !== index))} className="text-ds-red-500">{t('insightWork.removeEvidence')}</button>
    </div>)}
    <div className="flex flex-wrap gap-2">
      <select aria-label={t('insightWork.evidenceKind')} value={kind} onChange={e => setKind(e.target.value)} className="rounded border border-ds-zinc-500 bg-card p-2">
        {['code', 'file', 'insight', 'ci'].map(k => <option key={k} value={k}>{t(`insightWork.kind.${k}`)}</option>)}
      </select>
      <input aria-label={t('insightWork.searchEvidence')} value={query} onChange={e => setQuery(e.target.value)} placeholder={t('insightWork.searchEvidence')} className="min-w-0 flex-1 rounded border border-ds-zinc-500 bg-transparent p-2" />
    </div>
    {results.map((result, index) => <button key={index} type="button" disabled={value.length >= 50} onClick={() => { onChange([...value, result.evidence]); setQuery(''); setResults([]); }} className="block w-full rounded border border-ds-zinc-500/30 p-2 text-left text-ds-indigo-400">{t('insightWork.addEvidence')} · {result.label}</button>)}
    {truncated && <p>{t('insightWork.narrowSearch')}</p>}
    {error && <p role="alert" className="text-ds-red-500">{error}</p>}
  </fieldset>;
}
