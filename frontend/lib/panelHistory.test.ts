import { describe, expect, it } from 'vitest';
import {
  appendPanelHistory,
  EMPTY_PANEL_SELECTION,
  navigatePanelHistory,
  type PanelSelection,
} from './panelHistory';

const selection = (file: string, line = 1): PanelSelection => ({
  selectedFile: file,
  selectedDoc: null,
  selectedEntity: null,
  selectedLine: line,
});

describe('panel history', () => {
  it('keeps a fixed panel history independent of freeze state', () => {
    const a = selection('a.cbl');
    const b = selection('b.cbl');
    const entry = appendPanelHistory({ past: [], future: [] }, a, b);

    expect(navigatePanelHistory(entry, b, 'back')).toEqual({
      selection: a,
      entry: { past: [], future: [b] },
    });
  });

  it('supports forward navigation and clears redo after a new selection', () => {
    const a = selection('a.cbl');
    const b = selection('b.cbl');
    const c = selection('c.cbl');
    const history = appendPanelHistory({ past: [], future: [] }, a, b);
    const back = navigatePanelHistory(history, b, 'back');
    expect(back).not.toBeNull();
    const forward = navigatePanelHistory(back!.entry, a, 'forward');
    expect(forward).toEqual({
      selection: b,
      entry: { past: [a], future: [] },
    });
    expect(appendPanelHistory(back!.entry, a, c)).toEqual({ past: [a], future: [] });
  });

  it('does not create history for an empty or unchanged selection', () => {
    const empty = { past: [], future: [] };
    expect(appendPanelHistory(empty, EMPTY_PANEL_SELECTION, selection('a.cbl'))).toEqual(empty);
    const a = selection('a.cbl');
    expect(appendPanelHistory(empty, a, a)).toEqual(empty);
  });
});
