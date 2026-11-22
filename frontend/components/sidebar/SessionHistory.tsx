"use client";

import { api } from '@/app/services/api';
import type { ChatSession, Project } from '@/types/domain';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { cn } from '@/lib/utils';
import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { VirtualizedSessionList, type SidebarSession } from './VirtualizedSessionList';

const SEARCH_DEBOUNCE_MS = 250;

interface SessionHistoryProps {
  /** Die Suche klappt über die Lupe neben „Verlauf“ auf und wieder zu; zugeklappt gilt keine Suche. */
  searchOpen: boolean;
  onCloseSearch: () => void;
  sessions: ChatSession[];
  selectedProject: Project | null;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore?: () => void;
  activeSessionId: number | null;
  theme: string;
  onSelect: (session: ChatSession) => void;
  onRemove: (id: number, e: React.MouseEvent) => void;
}

type Override = Partial<Pick<ChatSession, 'title' | 'is_pinned'>>;

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Verlauf der Seitenleiste: Suche im Titel (serverseitig), angeheftete Sitzungen oben, Umbenennen, Anheften
 * und Export als Markdown je Zeile. Änderungen gelten sofort hier; die geladene Sitzungsliste der Seite
 * bleibt unberührt und übernimmt sie beim nächsten Laden.
 */
export function SessionHistory({
  searchOpen, onCloseSearch, sessions, selectedProject, hasMore, isLoadingMore, onLoadMore, activeSessionId, theme, onSelect, onRemove,
}: SessionHistoryProps) {
  const { t } = useLanguage();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<{ query: string; sessions: ChatSession[] } | null>(null);
  const [pinned, setPinned] = useState<ChatSession[]>([]);
  const [overrides, setOverrides] = useState<Record<number, Override>>({});
  const [error, setError] = useState<string | null>(null);
  const context = useMemo(
    () => (selectedProject ? { project_id: Number(selectedProject.id) } : { general: true }),
    [selectedProject],
  );

  useEffect(() => {
    let active = true;
    api.getChatSessionsPage({ ...context, pinned: true, limit: 50 })
      .then(res => { if (active) setPinned(res.data.sessions); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [context]);

  const trimmed = searchOpen ? query.trim() : '';
  useEffect(() => {
    if (!trimmed) return;
    const timer = setTimeout(() => {
      api.getChatSessionsPage({ ...context, q: trimmed, limit: 50 })
        .then(res => setResults({ query: trimmed, sessions: res.data.sessions }))
        .catch(() => setError(t('sidebar.sessionActionFailed')));
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [context, trimmed, t]);

  const apply = (session: ChatSession): ChatSession => ({ ...session, ...overrides[session.id] });
  const pinnedIds = new Set(pinned.map(session => session.id));
  const shown = trimmed
    ? (results?.query === trimmed ? results.sessions : []).map(apply)
    : [
      ...pinned.map(apply).filter(session => session.is_pinned),
      ...sessions.filter(session => !pinnedIds.has(session.id)).map(apply).filter(session => !session.is_pinned),
    ];
  const byId = new Map([...sessions, ...pinned, ...(results?.sessions ?? [])].map(session => [session.id, session]));

  const update = async (id: number, data: Override) => {
    setError(null);
    try {
      const res = await api.updateChatSession(id, data);
      setOverrides(current => ({ ...current, [id]: { title: res.data.title, is_pinned: res.data.is_pinned } }));
      if (data.is_pinned === true) setPinned(current => [apply(res.data), ...current.filter(s => s.id !== id)]);
      if (data.is_pinned === false) setPinned(current => current.filter(s => s.id !== id));
    } catch {
      setError(t('sidebar.sessionActionFailed'));
    }
  };
  const exportSession = async (id: number) => {
    setError(null);
    try {
      const res = await api.exportChatSession(id);
      const title = (overrides[id]?.title ?? byId.get(id)?.title ?? 'chat').replace(/[^\w\-äöüÄÖÜß]+/g, '-');
      download(res.data, `doctus-${title}.md`);
    } catch {
      setError(t('sidebar.sessionActionFailed'));
    }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {searchOpen && <div className="px-3 pb-1">
        <label className={cn(
          "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors",
          theme === 'dark'
            ? "border-ds-zinc-800 bg-ds-zinc-900/60 focus-within:border-ds-zinc-700"
            : "border-ds-zinc-200 bg-ds-white focus-within:border-ds-zinc-300",
        )}>
          <Search className="w-3 h-3 text-ds-zinc-500 shrink-0" />
          <input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder={t('sidebar.searchSessions')}
            aria-label={t('sidebar.searchSessions')}
            onKeyDown={e => { if (e.key === 'Escape') { setQuery(''); onCloseSearch(); } }}
            className="flex-1 min-w-0 bg-transparent outline-none placeholder:text-ds-zinc-500" />
          <button type="button" onClick={() => { setQuery(''); onCloseSearch(); }} aria-label={t('sidebar.clearSessionSearch')}>
            <X className="w-3 h-3 text-ds-zinc-500" />
          </button>
        </label>
        {error && <p role="alert" className="pt-1 text-[0.625rem] text-ds-red-500">{error}</p>}
        {trimmed && results?.query === trimmed && results.sessions.length === 0 && (
          <p className="pt-1 text-[0.625rem] text-ds-zinc-500">{t('sidebar.noSessionMatches')}</p>
        )}
      </div>}
      {!searchOpen && error && <p role="alert" className="px-4 pb-1 text-[0.625rem] text-ds-red-500">{error}</p>}
      <VirtualizedSessionList
        sessions={shown}
        hasMore={!trimmed && hasMore}
        isLoadingMore={!trimmed && isLoadingMore}
        onLoadMore={onLoadMore}
        activeSessionId={activeSessionId}
        theme={theme}
        onSelect={(session: SidebarSession) => {
          const original = byId.get(session.id);
          if (original) onSelect(apply(original));
        }}
        onRemove={(id, event) => {
          setPinned(current => current.filter(session => session.id !== id));
          setResults(current => current && { ...current, sessions: current.sessions.filter(session => session.id !== id) });
          onRemove(id, event);
        }}
        deleteSessionTitle={t('sidebar.deleteSessionTitle')}
        onRename={(id, title) => void update(id, { title })}
        onTogglePin={session => void update(session.id, { is_pinned: !session.is_pinned })}
        onExport={id => void exportSession(id)}
      />
    </div>
  );
}
