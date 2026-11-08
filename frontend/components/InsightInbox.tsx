"use client";

import { useCallback, useEffect, useRef, useState } from 'react';
import type { User } from '@/types/domain';
import type { InsightInboxData } from '@/lib/insights';
import { api } from '@/app/services/api';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { Bell } from 'lucide-react';
import { InsightDetailPanel } from './InsightDetailPanel';
import * as Dialog from '@radix-ui/react-dialog';

export function InsightInbox({ projectId, currentUser, onOpen, align = 'down', onOpenFile }: { projectId: number; currentUser: Partial<User> | null; onOpen?: (id: number) => void; align?: 'up' | 'down'; onOpenFile?: (path: string, line: number | null, sourceId: number | null) => void }) {
  const { t } = useLanguage();
  const [data, setData] = useState<InsightInboxData | null>(null);
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState<number | null>(null);
  const generation = useRef(0);
  const load = useCallback(async () => {
    const request = ++generation.current;
    try { const r = await api.getInsightNotifications(projectId); if (generation.current === request) setData(r.data); }
    catch { if (generation.current === request) setData(null); }
  }, [projectId]);
  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    const interval = window.setInterval(() => { if (document.visibilityState !== 'hidden') void load(); }, 60000);
    return () => { window.clearTimeout(timer); window.clearInterval(interval); generation.current += 1; };
  }, [load]);
  return <div className="relative text-xs">
    <button type="button" onClick={() => { setOpen(!open); void load(); }} aria-label={t('insightWork.notifications')} className="flex items-center gap-2 rounded border border-ds-zinc-500/30 p-2"><Bell className="h-4 w-4" />{t('insightWork.notifications')} · {data?.unread_count ?? '—'}</button>
    {open && <section className={`absolute left-0 z-50 max-h-80 w-72 max-w-[calc(100vw-2rem)] overflow-auto rounded border border-ds-zinc-500/30 bg-card p-3 text-foreground shadow-lg ${align === 'up' ? 'bottom-full mb-2' : 'top-full mt-1'}`}>
      {!data ? <p>{t('insightWork.failed')}</p> : <><p className="mb-2 font-semibold">{t('insightWork.notifications')} · {data.unread_count}</p>
        {data.items.map(item => <button key={item.id} type="button" aria-label={`${t('insightWork.event.' + item.kind)}: ${item.title}`} onClick={() => { setOpen(false); void api.readInsightNotification(projectId, item.id).then(load).catch(() => {}); if (onOpen) onOpen(item.insight_id); else setFocus(item.insight_id); }} className="mb-2 block w-full rounded border border-ds-zinc-500/30 p-2 text-left"><span className="block">{t(`insightWork.event.${item.kind}`)}</span><span className="block font-semibold">{item.title}</span></button>)}
        {data.has_more && <p>{t('insightWork.moreNotifications')}</p>}
        {data.unread_count > 0 && <button type="button" onClick={() => { void api.readInsightNotifications(projectId).then(load).catch(() => {}); }} className="text-ds-indigo-400">{t('insightWork.markRead')}</button>}</>}
    </section>}
    {focus != null && <Dialog.Root open onOpenChange={isOpen => { if (!isOpen) setFocus(null); }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[110] bg-ds-black/60" /><Dialog.Content className="fixed left-1/2 top-1/2 z-[111] max-h-[85vh] w-[calc(100%_-_2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded border border-border bg-card p-4 text-foreground"><Dialog.Title>{t('insightWork.detail')}</Dialog.Title><Dialog.Description>{t('insightWork.notifications')}</Dialog.Description><Dialog.Close className="my-2 text-xs text-ds-indigo-400">{t('common.cancel')}</Dialog.Close><InsightDetailPanel key={focus} projectId={projectId} insightId={focus} currentUser={currentUser} onChanged={() => void load()} onOpenFile={(path, line, sourceId) => { if (onOpenFile) { setFocus(null); onOpenFile(path, line, sourceId); } }} /></Dialog.Content></Dialog.Portal></Dialog.Root>}

  </div>;
}
