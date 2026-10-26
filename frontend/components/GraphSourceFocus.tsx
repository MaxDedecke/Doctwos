'use client';

import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import type { KnowledgeSource } from '@/types/domain';
import React, { useEffect, useState } from 'react';

interface Props {
  isDark: boolean;
  projectId: number | null;
  value: number | null;
  disabled?: boolean;
  onChange: (sourceId: number | null) => void;
}

/** Wählt die Wissensquelle, deren Knoten der Graph bei gleichem Limit bevorzugt zeigt (samt Nachbarn). */
export function GraphSourceFocus({ isDark, projectId, value, disabled, onChange }: Props) {
  const { t } = useLanguage();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await api.getKnowledgeSources();
        if (!cancelled) setSources((res.data ?? []).filter(source => projectId !== null && source.project_id === projectId));
      } catch {
        if (!cancelled) setSources([]);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [projectId]);

  if (sources.length < 2) return null;

  return (
    <label className="flex items-center gap-1.5 text-xs" title={t('knowledgeGraphView.sourceFocusTitle')}>
      <span className={isDark ? 'text-ds-zinc-400' : 'text-ds-zinc-600'}>{t('knowledgeGraphView.sourceFocusLabel')}</span>
      <select
        value={value ?? ''}
        disabled={disabled}
        onChange={event => onChange(event.target.value ? Number(event.target.value) : null)}
        className={cn(
          'h-7 max-w-[11rem] rounded-md border px-1.5 text-xs',
          isDark ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-200' : 'border-ds-zinc-300 bg-ds-white text-ds-zinc-800',
        )}
      >
        <option value="">{t('knowledgeGraphView.sourceFocusAll')}</option>
        {sources.map(source => (
          <option key={source.id} value={String(source.id)}>{source.name}</option>
        ))}
      </select>
    </label>
  );
}
