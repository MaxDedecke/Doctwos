"use client";

import type { ChatSource } from '@/types/domain';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { Lightbulb } from 'lucide-react';
import { InsightEvidence } from './InsightEvidence';

export function ChatInsightSource({ source, onOpenFile }: { source: ChatSource; onOpenFile: (path: string, line: number | null, sourceId: number | null) => void }) {
  const { t } = useLanguage();
  return <details className="max-w-full rounded-lg border border-ds-amber-500/40 bg-ds-amber-500/10 text-xs">
    <summary className="flex cursor-pointer items-center gap-1.5 px-2.5 py-1 text-ds-amber-500">
      <Lightbulb className="h-3 w-3 shrink-0" />
      <span className="truncate">{t('chatView.insightSource', { title: source.title || String(source.insight_id) })}</span>
    </summary>
    <div className="max-w-lg space-y-2 p-3">
      <p className="text-ds-zinc-500">{t('chatView.insightSnapshot')}</p>
      <p className="whitespace-pre-wrap break-words">{source.content}</p>
      <InsightEvidence evidence={source.evidence || []} onOpenFile={onOpenFile} />
    </div>
  </details>;
}
