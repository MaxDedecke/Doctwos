"use client";

import { cn } from '@/lib/utils';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { Download, MessageSquare, Pencil, Pin, PinOff, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';

// Grobe Zeilenhöhe (px-3 py-2 + Icon) -- vom Virtualizer nur als Startschätzung
// gebraucht, `measureElement` gleicht danach an die tatsächliche Höhe an.
const ESTIMATED_ROW_HEIGHT = 40;

// Ab so vielen Zeilen vor dem Listenende wird die nächste Seite nachgeladen.
const LOAD_MORE_THRESHOLD = 6;

export interface SidebarSession {
  id: number;
  title: string;
  is_pinned?: boolean;
}

interface VirtualizedSessionListProps {
  sessions: SidebarSession[];
  activeSessionId: number | null;
  theme: string;
  onSelect: (session: SidebarSession) => void;
  onRemove: (id: number, e: React.MouseEvent) => void;
  deleteSessionTitle: string;
  /** Es gibt ältere Sitzungen, die noch nicht geladen sind. */
  hasMore?: boolean;
  isLoadingMore?: boolean;
  onLoadMore?: () => void;
  /** Zeilenaktionen; ohne Angabe fehlt der jeweilige Knopf. */
  onRename?: (id: number, title: string) => void;
  onTogglePin?: (session: SidebarSession) => void;
  onExport?: (id: number) => void;
}

/**
 * O-036: Chat-Verlauf gefenstert gerendert statt der vollen Liste, damit die
 * Seitenleiste auch mit sehr vielen Sitzungen nicht anfängt zu ruckeln.
 */
export function VirtualizedSessionList({
  sessions,
  activeSessionId,
  theme,
  onSelect,
  onRemove,
  deleteSessionTitle,
  hasMore = false,
  isLoadingMore = false,
  onLoadMore,
  onRename,
  onTogglePin,
  onExport,
}: VirtualizedSessionListProps) {
  const { t } = useLanguage();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [renaming, setRenaming] = useState<{ id: number; title: string } | null>(null);
  const actionClass = cn(
    "p-1 rounded transition-all",
    theme === 'dark' ? "hover:bg-ds-zinc-700 text-ds-zinc-600 hover:text-ds-zinc-400" : "hover:bg-ds-zinc-200 text-ds-zinc-400 hover:text-ds-zinc-600"
  );
  const commitRename = () => {
    if (renaming && renaming.title.trim()) onRename?.(renaming.id, renaming.title.trim());
    setRenaming(null);
  };

  const virtualizer = useVirtualizer({
    count: sessions.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 8,
  });

  // Nähert sich die Ansicht dem Ende der geladenen Sitzungen, die nächste Seite holen.
  const items = virtualizer.getVirtualItems();
  const lastVisibleIndex = items.length > 0 ? items[items.length - 1].index : -1;
  useEffect(() => {
    if (hasMore && !isLoadingMore && onLoadMore && lastVisibleIndex >= sessions.length - 1 - LOAD_MORE_THRESHOLD) {
      onLoadMore();
    }
  }, [hasMore, isLoadingMore, onLoadMore, lastVisibleIndex, sessions.length]);

  return (
    <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-3 py-1.5">
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const session = sessions[virtualRow.index];
          return (
            <div
              key={session.id}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
              className="pb-0.5"
            >
              <div
                id={`sidebar-session-item-${session.id}`}
                onClick={() => onSelect(session)}
                className={cn(
                  "w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs transition-all group relative font-medium cursor-pointer",
                  activeSessionId === session.id
                    ? (theme === 'dark' ? "bg-ds-zinc-855 text-ds-zinc-150" : "bg-ds-zinc-200/75 text-ds-zinc-950")
                    : (theme === 'dark' ? "text-ds-zinc-400 hover:bg-ds-zinc-800 hover:text-ds-zinc-200" : "text-ds-zinc-600 hover:bg-ds-zinc-200/50 hover:text-ds-zinc-900")
                )}
              >
                {session.is_pinned
                  ? <Pin className="w-3.5 h-3.5 text-ds-indigo-500 shrink-0" />
                  : <MessageSquare className="w-3.5 h-3.5 text-ds-zinc-500 shrink-0" />}
                {renaming?.id === session.id ? (
                  <input
                    autoFocus
                    value={renaming.title}
                    aria-label={t('sidebar.renameSession')}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setRenaming({ id: session.id, title: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitRename();
                      if (e.key === 'Escape') setRenaming(null);
                    }}
                    onBlur={commitRename}
                    className="flex-1 min-w-0 bg-transparent border-b border-ds-indigo-500 outline-none"
                  />
                ) : (
                  <span className="truncate text-left flex-1">{session.title}</span>
                )}
                <div className="absolute right-2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-all">
                  {onRename && (
                    <button type="button" className={actionClass} title={t('sidebar.renameSession')} aria-label={t('sidebar.renameSession')}
                      onClick={(e) => { e.stopPropagation(); setRenaming({ id: session.id, title: session.title }); }}>
                      <Pencil className="w-3 h-3" />
                    </button>
                  )}
                  {onTogglePin && (
                    <button type="button" className={actionClass}
                      title={t(session.is_pinned ? 'sidebar.unpinSession' : 'sidebar.pinSession')}
                      aria-label={t(session.is_pinned ? 'sidebar.unpinSession' : 'sidebar.pinSession')}
                      onClick={(e) => { e.stopPropagation(); onTogglePin(session); }}>
                      {session.is_pinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
                    </button>
                  )}
                  {onExport && (
                    <button type="button" className={actionClass} title={t('sidebar.exportSession')} aria-label={t('sidebar.exportSession')}
                      onClick={(e) => { e.stopPropagation(); onExport(session.id); }}>
                      <Download className="w-3 h-3" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={(e) => onRemove(session.id, e)}
                    id={`sidebar-remove-session-${session.id}`}
                    className={actionClass}
                    title={deleteSessionTitle}
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {isLoadingMore && (
        <div className="flex items-center justify-center gap-1.5 py-2 text-[0.625rem] text-ds-zinc-500" role="status">
          <Loader2 className="w-3 h-3 animate-spin" />
        </div>
      )}
    </div>
  );
}
