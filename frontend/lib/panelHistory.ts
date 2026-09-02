export type PanelSelection = {
  selectedFile: string | null;
  selectedDoc: any | null;
  selectedEntity: any | null;
  selectedLine: number | null;
};

export type PanelHistoryEntry = {
  past: PanelSelection[];
  future: PanelSelection[];
};

export type PanelHistoryDirection = 'back' | 'forward';

export const EMPTY_PANEL_SELECTION: PanelSelection = {
  selectedFile: null,
  selectedDoc: null,
  selectedEntity: null,
  selectedLine: null,
};

export function panelSelectionsEqual(a: PanelSelection, b: PanelSelection): boolean {
  return a.selectedFile === b.selectedFile &&
    a.selectedDoc === b.selectedDoc &&
    a.selectedEntity === b.selectedEntity &&
    a.selectedLine === b.selectedLine;
}

/**
 * Add the current panel selection to its own history and clear the redo side.
 * Freeze state deliberately does not participate here: a panel's history is
 * about that panel's selection, regardless of whether it mirrors global state.
 */
export function appendPanelHistory(
  entry: PanelHistoryEntry,
  previous: PanelSelection,
  next: PanelSelection,
): PanelHistoryEntry {
  if (panelSelectionsEqual(previous, next) || (!previous.selectedFile && !previous.selectedDoc)) {
    return entry;
  }
  return { past: [...entry.past, previous], future: [] };
}

/**
 * Move one step through a panel's history. The returned transition is
 * independent of the panel's frozen/live mode; callers decide separately
 * whether the global selection should be mirrored.
 */
export function navigatePanelHistory(
  entry: PanelHistoryEntry,
  current: PanelSelection,
  direction: PanelHistoryDirection,
): { entry: PanelHistoryEntry; selection: PanelSelection } | null {
  if (direction === 'back') {
    if (entry.past.length === 0) return null;
    const selection = entry.past[entry.past.length - 1];
    return {
      selection,
      entry: { past: entry.past.slice(0, -1), future: [current, ...entry.future] },
    };
  }

  if (entry.future.length === 0) return null;
  const selection = entry.future[0];
  return {
    selection,
    entry: { past: [...entry.past, current], future: entry.future.slice(1) },
  };
}
