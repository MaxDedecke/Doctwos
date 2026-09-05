"use client";

import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { MessageSquare, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

// Grobe Zeilenhöhe (px-3 py-2 + Icon) -- vom Virtualizer nur als Startschätzung
// gebraucht, `measureElement` gleicht danach an die tatsächliche Höhe an.
const ESTIMATED_ROW_HEIGHT = 40;

export interface SidebarSession {
  id: number;
  title: string;
  [key: string]: unknown;
}

interface VirtualizedSessionListProps {
  sessions: SidebarSession[];
  activeSessionId: number | null;
  theme: string;
  onSelect: (session: SidebarSession) => void;
  onRemove: (id: number, e: React.MouseEvent) => void;
  deleteSessionTitle: string;
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
}: VirtualizedSessionListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: sessions.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 8,
  });

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
    </div>
  );
}
