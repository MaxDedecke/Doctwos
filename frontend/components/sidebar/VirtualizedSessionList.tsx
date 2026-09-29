"use client";

import { cn } from '@/lib/utils';
import { useVirtualizer } from '@tanstack/react-virtual';
import { MessageSquare, Trash2 } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';

// Grobe Zeilenhöhe (px-3 py-2 + Icon) -- vom Virtualizer nur als Startschätzung
// gebraucht, `measureElement` gleicht danach an die tatsächliche Höhe an.
const ESTIMATED_ROW_HEIGHT = 40;

// Ab so vielen Zeilen vor dem Listenende wird die nächste Seite nachgeladen.
const LOAD_MORE_THRESHOLD = 6;

export interface SidebarSession {
  id: number;
  title: string;

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
}: VirtualizedSessionListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

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
                <MessageSquare className="w-3.5 h-3.5 text-ds-zinc-500 shrink-0" />
                <span className="truncate text-left flex-1">{session.title}</span>
                <button
                  type="button"
                  onClick={(e) => onRemove(session.id, e)}
                  id={`sidebar-remove-session-${session.id}`}
                  className={cn(
                    "absolute right-2 p-1 rounded opacity-0 group-hover:opacity-100 transition-all",
                    theme === 'dark' ? "hover:bg-ds-zinc-700 text-ds-zinc-600 hover:text-ds-zinc-400" : "hover:bg-ds-zinc-200 text-ds-zinc-400 hover:text-ds-zinc-600"
                  )}
                  title={deleteSessionTitle}
                >
                  <Trash2 className="w-3 h-3" />
                </button>
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
