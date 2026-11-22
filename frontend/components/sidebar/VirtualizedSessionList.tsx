"use client";

import { cn } from '@/lib/utils';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Download, MessageSquare, MoreHorizontal, Pencil, Pin, PinOff, Trash2 } from 'lucide-react';
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
  const [menuOpenId, setMenuOpenId] = useState<number | null>(null);
  // Umbenennen beginnt erst, wenn das Menü zu ist: Es gäbe den Fokus sonst an den Knopf zurück, und das
  // Eingabefeld würde sofort wieder verlassen.
  const pendingRename = useRef<{ id: number; title: string } | null>(null);
  const menuItemClass = cn("text-xs gap-2", theme === 'dark' ? "focus:bg-ds-zinc-800" : "focus:bg-ds-zinc-100");
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
                  <span className="min-w-0 flex-1 truncate text-left">{session.title}</span>
                )}
                <DropdownMenu onOpenChange={(open) => setMenuOpenId(open ? session.id : null)}>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      id={`sidebar-session-menu-${session.id}`}
                      onClick={(e) => e.stopPropagation()}
                      title={t('sidebar.sessionOptions')}
                      aria-label={t('sidebar.sessionOptions')}
                      className={cn(
                        "shrink-0 p-1 rounded transition-all",
                        menuOpenId === session.id ? "opacity-100" : "[@media(hover:hover)]:opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
                        theme === 'dark' ? "hover:bg-ds-zinc-700 text-ds-zinc-500 hover:text-ds-zinc-300" : "hover:bg-ds-zinc-200 text-ds-zinc-400 hover:text-ds-zinc-700",
                      )}
                    >
                      <MoreHorizontal className="w-3.5 h-3.5" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    onClick={(e) => e.stopPropagation()}
                    onCloseAutoFocus={(e) => {
                      if (!pendingRename.current) return;
                      e.preventDefault();
                      setRenaming(pendingRename.current);
                      pendingRename.current = null;
                    }}
                    className={cn("w-52", theme === 'dark' ? "bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-200" : "bg-ds-white border-ds-zinc-200 text-ds-zinc-800")}
                  >
                    {onRename && (
                      <DropdownMenuItem className={menuItemClass}
                        onClick={() => { pendingRename.current = { id: session.id, title: session.title }; }}>
                        <Pencil className="w-3.5 h-3.5" />{t('sidebar.renameSession')}
                      </DropdownMenuItem>
                    )}
                    {onTogglePin && (
                      <DropdownMenuItem className={menuItemClass} onClick={() => onTogglePin(session)}>
                        {session.is_pinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
                        {t(session.is_pinned ? 'sidebar.unpinSession' : 'sidebar.pinSession')}
                      </DropdownMenuItem>
                    )}
                    {onExport && (
                      <DropdownMenuItem className={menuItemClass} onClick={() => onExport(session.id)}>
                        <Download className="w-3.5 h-3.5" />{t('sidebar.exportSession')}
                      </DropdownMenuItem>
                    )}
                    {(onRename || onTogglePin || onExport) && <DropdownMenuSeparator className={theme === 'dark' ? "bg-ds-zinc-800" : "bg-ds-zinc-200"} />}
                    <DropdownMenuItem
                      id={`sidebar-remove-session-${session.id}`}
                      className={cn(menuItemClass, "text-ds-red-500 focus:text-ds-red-500")}
                      onClick={(e) => onRemove(session.id, e)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />{deleteSessionTitle}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
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
