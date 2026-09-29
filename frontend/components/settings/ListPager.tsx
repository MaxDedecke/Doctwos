"use client";

import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import React from 'react';

interface ListPagerProps {
  /** 0-basierte aktuelle Seite. */
  page: number;
  pageSize: number;
  /** Anzahl der Einträge auf der aktuellen Seite. */
  shown: number;
  total: number;
  loading?: boolean;
  theme: string;
  onPageChange: (page: number) => void;
}

/**
 * Gemeinsame Blätterleiste der serverseitig seitenweise geladenen Listen
 * (MCP-Audit, negativ bewertete Antworten): zeigt den Ausschnitt "von–bis von
 * gesamt" und blättert per Vor/Zurück. Rendert nichts, solange die Liste leer ist.
 */
export const ListPager: React.FC<ListPagerProps> = ({ page, pageSize, shown, total, loading = false, theme, onPageChange }) => {
  const { t } = useLanguage();
  if (total <= 0) return null;

  const dark = theme === 'dark';
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const from = page * pageSize + 1;
  const to = page * pageSize + shown;
  const control = dark
    ? 'bg-ds-zinc-900 border-ds-zinc-800 hover:bg-ds-zinc-800 text-ds-zinc-300'
    : 'bg-ds-white border-ds-zinc-200 hover:bg-ds-zinc-100 text-ds-zinc-700';

  return (
    <div className="flex items-center justify-between gap-3 text-[0.625rem]">
      <span className="text-ds-zinc-500" data-testid="list-pager-range">{t('settings.pager.range', { from, to, total })}</span>
      <div className="flex items-center gap-1.5">
        <Button type="button" size="sm" variant="outline" disabled={page === 0 || loading} onClick={() => onPageChange(page - 1)}
          aria-label={t('settings.pager.previousPage')} className={cn('h-7 w-7 p-0 focus:ring-0', control)}>
          <ChevronLeft className="w-3.5 h-3.5" />
        </Button>
        <span className="tabular-nums text-ds-zinc-500">{t('settings.pager.pageOf', { page: page + 1, pages: pageCount })}</span>
        <Button type="button" size="sm" variant="outline" disabled={page + 1 >= pageCount || loading} onClick={() => onPageChange(page + 1)}
          aria-label={t('settings.pager.nextPage')} className={cn('h-7 w-7 p-0 focus:ring-0', control)}>
          <ChevronRight className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
};
