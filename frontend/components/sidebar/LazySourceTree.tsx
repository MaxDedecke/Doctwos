"use client";

import { api } from '@/app/services/api';
import { KnowledgeNodeIcon } from '@/components/KnowledgeNodeIcon';
import { ANALYSIS_STATUS_COLOR_TOKEN, formatAnalysisStatusTooltip } from '@/lib/analysisStatus';
import { useLanguage } from '@/lib/i18n/LanguageContext';
import { flattenLazyTree, type LazyTreeRow, type LoadedDir } from '@/lib/lazySourceTree';
import { cn } from '@/lib/utils';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, ChevronRight, Folder, Loader2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SourceScanSummary, type SourceScanSummaryData } from './SourceScanSummary';

const PAGE_SIZE = 200;
// Grobe Zeilenhöhe (py-1 + Icon); `measureElement` gleicht an die tatsächliche Höhe an.
const ESTIMATED_ROW_HEIGHT = 26;

// Geladene Seiten und aufgeklappte Ordner je Quelle bleiben beim Zuklappen erhalten (kein erneuter Abruf).
const treeCache = new Map<number, { dirs: Record<string, LoadedDir>; expanded: Set<string>; summary?: SourceScanSummaryData }>();

/** Für Tests und nach einer Neusynchronisierung. */
export function clearSourceTreeCache() {
  treeCache.clear();
}

interface LazySourceTreeProps {
  sourceId: number;
  sourceType?: string;
  selectedFile: string | null;
  onFileSelect: (path: string, sourceId: number) => void;
  theme: string;
}

/**
 * Datei-Baum einer angehefteten Wissensquelle, der nur lädt, was sichtbar wird: beim Aufklappen der Quelle
 * die erste Seite der Wurzel, beim Aufklappen eines Ordners dessen erste Seite, weitere Seiten beim
 * Herunterscrollen. Gerendert wird gefenstert (O-036), damit auch Tausende Einträge flüssig bleiben.
 */
