"use client";

import type { ChatSource } from '@/types/domain';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { ChatInsightSource } from './ChatInsightSource';
import { CIBuildResults } from './CIBuildResults';

export function ChatReviewedSource({ source, onOpenFile }: { source: ChatSource; onOpenFile: (path: string, line: number | null, sourceId: number | null) => void }) {
  const { t } = useLanguage();
  if (source.kind === 'insight') return <ChatInsightSource source={source} onOpenFile={onOpenFile} />;
  return <details className="max-w-full rounded-lg border border-ds-indigo-500/40 bg-ds-indigo-500/10 text-xs">
    <summary className="cursor-pointer px-2.5 py-1 text-ds-indigo-400">{source.title || t('ciBuild.results')}</summary>
    <div className="max-w-lg space-y-2 p-3">
      <p className="text-ds-zinc-500">{t('chatView.ciSnapshot')}</p>
      <CIBuildResults data={{ status: 'found', items: source.build ? [source.build] : [] }} />
    </div>
  </details>;
}
