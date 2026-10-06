"use client";

import { api } from '@/app/services/api';
import { hasPulseContent, pulseTypesToShow, type ProjectPulse } from '@/lib/chatStarters';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import React from 'react';

/**
 * Kennzahlen des Projekts (Klassen, Interfaces, Methoden, Module …) an der Git-Wissensquelle.
 * Sie standen früher im leeren Chat; dort stören sie, hier gehören sie zur Quelle.
 */
export function GitSourcePulse({ projectId, theme }: { projectId: number; theme: string }) {
  const { t, language } = useLanguage();
  const [loaded, setLoaded] = React.useState<{ projectId: number; pulse: ProjectPulse | null } | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    Promise.resolve()
      .then(() => api.getProjectPulse(projectId))
      .then((res) => { if (!cancelled) setLoaded({ projectId, pulse: res.data?.counts ? res.data : null }); })
      .catch(() => { if (!cancelled) setLoaded({ projectId, pulse: null }); });
    return () => { cancelled = true; };
  }, [projectId]);

  const pulse = loaded?.projectId === projectId ? loaded.pulse : null;
  if (!hasPulseContent(pulse)) return null;
  const locale = language === 'de' ? 'de-DE' : 'en-US';
  const dark = theme === 'dark';

  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t pt-2 mt-1 border-ds-zinc-800/20" aria-label={t('settings.sourcesTab.pulseLabel')}>
      {pulseTypesToShow(pulse).map((type) => (
        <span key={type} className="inline-flex items-baseline gap-1.5">
          <span className={cn('tabular-nums font-semibold', dark ? 'text-ds-zinc-200' : 'text-ds-zinc-800')}>
            {pulse.counts[type].toLocaleString(locale)}
          </span>
          <span className="opacity-70">{t(`chatView.empty.counts.${type}`)}</span>
        </span>
      ))}
    </div>
  );
}
