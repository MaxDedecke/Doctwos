"use client";

import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Lightbulb, Loader2 } from 'lucide-react';
import { useState } from 'react';

type Origin = 'chat' | 'code' | 'process';

interface Props {
  projectId?: number | null;
  origin: Origin;
  evidence: Array<Record<string, unknown>>;
  defaultTitle: string;
  theme: string;
  className?: string;
}

/** Compact inline form used where a user has just inspected the supporting evidence. */
export function InsightDraftAction({ projectId, origin, evidence, defaultTitle, theme, className }: Props) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(defaultTitle);
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unavailable = !projectId || evidence.length === 0;

  const save = async () => {
    if (!projectId || !title.trim() || !content.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.createInsight(projectId, { title: title.trim(), content: content.trim(), origin_kind: origin, evidence });
      setOpen(false);
      setContent('');
    } catch {
      setError(t('insightDraft.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        disabled={unavailable}
        onClick={() => setOpen(value => !value)}
        title={unavailable ? t('insightDraft.noEvidence') : t('insightDraft.action')}
        className="inline-flex h-7 items-center gap-1.5 rounded border border-ds-amber-500/50 px-2 text-[10px] font-semibold text-ds-amber-500 hover:bg-ds-amber-500/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Lightbulb className="h-3.5 w-3.5" />{t('insightDraft.action')}
      </button>
      {open && (
        <div className={cn('absolute right-0 z-30 mt-1 w-80 rounded-lg border p-3 shadow-xl', theme === 'dark' ? 'border-ds-zinc-700 bg-ds-zinc-900' : 'border-ds-zinc-300 bg-ds-white')}>
          <label className="block text-[10px] font-semibold text-ds-zinc-500">{t('insightDraft.title')}</label>
          <input value={title} onChange={event => setTitle(event.target.value)} maxLength={240} className="mt-1 w-full rounded border border-ds-zinc-600 bg-transparent px-2 py-1.5 text-xs" />
          <label className="mt-2 block text-[10px] font-semibold text-ds-zinc-500">{t('insightDraft.content')}</label>
          <textarea value={content} onChange={event => setContent(event.target.value)} rows={4} className="mt-1 w-full resize-y rounded border border-ds-zinc-600 bg-transparent px-2 py-1.5 text-xs" placeholder={t('insightDraft.contentHint')} />
          {error && <p className="mt-1 text-[10px] text-ds-red-500">{error}</p>}
          <div className="mt-2 flex justify-end gap-2">
            <button type="button" onClick={() => setOpen(false)} className="text-[10px] text-ds-zinc-500">{t('common.cancel')}</button>
            <button type="button" disabled={saving || !title.trim() || !content.trim()} onClick={save} className="inline-flex items-center gap-1 rounded bg-ds-amber-500 px-2 py-1 text-[10px] font-semibold text-black disabled:opacity-50">
              {saving && <Loader2 className="h-3 w-3 animate-spin" />}{t('insightDraft.saveDraft')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
