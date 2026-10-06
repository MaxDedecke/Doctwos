"use client";

import { Button } from '@/components/ui/button';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import React, { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';

// Indizierungslogs wachsen ohne Obergrenze (mehrere hundert KB bei großen Quellen).
// Der Viewer zeigt deshalb zuerst nur das Ende und lädt ältere Zeilen blockweise
// nach oben nach — per Button oder automatisch beim Hochscrollen.
export const SYNC_LOG_PAGE_LINES = 200;
const EDGE_PX = 24;

interface SyncLogViewerProps {
  log: string | null | undefined;
}

/** Nach Quellenwechsel mit `key={source.id}` neu mounten, damit das Fenster zurückgesetzt wird. */
export const SyncLogViewer: React.FC<SyncLogViewerProps> = ({ log }) => {
  const { t } = useLanguage();
  // null = dem Ende folgen (letzte SYNC_LOG_PAGE_LINES Zeilen); sonst fester Startindex,
  // damit nachgeladene Zeilen beim Anwachsen des Logs nicht wieder oben herausfallen.
  const [loadedFrom, setLoadedFrom] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const restoreHeightRef = useRef<number | null>(null);

  const lines = useMemo(() => (log ? log.split('\n').filter(Boolean) : []), [log]);
  const tailStart = Math.max(0, lines.length - SYNC_LOG_PAGE_LINES);
  // Wurde das Log neu gestartet und ist kürzer als der gemerkte Start, wieder dem Ende folgen.
  const firstShown = loadedFrom !== null && loadedFrom < lines.length ? loadedFrom : tailStart;
  const text = useMemo(() => lines.slice(firstShown).join('\n'), [lines, firstShown]);
  const hiddenCount = firstShown;

  const loadOlder = useCallback(() => {
    const element = scrollRef.current;
    restoreHeightRef.current = element ? element.scrollHeight : null;
    setLoadedFrom(Math.max(0, firstShown - SYNC_LOG_PAGE_LINES));
  }, [firstShown]);

  // Nach dem Nachladen die Leseposition halten (neue Zeilen stehen oberhalb);
  // sonst dem Ende folgen, solange der Nutzer dort steht.
  useLayoutEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    if (restoreHeightRef.current !== null) {
      element.scrollTop += element.scrollHeight - restoreHeightRef.current;
      restoreHeightRef.current = null;
    } else if (stickToBottomRef.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [text]);

  const handleScroll = () => {
    const element = scrollRef.current;
    if (!element) return;
    stickToBottomRef.current = element.scrollHeight - element.scrollTop - element.clientHeight <= EDGE_PX;
    if (element.scrollTop <= EDGE_PX && hiddenCount > 0) loadOlder();
  };

  if (lines.length === 0) {
    return (
      <div className="p-4 rounded-lg border font-mono text-[0.625rem] leading-relaxed whitespace-pre-wrap bg-ds-zinc-950 text-ds-zinc-300 border-ds-zinc-800">
        {t('settings.logsTab.noLogsPlaceholder')}
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col rounded-lg border bg-ds-zinc-950 border-ds-zinc-800 overflow-hidden" data-testid="sync-log-viewer">
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-ds-zinc-800 px-3 py-1.5 text-[0.625rem] text-ds-zinc-500">
        <span data-testid="sync-log-range">{t('settings.logsTab.logRange', { from: firstShown + 1, to: lines.length, total: lines.length })}</span>
        {hiddenCount > 0 && (
          <Button type="button" size="sm" variant="outline" onClick={loadOlder}
            className="h-6 px-2 text-[0.625rem] bg-ds-zinc-900 border-ds-zinc-800 text-ds-zinc-300 hover:bg-ds-zinc-800 focus:ring-0">
            {t('settings.logsTab.loadOlder', { count: Math.min(hiddenCount, SYNC_LOG_PAGE_LINES) })}
          </Button>
        )}
      </div>
      <div ref={scrollRef} onScroll={handleScroll} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4 font-mono text-[0.625rem] leading-relaxed text-ds-zinc-300" data-testid="sync-log-scroll">
        <pre className="whitespace-pre-wrap break-words font-mono">{text}</pre>
      </div>
    </div>
  );
};
