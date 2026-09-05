"use client";

import { useMemo, useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, ChevronRight, Folder } from 'lucide-react';
import { cn } from '@/lib/utils';
import { KnowledgeNodeIcon } from '@/components/KnowledgeNodeIcon';
import { buildFileTree, flattenVisibleFileTree, type FlatTreeRow } from '@/lib/sidebarFileTree';

// Grobe Zeilenhöhe (py-1 + Icon) -- nur Startschätzung für den Virtualizer,
// `measureElement` gleicht danach an die tatsächliche Höhe an.
const ESTIMATED_ROW_HEIGHT = 26;

interface FileTreeListProps {
  filesList: string[];
  sourceId: number;
  sourceType?: string;
  selectedFile: string | null;
  collapsedFolders: Record<string, boolean>;
  toggleFolder: (path: string) => void;
  onFileSelect: (path: string, sourceId: number) => void;
  theme: string;
}

/**
 * O-036: der Datei-Baum einer Wissensquelle wird gefenstert gerendert statt
 * rekursiv voll ausgeklappt -- bei einem großen COBOL-Bestand (Ziel laut
 * CLAUDE.md Prinzip 4: 100-GB-Monorepos) wären das sonst zehntausende DOM-
 * Knoten gleichzeitig. Der Baum wird dafür vorab auf die aktuell sichtbaren
 * Zeilen abgeflacht (`flattenVisibleFileTree` -- Kinder eingeklappter Ordner
 * fehlen dort schlicht), der Virtualizer kennt danach nur noch eine flache,
 * indexierbare Liste.
 */
export function FileTreeList({
  filesList,
  sourceId,
  sourceType,
  selectedFile,
  collapsedFolders,
  toggleFolder,
  onFileSelect,
  theme,
}: FileTreeListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const rows = useMemo(
    () => flattenVisibleFileTree(buildFileTree(filesList), collapsedFolders),
    [filesList, collapsedFolders]
  );

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ESTIMATED_ROW_HEIGHT,
    overscan: 12,
  });

  const renderRow = (row: FlatTreeRow) => {
    const { node, depth } = row;
    if (node.type === 'folder') {
      const isCollapsed = !!collapsedFolders[node.path];
      return (
        <button
          type="button"
          onClick={() => toggleFolder(node.path)}
          className={cn(
            "w-full flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-semibold transition-all text-left",
            theme === 'dark' ? "text-ds-zinc-400 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-200" : "text-ds-zinc-650 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-850"
          )}
          style={{ paddingLeft: `${Math.max(8, depth * 12)}px` }}
        >
          <span className="w-3.5 h-3.5 flex items-center justify-center shrink-0">
            {isCollapsed ? (
              <ChevronRight className="w-3.5 h-3.5 text-ds-zinc-500" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5 text-ds-zinc-500" />
            )}
          </span>
          <Folder className="w-3.5 h-3.5 shrink-0 opacity-70 text-ds-indigo-500" />
          <span className="truncate flex-1 min-w-0 font-sans">{node.name}</span>
        </button>
      );
    }

    const isFileSelected = selectedFile === node.path;
    return (
      <button
        type="button"
        onClick={() => onFileSelect(node.path, sourceId)}
        className={cn(
          "w-full flex items-center gap-2 py-1 rounded text-[11px] transition-all text-left",
          isFileSelected
            ? (theme === 'dark' ? "bg-ds-indigo-500/10 text-ds-indigo-400 font-semibold" : "bg-ds-indigo-55 text-ds-indigo-750 font-semibold")
            : (theme === 'dark' ? "text-ds-zinc-500 hover:bg-ds-zinc-800/40 hover:text-ds-zinc-300" : "text-ds-zinc-550 hover:bg-ds-zinc-200/55 hover:text-ds-zinc-800")
        )}
        style={{ paddingLeft: `${Math.max(8, depth * 12 + 14)}px` }}
        title={node.path}
      >
        <KnowledgeNodeIcon
          node={{ type: 'document', source_type: sourceType }}
          className="w-3 h-3 shrink-0 opacity-70"
        />
        <span className="truncate flex-1 min-w-0 font-mono">{node.name}</span>
      </button>
    );
  };

  return (
    <div ref={scrollRef} className="max-h-[300px] overflow-y-auto pr-1">
      <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const row = rows[virtualRow.index];
          return (
            <div
              key={row.node.path}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              {renderRow(row)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
