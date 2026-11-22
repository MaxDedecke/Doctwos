"use client";

import { useCallback, useEffect, useRef, useState } from 'react';
import type { User } from '@/types/domain';
import type { InsightInboxData } from '@/lib/insights';
import { api } from '@/app/services/api';
import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Bell, CheckCheck, X } from 'lucide-react';
import { InsightDetailPanel } from './InsightDetailPanel';
import * as Dialog from '@radix-ui/react-dialog';

const REFRESH_MS = 60000;

/**
 * Hinweise zu Erkenntnissen als Glocke mit Zähler (wie die Aufgabenübersicht daneben). Ein Klick öffnet die
 * Liste; ein Hinweis öffnet seine Erkenntnis und gilt damit als gelesen.
 */
export function InsightInbox({ projectId, currentUser, onOpen, onOpenFile, theme = 'dark' }: {
  projectId: number;
  currentUser: Partial<User> | null;
  onOpen?: (id: number) => void;
  onOpenFile?: (path: string, line: number | null, sourceId: number | null) => void;
  theme?: string;
}) {
  const { t } = useLanguage();
  const [data, setData] = useState<InsightInboxData | null>(null);
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState<number | null>(null);
  const generation = useRef(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const dark = theme === 'dark';

  const load = useCallback(async () => {
    const request = ++generation.current;
    try { const r = await api.getInsightNotifications(projectId); if (generation.current === request) setData(r.data); }
    catch { if (generation.current === request) setData(null); }
  }, [projectId]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    const interval = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, REFRESH_MS);
    return () => { window.clearTimeout(timer); window.clearInterval(interval); generation.current += 1; };
  }, [load]);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', escape); };
  }, [open]);

  const unread = data?.unread_count ?? 0;
  return <div ref={rootRef} className="relative">
    <Button
      variant="ghost" size="icon" onClick={() => { setOpen(!open); void load(); }}
      aria-label={t('insightWork.notifications')} aria-expanded={open} title={t('insightWork.notifications')}
      className={cn("relative h-9 w-9 rounded-lg transition-colors duration-150", dark ? "text-ds-zinc-400 hover:text-ds-zinc-100 hover:bg-ds-zinc-800" : "text-ds-zinc-600 hover:text-ds-zinc-900 hover:bg-ds-zinc-200/70")}
    >
      <Bell className="h-4 w-4" />
      {unread > 0 && <span data-testid="insight-inbox-count" className="absolute -right-1 -top-1 min-w-4 h-4 px-1 rounded-full bg-ds-rose-600 text-ds-white text-[0.5625rem] leading-4 font-bold">{unread > 99 ? '99+' : unread}</span>}
    </Button>
    <span className="sr-only" aria-live="polite">{t('insightWork.unreadCount', { count: unread })}</span>
    {open && <section aria-label={t('insightWork.notifications')} className={cn("absolute right-0 top-10 z-[110] w-[min(24rem,calc(100vw-1rem))] rounded-xl border shadow-2xl", dark ? "bg-ds-zinc-950 border-ds-zinc-800" : "bg-ds-white border-ds-zinc-200")}>
      <header className={cn("flex items-center justify-between gap-2 px-4 py-3 border-b", dark ? "border-ds-zinc-800/50" : "border-ds-zinc-200")}>
        <h2 className="text-sm font-bold">{t('insightWork.notifications')}</h2>
        <div className="flex items-center gap-2">
          {unread > 0 && <button type="button" onClick={() => { void api.readInsightNotifications(projectId).then(load).catch(() => {}); }} title={t('insightWork.markRead')} aria-label={t('insightWork.markRead')} className="text-ds-zinc-500 hover:text-ds-indigo-500"><CheckCheck className="h-4 w-4" /></button>}
          <button type="button" onClick={() => setOpen(false)} aria-label={t('common.close')}><X className="h-4 w-4 text-ds-zinc-500" /></button>
        </div>
      </header>
      <div className="max-h-[24rem] overflow-y-auto p-2">
        {!data && <p className="p-6 text-center text-xs text-ds-zinc-500">{t('insightWork.failed')}</p>}
        {data && data.items.length === 0 && <p className="p-6 text-center text-xs text-ds-zinc-500">{t('insightWork.noNotifications')}</p>}
        {data?.items.map(item => <button key={item.id} type="button" aria-label={`${t('insightWork.event.' + item.kind)}: ${item.title}`}
          onClick={() => { setOpen(false); void api.readInsightNotification(projectId, item.id).then(load).catch(() => {}); if (onOpen) onOpen(item.insight_id); else setFocus(item.insight_id); }}
          className={cn("mb-2 block w-full rounded-lg border p-3 text-left text-xs transition-colors", dark ? "border-ds-zinc-800 bg-ds-zinc-900/50 hover:bg-ds-zinc-900" : "border-ds-zinc-200 bg-ds-zinc-50 hover:bg-ds-zinc-100")}>
          <span className="block text-[0.625rem] font-semibold uppercase tracking-wider text-ds-indigo-500">{t(`insightWork.event.${item.kind}`)}</span>
          <span className="mt-0.5 block font-semibold">{item.title}</span>
        </button>)}
        {data?.has_more && <p className="px-2 pb-1 text-[0.625rem] text-ds-zinc-500">{t('insightWork.moreNotifications')}</p>}
      </div>
    </section>}
    {focus != null && <Dialog.Root open onOpenChange={isOpen => { if (!isOpen) setFocus(null); }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/60" /><Dialog.Content className="fixed left-1/2 top-1/2 z-[111] max-h-[85vh] w-[calc(100%_-_2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded border border-border bg-card p-4 text-foreground"><Dialog.Title>{t('insightWork.detail')}</Dialog.Title><Dialog.Description>{t('insightWork.notifications')}</Dialog.Description><Dialog.Close className="my-2 text-xs text-ds-indigo-400">{t('common.cancel')}</Dialog.Close><InsightDetailPanel key={focus} projectId={projectId} insightId={focus} currentUser={currentUser} onChanged={() => void load()} onOpenFile={(path, line, sourceId) => { if (onOpenFile) { setFocus(null); onOpenFile(path, line, sourceId); } }} /></Dialog.Content></Dialog.Portal></Dialog.Root>}
  </div>;
}
