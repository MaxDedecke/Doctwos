"use client";

import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Lightbulb, Loader2, X } from 'lucide-react';
import { createPortal } from 'react-dom';
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
    <div className={cn('relative inline-flex items-center', className)}>
      <button
        type="button"
        disabled={unavailable}
        onClick={() => setOpen(true)}
        title={unavailable ? t('insightDraft.noEvidence') : t('insightDraft.action')}
        aria-label={t('insightDraft.action')}
        aria-expanded={open}
        className={cn(
          'group/insight inline-flex h-7 w-7 items-center overflow-hidden rounded-md border border-ds-amber-500/60 bg-ds-amber-500/10 text-ds-amber-500 transition-[width,background-color] duration-200 ease-out hover:w-[132px] hover:bg-ds-amber-500 focus-visible:w-[132px] focus-visible:bg-ds-amber-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ds-amber-400 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:w-7'
        )}
      >
        <Lightbulb className="ml-[7px] h-3.5 w-3.5 shrink-0 transition-colors group-hover/insight:text-ds-black group-focus-visible/insight:text-ds-black" />
        <span className="ml-2 whitespace-nowrap text-[10px] font-semibold opacity-0 transition-opacity duration-150 group-hover/insight:opacity-100 group-focus-visible/insight:opacity-100 group-hover/insight:text-ds-black group-focus-visible/insight:text-ds-black">
          {t('insightDraft.action')}
        </span>
      </button>
      {open && createPortal(
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-ds-black/60 p-4 backdrop-blur-sm" onMouseDown={event => { if (event.target === event.currentTarget && !saving) setOpen(false); }} onKeyDown={event => { if (event.key === 'Escape' && !saving) setOpen(false); }}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="insight-draft-dialog-title"
            className={cn('w-full max-w-lg rounded-lg border p-5 shadow-2xl', theme === 'dark' ? 'border-ds-zinc-700 bg-ds-zinc-900 text-ds-zinc-100' : 'border-ds-zinc-200 bg-ds-white text-ds-zinc-950')}
          >
            <header className="mb-4 flex items-center justify-between gap-3">
              <h2 id="insight-draft-dialog-title" className="flex items-center gap-2 text-sm font-semibold">
                <Lightbulb className="h-4 w-4 text-ds-amber-500" />{t('insightDraft.action')}
              </h2>
              <button type="button" disabled={saving} onClick={() => setOpen(false)} aria-label={t('common.cancel')} className="rounded p-1 text-ds-zinc-500 hover:bg-ds-zinc-500/10 hover:text-ds-zinc-200 disabled:opacity-50">
                <X className="h-4 w-4" />
              </button>
            </header>
            <label className="block text-[11px] font-semibold text-ds-zinc-500">{t('insightDraft.title')}</label>
            <input autoFocus value={title} onChange={event => setTitle(event.target.value)} maxLength={240} className="mt-1 w-full rounded-md border border-ds-zinc-600 bg-transparent px-3 py-2 text-sm focus:border-ds-amber-500 focus:outline-none" />
            <label className="mt-4 block text-[11px] font-semibold text-ds-zinc-500">{t('insightDraft.content')}</label>
            <textarea value={content} onChange={event => setContent(event.target.value)} rows={5} className="mt-1 w-full resize-y rounded-md border border-ds-zinc-600 bg-transparent px-3 py-2 text-sm focus:border-ds-amber-500 focus:outline-none" placeholder={t('insightDraft.contentHint')} />
            {error && <p className="mt-2 text-xs text-ds-red-500">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" disabled={saving} onClick={() => setOpen(false)} className="rounded-md px-3 py-2 text-xs text-ds-zinc-500 hover:bg-ds-zinc-500/10 disabled:opacity-50">{t('common.cancel')}</button>
              <button type="button" disabled={saving || !title.trim() || !content.trim()} onClick={save} className="inline-flex items-center gap-1.5 rounded-md bg-ds-amber-500 px-3 py-2 text-xs font-semibold text-ds-black hover:bg-ds-amber-400 disabled:opacity-50">
                {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{t('insightDraft.saveDraft')}
              </button>
            </div>
          </section>
        </div>,
        document.body
      )}
    </div>
  );
}
