import type { AnalysisStatusInfo } from '@/lib/analysisStatus';

/** Ein direkter Eintrag eines Ordners einer Wissensquelle (Backend: services/source_tree.py). */
export type SourceTreeEntry =
  | { type: 'dir'; name: string; path: string; files: number }
  | { type: 'file'; name: string; path: string; status?: AnalysisStatusInfo };

export interface SourceTreePage {
  dir: string;
  entries: SourceTreeEntry[];
  total: number;
  next_offset: number | null;
}

/** Geladener Stand eines Ordners: bisher geladene Einträge und wo es weitergeht. */
export interface LoadedDir {
  entries: SourceTreeEntry[];
  total: number;
  nextOffset: number | null;
  loading: boolean;
  failed?: boolean;
}

export type LazyTreeRow =
  | { kind: 'entry'; entry: SourceTreeEntry; depth: number; expanded: boolean }
  | { kind: 'loading'; dir: string; depth: number }
  | { kind: 'more'; dir: string; depth: number; loaded: number; total: number; loading: boolean };

/**
 * Sichtbare Zeilen des Baums: Einträge geladener Ordner, Kinder nur unter aufgeklappten Ordnern, je Ordner
 * eine Ladezeile (erste Seite) oder eine „mehr“-Zeile (weitere Seiten).
 */
export function flattenLazyTree(dirs: Record<string, LoadedDir>, expanded: ReadonlySet<string>, dir = '', depth = 0): LazyTreeRow[] {
  const state = dirs[dir];
  if (!state || (state.loading && state.entries.length === 0)) return [{ kind: 'loading', dir, depth }];
  const rows: LazyTreeRow[] = [];
  for (const entry of state.entries) {
    const isOpen = entry.type === 'dir' && expanded.has(entry.path);
    rows.push({ kind: 'entry', entry, depth, expanded: isOpen });
    if (isOpen) rows.push(...flattenLazyTree(dirs, expanded, entry.path, depth + 1));
  }
  if (state.nextOffset != null) {
    rows.push({ kind: 'more', dir, depth, loaded: state.entries.length, total: state.total, loading: state.loading });
  }
  return rows;
}