export function LazySourceTree({ sourceId, sourceType, selectedFile, onFileSelect, theme }: LazySourceTreeProps) {
  const { t } = useLanguage();
  const cached = treeCache.get(sourceId);
  const [dirs, setDirs] = useState<Record<string, LoadedDir>>(() => cached?.dirs ?? {});
  const [expanded, setExpanded] = useState<Set<string>>(() => cached?.expanded ?? new Set());
  const [summary, setSummary] = useState<SourceScanSummaryData | undefined>(() => cached?.summary);
  useEffect(() => {
    // Nur fertige Ordner merken; ein abgebrochener Abruf würde sonst als ewiges Laden zurückkommen.
    const settled = Object.fromEntries(Object.entries(dirs).filter(([, state]) => !state.loading && !state.failed));
    treeCache.set(sourceId, { dirs: settled, expanded, summary });
  }, [dirs, expanded, summary, sourceId]);
  const inFlight = useRef(new Set<string>());
  const scrollRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (dir: string, offset: number) => {
    if (inFlight.current.has(dir)) return;
    inFlight.current.add(dir);
    setDirs(current => ({
      ...current,
      [dir]: { entries: current[dir]?.entries ?? [], total: current[dir]?.total ?? 0, nextOffset: current[dir]?.nextOffset ?? null, loading: true },
    }));
    try {
      const res = await api.getSourceTree(sourceId, { dir, offset, limit: PAGE_SIZE });
      setDirs(current => ({
        ...current,
        [dir]: {
          entries: offset === 0 ? res.data.entries : [...(current[dir]?.entries ?? []), ...res.data.entries],
          total: res.data.total,
          nextOffset: res.data.next_offset,
          loading: false,
        },
      }));
    } catch (error) {
      console.error('Failed to load source tree', error);
      setDirs(current => ({ ...current, [dir]: { ...(current[dir] ?? { entries: [], total: 0, nextOffset: null }), loading: false, failed: true } }));
    } finally {
      inFlight.current.delete(dir);
    }
  }, [sourceId]);

  useEffect(() => {
    if (treeCache.get(sourceId)?.dirs['']) return;
    void load('', 0);
    api.getSourceScanSummary(sourceId).then(res => setSummary(res.data)).catch(() => undefined);
  }, [load, sourceId]);

  const toggleDir = (path: string) => {
    setExpanded(current => {
      const next = new Set(current);
      if (!next.delete(path)) next.add(path);
      return next;
    });
    if (!dirs[path]) void load(path, 0);
  };

  const rows = useMemo(() => flattenLazyTree(dirs, expanded), [dirs, expanded]);
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 12,
  });

  // Ist eine „mehr“-Zeile im Blick, die nächste Seite dieses Ordners holen.
  const visibleMore = virtualizer.getVirtualItems()
    .map(item => rows[item.index])
    .filter((row): row is Extract<LazyTreeRow, { kind: 'more' }> => row?.kind === 'more' && !row.loading);
  const moreKey = visibleMore.map(row => `${row.dir}:${row.loaded}`).join('|');
  useEffect(() => {
    for (const row of visibleMore) {
      const next = dirs[row.dir]?.nextOffset;
      if (next != null) void load(row.dir, next);
    }
    // moreKey fasst die sichtbaren „mehr“-Zeilen zusammen; die Liste selbst ist bei jedem Rendern neu.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moreKey]);

  const root = dirs[''];
  if (root && !root.loading && root.entries.length === 0) {
    return (
      <div className="text-[0.625rem] text-ds-zinc-500 italic px-2 py-3 text-center">
        {root.failed ? t('sidebar.filesLoadFailed') : t('sidebar.noFiles')}
      </div>
    );
  }

  const rowClass = theme === 'dark'
    ? "text-ds-zinc-400 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-200"
    : "text-ds-zinc-650 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-850";

  const renderRow = (row: LazyTreeRow) => {
    if (row.kind === 'loading' || (row.kind === 'more' && row.loading)) {
      return (
        <div className="flex items-center gap-1.5 py-1 text-[0.625rem] text-ds-zinc-500" style={{ paddingLeft: `${Math.max(8, row.depth * 12 + 14)}px` }}>
          <Loader2 className="w-3 h-3 animate-spin" />
          <span>{t('sidebar.loadingFiles')}</span>
        </div>
      );
    }
    if (row.kind === 'more') {
      return (
        <button type="button" onClick={() => { const next = dirs[row.dir]?.nextOffset; if (next != null) void load(row.dir, next); }}
          className={cn("w-full py-1 rounded text-left text-[0.625rem] font-semibold text-ds-indigo-500 hover:underline")}
          style={{ paddingLeft: `${Math.max(8, row.depth * 12 + 14)}px` }}>
          {t('sidebar.loadMoreFiles', { loaded: row.loaded, total: row.total })}
        </button>
      );
    }
    const { entry, depth } = row;
    if (entry.type === 'dir') {
      return (
        <button
          type="button"
          onClick={() => toggleDir(entry.path)}
          aria-expanded={row.expanded}
          className={cn("w-full flex items-center gap-1.5 px-2 py-1 rounded text-[0.6875rem] font-semibold transition-all text-left", rowClass)}
          style={{ paddingLeft: `${Math.max(8, depth * 12)}px` }}
        >
          <span className="w-3.5 h-3.5 flex items-center justify-center shrink-0">
            {row.expanded ? <ChevronDown className="w-3.5 h-3.5 text-ds-zinc-500" /> : <ChevronRight className="w-3.5 h-3.5 text-ds-zinc-500" />}
          </span>
          <Folder className="w-3.5 h-3.5 shrink-0 opacity-70 text-ds-indigo-500" />
          <span className="truncate flex-1 min-w-0 font-sans">{entry.name}</span>
          <span className="shrink-0 pr-1 text-[0.5625rem] font-mono text-ds-zinc-500">{entry.files}</span>
        </button>
      );
    }
    const isSelected = selectedFile === entry.path;
    const title = entry.status ? `${entry.path}\n${formatAnalysisStatusTooltip(entry.status, t)}` : entry.path;
    return (
      <button
        type="button"
        onClick={() => onFileSelect(entry.path, sourceId)}
        className={cn(
          "w-full flex items-center gap-2 py-1 rounded text-[0.6875rem] transition-all text-left",
          isSelected
            ? (theme === 'dark' ? "bg-ds-indigo-500/10 text-ds-indigo-400 font-semibold" : "bg-ds-indigo-55 text-ds-indigo-750 font-semibold")
            : (theme === 'dark' ? "text-ds-zinc-500 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-300" : "text-ds-zinc-550 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-800")
        )}
        style={{ paddingLeft: `${Math.max(8, depth * 12 + 14)}px` }}
        title={title}
      >
        <KnowledgeNodeIcon node={{ type: 'document', source_type: sourceType }} className="w-3 h-3 shrink-0 opacity-70" />
        <span className="truncate flex-1 min-w-0 font-mono">{entry.name}</span>
        {entry.status && (
          <span data-testid="analysis-status-dot" className="w-1.5 h-1.5 rounded-full shrink-0 mr-1.5"
            style={{ backgroundColor: ANALYSIS_STATUS_COLOR_TOKEN[entry.status.status] }} />
        )}
      </button>
    );
  };

  return (
    <>
      <SourceScanSummary summary={summary} theme={theme} />
      <div ref={scrollRef} className="max-h-[300px] overflow-y-auto pr-1">
        <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const row = rows[virtualRow.index];
            const key = row.kind === 'entry' ? row.entry.path : `${row.kind}:${row.dir}`;
            return (
              <div key={key} data-index={virtualRow.index} ref={virtualizer.measureElement}
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${virtualRow.start}px)` }}>
                {renderRow(row)}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
