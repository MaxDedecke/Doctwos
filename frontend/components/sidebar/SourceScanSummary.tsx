"use client";

import { cn } from '@/lib/utils';
import { useLanguage } from '@/lib/i18n/LanguageContext';

export interface SourceScanSummaryData {
  total_files: number;
  by_status: Record<string, number>;
  by_reason?: Record<string, { total_files: number; by_language: Record<string, number> }>;
  parser_error_classes?: Record<string, number>;
  edges?: {
    unresolved_external: number;
    unresolved_open: number;
  };
}

/**
 * O-380: zeigt je Quelle, wie viele Dateien nicht vollständig strukturiert
 * wurden und warum, damit Nutzer abschätzen können, was der Index nicht abdeckt.
 * Ohne betroffene Dateien und ohne offene Kanten rendert die Komponente nichts.
 */
export function SourceScanSummary({ summary, theme }: { summary?: SourceScanSummaryData; theme: string }) {
  const { t } = useLanguage();
  if (!summary) return null;
  const reasons = Object.entries(summary.by_reason ?? {})
    .filter(([, v]) => v.total_files > 0)
    .sort((a, b) => b[1].total_files - a[1].total_files);
  const affected = reasons.reduce((sum, [, v]) => sum + v.total_files, 0);
  const openEdges = summary.edges?.unresolved_open ?? 0;
  const externalEdges = summary.edges?.unresolved_external ?? 0;
  if (affected === 0 && openEdges === 0 && externalEdges === 0) return null;

  const muted = theme === 'dark' ? 'text-ds-zinc-400' : 'text-ds-zinc-600';
  const languages = (byLanguage: Record<string, number>) =>
    Object.entries(byLanguage)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4)
      .map(([lang, n]) => `${lang} ${n}`)
      .join(', ');

  return (
    <details data-testid="source-scan-summary" className={cn('px-2 py-1 text-[0.625rem]', muted)}>
      <summary className="cursor-pointer select-none font-medium">
        {t('sidebar.scanSummaryTitle')
          .replace('{count}', String(affected))
          .replace('{total}', String(summary.total_files))}
      </summary>
      <ul className="mt-1 space-y-0.5">
        {reasons.map(([reason, v]) => (
          <li key={reason} className="flex justify-between gap-2">
            <span className="truncate" title={languages(v.by_language)}>
              {t(`sidebar.scanReason_${reason}`)}
            </span>
            <span className="shrink-0 tabular-nums">{v.total_files}</span>
          </li>
        ))}
        {openEdges > 0 && (
          <li className="flex justify-between gap-2">
            <span className="truncate">{t('sidebar.scanEdgesOpen')}</span>
            <span className="shrink-0 tabular-nums">{openEdges}</span>
          </li>
        )}
        {externalEdges > 0 && (
          <li className="flex justify-between gap-2">
            <span className="truncate">{t('sidebar.scanEdgesExternal')}</span>
            <span className="shrink-0 tabular-nums">{externalEdges}</span>
          </li>
        )}
      </ul>
    </details>
  );
}
