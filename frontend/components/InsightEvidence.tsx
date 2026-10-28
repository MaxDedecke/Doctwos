"use client";

import { useLanguage } from '@/lib/i18n/LanguageContext';

export function InsightEvidence({ evidence, onOpenFile }: { evidence: Array<Record<string, unknown>>; onOpenFile?: (path: string, line: number | null, sourceId: number | null) => void }) {
  const { t } = useLanguage();
  return <details className="mt-2 text-xs">
    <summary className="cursor-pointer text-ds-indigo-400">{t('insightReview.evidenceCount', { count: evidence.length })}</summary>
    <div className="mt-2 space-y-2">{evidence.map((item, index) => <div key={index} className="rounded border border-ds-zinc-500/30 p-2">
      {typeof item.file === 'string' && onOpenFile && <button type="button" className="mb-2 text-ds-indigo-400 underline" onClick={() => onOpenFile(item.file as string, typeof item.start_line === 'number' ? item.start_line : Number.parseInt(String(item.lines || ''), 10) || null, typeof item.source_id === 'number' ? item.source_id : null)}>{t('insightEvidence.openSource')}</button>}
      {Object.entries(item).map(([key, value]) => value == null ? null : <div key={key} className="flex gap-2 py-0.5">
        <span className="shrink-0 text-ds-zinc-500">{t(`insightEvidence.${key}`) === `insightEvidence.${key}` ? key : t(`insightEvidence.${key}`)}</span>
        <span className="min-w-0 whitespace-pre-wrap break-words">{typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}</span>
      </div>)}
    </div>)}</div>
  </details>;
}
