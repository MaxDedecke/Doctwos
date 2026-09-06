/**
 * O-092 — Regressionstests zur Soll-Matrix der Panel-Synchronisation.
 *
 * Die fachliche Festlegung steht in `docs/PANEL_SYNCHRONISATION.md`; jeder Test
 * hier trägt die ID der Matrixzeile (PS-nn), die er absichert. Bewusst NICHT
 * getestet sind die Zeilen, deren Soll noch als offene Entscheidung (D-1 bis
 * D-6) geführt wird — sie stehen als `it.todo` drin, damit sie sichtbar offen
 * bleiben, statt den Ist-Zustand stillschweigend zu zementieren.
 *
 * Der Zuschnitt folgt den zwei Navigationspfaden aus der Doku:
 *   Pfad A (global)      — globale Auswahl + ensurePanelType, danach greift die
 *                          Render-Synchronisation in useWorkspaceLayout.
 *   Pfad B (panel-lokal) — usePanelNavigation::handlePanelFileSelect mit
 *                          Zielauflösung über lib/panelNavigation.
 */
import { act, renderHook } from '@testing-library/react';
import { useRef, useState } from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { useWorkspaceLayout, type PinnedCode } from './useWorkspaceLayout';
import { usePanelNavigation } from './usePanelNavigation';
import { api } from '@/app/services/api';
import type { PanelHistoryEntry, PanelSelection } from '@/lib/panelHistory';

vi.mock('@/app/services/api', () => ({
  api: {
    resolveEntity: vi.fn(),
    updateChatSessionSnapshot: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

const EMPTY: PanelSelection = { selectedFile: null, selectedDoc: null, selectedEntity: null, selectedLine: null };

// ── Pfad A ───────────────────────────────────────────────────────────────────
// page.tsx::handleFileSelect macht nach dem Laden genau zwei Dinge, die für die
// Synchronisation zählen: globale Auswahl setzen und ensurePanelType() rufen.
// Genau diese Sequenz wird hier gefahren, ohne den I/O-Teil der Seite.

function renderLayout() {
  return renderHook(() => useWorkspaceLayout({
    activeSessionId: null,
    selectedProject: null,
    selectedSource: null,
    t: (key: string) => key,
  }));
}

describe('Pfad A — globale Navigation (Sidebar, globale Suche)', () => {
  it('PS-01: ein offenes Live-Panel des Zieltyps übernimmt die globale Auswahl', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.setSelectedFile('app/main.cbl'); });

    expect(result.current.panelConfigs).toEqual(['chat', 'code']);
    expect(result.current.panelSelections[1].selectedFile).toBe('app/main.cbl');
  });

  it('PS-02: ein im selben Zug neu geöffnetes Panel korrigiert seine Startauswahl auf die aktuelle', () => {
    const { result } = renderLayout();

    // addPanel liest die globale Auswahl aus dem laufenden Render -- zum
    // Zeitpunkt des Aufrufs also noch die alte. Dass das Panel trotzdem die
    // neue Datei zeigt, leistet erst die Render-Synchronisation; deshalb ist
    // dieser Fall eigens abgesichert und nicht bloß Nebeneffekt.
    act(() => {
      result.current.setSelectedFile('app/main.cbl');
      result.current.ensurePanelType('code');
    });

    expect(result.current.panelConfigs).toEqual(['chat', 'code']);
    expect(result.current.panelSelections[1].selectedFile).toBe('app/main.cbl');
  });

  it('PS-03: ein nur eingefrorenes Panel des Zieltyps gilt nicht als vorhanden -- es wird ein Live-Panel geöffnet (D-1)', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.togglePanelFreeze(1); });
    act(() => {
      result.current.setSelectedFile('app/main.cbl');
      result.current.ensureLivePanelType('code');
    });

    expect(result.current.panelConfigs).toEqual(['chat', 'code', 'code']);
    expect(result.current.panelFrozen).toEqual([false, true, false]);
    // Das eingefrorene Panel bleibt unberührt, das neue zeigt die Auswahl.
    expect(result.current.panelSelections[1].selectedFile).toBeNull();
    expect(result.current.panelSelections[2].selectedFile).toBe('app/main.cbl');
  });

  it('PS-03: ensurePanelType (Chat-Pin) zählt ein eingefrorenes Panel weiterhin als vorhanden (PS-20)', () => {
    const { result } = renderLayout();

    act(() => { result.current.togglePanelFreeze(0); });
    act(() => { result.current.ensurePanelType('chat'); });

    expect(result.current.panelConfigs).toEqual(['chat']);
  });

  it('PS-04: die Obergrenze von vier Panels hält, ein fünftes entsteht nicht', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.addPanel('doc'); });
    act(() => { result.current.addPanel('graph'); });
    act(() => { result.current.addPanel('callgraph'); });

    expect(result.current.panelConfigs).toEqual(['chat', 'code', 'doc', 'graph']);
    expect(result.current.layoutMode).toBe('4-grid');
  });

  it('PS-04: an der 4-Panel-Grenze meldet ensureLivePanelType den Fehlschlag zurück, statt still zu scheitern (D-2)', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.addPanel('doc'); });
    act(() => { result.current.addPanel('graph'); });

    let opened: boolean | undefined;
    act(() => { opened = result.current.ensureLivePanelType('callgraph'); });

    expect(opened).toBe(false);
    expect(result.current.panelConfigs).toEqual(['chat', 'code', 'doc', 'graph']);
  });

  it('PS-22: ein eingefrorenes Panel folgt der globalen Auswahl nicht mehr', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.setSelectedFile('app/first.cbl'); });
    act(() => { result.current.togglePanelFreeze(1); });
    act(() => { result.current.setSelectedFile('app/second.cbl'); });

    expect(result.current.panelFrozen[1]).toBe(true);
    expect(result.current.panelSelections[1].selectedFile).toBe('app/first.cbl');
    expect(result.current.panelSelections[0].selectedFile).toBe('app/second.cbl');
  });

  // PS-23: togglePanelFreeze setzt beim Auftauen `selectedLine: null` -- was wie
  // ein verlorener Zeilensprung aussieht. Tatsächlich läuft direkt danach die
  // Render-Synchronisation (panelFrozen hat eine neue Identität) und schreibt die
  // globale Zeile zurück. Das `null` ist also redundant, nicht schädlich; dieser
  // Test hält fest, dass die Zeile beim Auftauen ankommt -- egal über welchen der
  // beiden Schritte.
  it('PS-23: das Auftauen übernimmt die globale Auswahl samt Zeile', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.togglePanelFreeze(1); });
    act(() => {
      result.current.setSelectedFile('app/main.cbl');
      result.current.setSelectedLine(42);
    });
    act(() => { result.current.togglePanelFreeze(1); });

    expect(result.current.panelSelections[1].selectedFile).toBe('app/main.cbl');
    expect(result.current.panelSelections[1].selectedLine).toBe(42);
  });

  it.todo('PS-25: zieht die Historie eines Live-Panels die anderen mit? -- siehe D-4');

  it('PS-26: die Historie eines eingefrorenen Panels bleibt lokal', () => {
    const { result } = renderLayout();
    const older: PanelSelection = { selectedFile: 'app/older.cbl', selectedDoc: null, selectedEntity: null, selectedLine: null };

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.setSelectedFile('app/current.cbl'); });
    act(() => { result.current.togglePanelFreeze(1); });
    act(() => {
      result.current.setPanelHistory((previous) => {
        const next = [...previous];
        next[1] = { past: [older], future: [] };
        return next;
      });
    });
    act(() => { result.current.goBackPanel(1); });

    expect(result.current.panelSelections[1].selectedFile).toBe('app/older.cbl');
    expect(result.current.selectedFile).toBe('app/current.cbl');
  });

  it('PS-27: der Typwechsel im Panel-Kopf leert die Panel-Historie und holt die passende globale Auswahl', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('doc'); });
    act(() => { result.current.setSelectedFile('app/main.cbl'); });

    // Ein doc-Panel synchronisiert eine Code-Auswahl nicht ...
    expect(result.current.panelSelections[1].selectedFile).toBeNull();

    act(() => {
      result.current.setPanelConfigs((previous) => {
        const next = [...previous];
        next[1] = 'code';
        return next;
      });
    });

    // ... nach dem Typwechsel zieht es sie nach.
    expect(result.current.panelSelections[1].selectedFile).toBe('app/main.cbl');
  });

  it('PS-28: das Schließen eines Panels lässt die globale Auswahl bestehen', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('code'); });
    act(() => { result.current.setSelectedFile('app/main.cbl'); });
    act(() => { result.current.closePanel(1); });

    expect(result.current.panelConfigs).toEqual(['chat']);
    expect(result.current.panelSelections).toHaveLength(1);
    expect(result.current.selectedFile).toBe('app/main.cbl');
  });
  it('PS-29: der Call-Graph behält seinen Objektfokus, wenn anderswo ein Dokument geöffnet wird (D-3)', () => {
    const { result } = renderLayout();
    const entity = { id: 5, name: 'CBACT01C', type: 'program', file_path: 'SRC/CBACT01C.cbl', start_line: 40 };

    act(() => { result.current.addPanel('callgraph'); });
    act(() => {
      result.current.setSelectedFile('SRC/CBACT01C.cbl');
      result.current.setSelectedEntity(entity);
    });

    expect(result.current.panelSelections[1].selectedEntity).toEqual(entity);

    act(() => {
      result.current.setSelectedFile(null);
      result.current.setSelectedEntity(null);
      result.current.setSelectedDoc({ id: 8, name: 'handbuch.pdf' });
    });

    expect(result.current.panelSelections[1].selectedEntity).toEqual(entity);
    // Das Chat-Panel folgt der Dokumentauswahl wie bisher.
    expect(result.current.panelSelections[0].selectedDoc).toEqual({ id: 8, name: 'handbuch.pdf' });
  });


  it('PS-30: ein Link-Manager-Panel synchronisiert keine Datei-Auswahl', () => {
    const { result } = renderLayout();

    act(() => { result.current.addPanel('linkmanager'); });
    act(() => { result.current.setSelectedFile('app/main.cbl'); });

    expect(result.current.panelSelections[1]).toMatchObject({ selectedFile: null, selectedDoc: null });
  });
});

// ── Pfad B ───────────────────────────────────────────────────────────────────

type HarnessOptions = {
  panelConfigs?: string[];
  panelFrozen?: boolean[];
  panelSelections?: PanelSelection[];
  connectedSources?: any[];
  projectEntities?: any[];
};

function useNavigationHarness(options: HarnessOptions = {}) {
  const [panelSelections, setPanelSelections] = useState<PanelSelection[]>(
    options.panelSelections ?? (options.panelConfigs ?? ['chat']).map(() => EMPTY)
  );
  const [panelHistory, setPanelHistory] = useState<PanelHistoryEntry[]>(
    (options.panelConfigs ?? ['chat']).map(() => ({ past: [], future: [] }))
  );
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<any | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<any | null>(null);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [pinnedCode, setPinnedCode] = useState<PinnedCode | null>(null);
  const [activeMobileTab, setActiveMobileTab] = useState<'chat' | 'editor' | 'graph'>('chat');
  const isPanelHistoryNavRef = useRef(false);
  const isEditorNavigatingRef = useRef(false);
  const [addPanel] = useState(() => vi.fn().mockReturnValue(true));
  const [ensurePanelType] = useState(() => vi.fn().mockReturnValue(true));
  const [ensureLivePanelType] = useState(() => vi.fn().mockReturnValue(true));
  const [showToast] = useState(() => vi.fn());
  const [handleFileSelect] = useState(() => vi.fn().mockResolvedValue(undefined));
  const [loadFileReferences] = useState(() => vi.fn().mockResolvedValue(undefined));
  const [updatePanelEntitySelection] = useState(() => vi.fn());
  const [setPanelFocusObject] = useState(() => vi.fn());

  const navigation = usePanelNavigation({
    t: (key) => key,
    showToast,
    selectedProject: { id: 11, name: 'Demo' },
    selectedSource: null,
    connectedSources: options.connectedSources ?? [],
    projectEntities: options.projectEntities ?? [],
    panelConfigs: options.panelConfigs ?? ['chat'],
    panelFrozen: options.panelFrozen ?? (options.panelConfigs ?? ['chat']).map(() => false),
    panelSelections,
    fileNavStack: [],
    setPinnedCode,
    setPanelFocusObject,
    setPanelSelections,
    setPanelHistory,
    setActiveMobileTab,
    setSelectedDoc,
    setSelectedFile,
    setSelectedEntity,
    setSelectedLine,
    setFileNavStack: vi.fn(),
    setIsEditorMaximized: vi.fn(),
    isPanelHistoryNavRef,
    isEditorNavigatingRef,
    addPanel,
    ensurePanelType,
    ensureLivePanelType,
    updatePanelEntitySelection,
    handleFileSelect,
    loadFileReferences,
  });

  return {
    navigation, addPanel, ensurePanelType, ensureLivePanelType, showToast, updatePanelEntitySelection, handleFileSelect,
    panelSelections, panelHistory, selectedFile, selectedDoc, selectedEntity, selectedLine,
    pinnedCode, activeMobileTab,
  };
}

describe('Pfad B — panel-lokale Navigation (Chat, Editor, Graph, Call-Graph)', () => {
  beforeEach(() => {
    vi.mocked(api.resolveEntity).mockResolvedValue({ data: null } as any);
  });

  it('PS-05: ein Verweis aus dem Chat landet im offenen Live-Code-Panel und in der globalen Auswahl', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat', 'code'] }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(0, 'app/main.cbl', 12); });

    expect(result.current.addPanel).not.toHaveBeenCalled();
    expect(result.current.selectedFile).toBe('app/main.cbl');
    expect(result.current.selectedLine).toBe(12);
    expect(result.current.panelSelections[1].selectedLine).toBe(12);
    expect(result.current.activeMobileTab).toBe('editor');
  });

  it('PS-06: ein Verweis im Code-Panel selbst bleibt in diesem Panel', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat', 'code'] }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(1, 'app/other.cbl', 3); });

    expect(result.current.addPanel).not.toHaveBeenCalled();
    expect(result.current.selectedFile).toBe('app/other.cbl');
  });

  it('PS-07: im eingefrorenen Panel selbst navigiert der Klick lokal und schreibt Historie', async () => {
    const previous: PanelSelection = { selectedFile: 'app/first.cbl', selectedDoc: null, selectedEntity: null, selectedLine: 1 };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat', 'code'],
      panelFrozen: [false, true],
      panelSelections: [EMPTY, previous],
    }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(1, 'app/second.cbl', 7); });

    expect(result.current.panelSelections[1].selectedFile).toBe('app/second.cbl');
    expect(result.current.selectedFile).toBeNull();
    expect(result.current.panelHistory[1].past).toEqual([previous]);
  });

  it('PS-08: ein Verweis aus dem Chat überschreibt ein eingefrorenes Code-Panel nicht mehr, sondern öffnet ein eigenes (D-1)', async () => {
    const frozen: PanelSelection = { selectedFile: 'app/frozen.cbl', selectedDoc: null, selectedEntity: null, selectedLine: null };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat', 'code'],
      panelFrozen: [false, true],
      panelSelections: [EMPTY, frozen],
    }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(0, 'app/target.cbl', 5); });

    expect(result.current.addPanel).toHaveBeenCalledWith('code', expect.objectContaining({ selectedFile: 'app/target.cbl' }), false);
    expect(result.current.panelSelections[1]).toEqual(frozen);
    expect(result.current.selectedFile).toBeNull();
  });

  it('PS-09: der Call-Graph überschreibt ein eingefrorenes Code-Panel nicht, sondern öffnet ein eigenes', async () => {
    const frozen: PanelSelection = { selectedFile: 'app/frozen.cbl', selectedDoc: null, selectedEntity: null, selectedLine: null };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['callgraph', 'code'],
      panelFrozen: [false, true],
      panelSelections: [EMPTY, frozen],
    }));

    await act(async () => {
      // Signatur wie in PanelContentRenderer (callgraph-Zweig): openIfMissing=true.
      // Der frühere Sonderparameter preserveFrozenTarget ist mit D-1 entfallen --
      // kein Pfad zielt mehr auf ein eingefrorenes Panel.
      await result.current.navigation.handlePanelFileSelect(0, 'app/target.cbl', 5, null, true);
    });

    expect(result.current.addPanel).toHaveBeenCalledWith('code', expect.objectContaining({ selectedFile: 'app/target.cbl' }), false);
    expect(result.current.panelSelections[1]).toEqual(frozen);
  });

  it('PS-10: fehlt das Zielpanel, öffnet openIfMissing=true ein neues Live-Panel', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat'] }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(0, 'app/main.cbl', 9); });

    expect(result.current.addPanel).toHaveBeenCalledWith('code', {
      selectedFile: 'app/main.cbl',
      selectedDoc: null,
      selectedEntity: null,
      selectedLine: 9,
    }, false);
  });

  it('PS-11: der Graph-Einfachklick stupst nur an -- ohne passendes Panel passiert nichts', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat', 'graph'] }));

    await act(async () => {
      await result.current.navigation.handlePanelFileSelect(1, 'app/main.cbl', 4, null, false);
    });

    expect(result.current.addPanel).not.toHaveBeenCalled();
    expect(result.current.selectedFile).toBeNull();
  });

  it('PS-12: bei vier offenen Panels ohne passenden Typ bleibt die Navigation wirkungslos', async () => {
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat', 'graph', 'callgraph', 'linkmanager'],
    }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(0, 'app/main.cbl', 2); });

    expect(result.current.addPanel).not.toHaveBeenCalled();
    expect(result.current.selectedFile).toBeNull();
    // D-2: der Klick verpufft nicht mehr kommentarlos.
    expect(result.current.showToast).toHaveBeenCalledWith('page.toast.noPanelSpace', 'error');
  });

  it('PS-11/PS-12: der bewusste "nur anstupsen"-Fall bleibt still', async () => {
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat', 'graph'] }));

    await act(async () => {
      await result.current.navigation.handlePanelFileSelect(1, 'app/main.cbl', 4, null, false);
    });

    expect(result.current.showToast).not.toHaveBeenCalled();
  });

  it('PS-13: eine Dokumentendung landet im doc-Panel', async () => {
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat'],
      connectedSources: [{ id: 8, type: 'local', name: 'handbuch.pdf' }],
    }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(0, 'handbuch.pdf', null, 8); });

    expect(result.current.addPanel).toHaveBeenCalledWith('doc', expect.objectContaining({
      selectedDoc: { id: 8, name: 'handbuch.pdf' },
    }), false);
  });

  it('PS-14: eine Confluence-Quelle landet unabhängig von der Endung im webview-Panel', async () => {
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat'],
      connectedSources: [{ id: 4, type: 'confluence', name: 'Fachkonzept' }],
    }));

    await act(async () => { await result.current.navigation.handlePanelFileSelect(0, 'RAUM/Fachkonzept', null, 4); });

    expect(result.current.addPanel).toHaveBeenCalledWith('webview', expect.objectContaining({
      selectedDoc: expect.objectContaining({ isWebOrigin: true }),
    }), false);
  });

  // PS-15: der Sollzustand ist "ein Klick = eine Ansicht". Heute bestimmen
  // onFileSelect und onDocFocus den Zieltyp unabhängig voneinander, und bei
  // einem Dokument-Knoten mit Code-Endung fallen die Entscheidungen
  // auseinander -- das ist O-091. `it.fails` hält das Soll fest; sobald O-091
  // behoben ist, schlägt der Test an und wird zum normalen `it`.
  it.fails('PS-15: der Graph öffnet für einen Dokument-Knoten mit .cbl-Endung genau eine Ansicht', async () => {
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat', 'graph'],
      connectedSources: [{ id: 7, type: 'git', name: 'carddemo' }],
    }));

    // Genau die Reihenfolge aus KnowledgeGraphView.tsx (Dokument-Zweig der
    // Aktion "In passender Ansicht öffnen").
    await act(async () => {
      await result.current.navigation.handlePanelFileSelect(1, 'SRC/CBACT01C.cbl', null, 7);
      result.current.navigation.handleDocFocusRequest('SRC/CBACT01C.cbl', 7, true);
    });

    const openedTypes = [
      ...result.current.addPanel.mock.calls.map((call: any[]) => call[0]),
      ...result.current.ensurePanelType.mock.calls.map((call: any[]) => call[0]),
      ...result.current.ensureLivePanelType.mock.calls.map((call: any[]) => call[0]),
    ];
    expect(openedTypes).toHaveLength(1);
  });

  it('PS-17/PS-18: eine Objektauswahl schreibt panel-lokal und pinnt das Objekt für den Chat', async () => {
    const entity = { name: 'CBACT01C', type: 'program', file_path: 'SRC/CBACT01C.cbl', start_line: 40, source_id: 7 };
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat', 'graph'] }));

    await act(async () => { await result.current.navigation.handlePanelEntitySelect(1, entity); });

    expect(result.current.updatePanelEntitySelection).toHaveBeenCalledWith(1, entity);
    expect(result.current.pinnedCode).toMatchObject({ filepath: 'SRC/CBACT01C.cbl', line: 40, label: 'CBACT01C' });
  });

  it('PS-19: ein Objekt-Treffer der globalen Suche geht über den globalen Pfad', async () => {
    const entity = { name: 'CBACT01C', type: 'program', file_path: 'SRC/CBACT01C.cbl', start_line: 40, source_id: 7 };
    const { result } = renderHook(() => useNavigationHarness({ panelConfigs: ['chat'] }));

    await act(async () => { await result.current.navigation.handleEntitySelect(entity); });

    expect(result.current.handleFileSelect).toHaveBeenCalledWith('SRC/CBACT01C.cbl', 40, 7, null);
    expect(result.current.selectedEntity).toEqual(entity);
  });

  it('PS-20: der Gutter-Klick erreicht das Chat-Panel auch dann, wenn es eingefroren ist', () => {
    const selection: PanelSelection = { selectedFile: 'app/main.cbl', selectedDoc: null, selectedEntity: null, selectedLine: null };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['chat', 'code'],
      panelFrozen: [true, false],
      panelSelections: [EMPTY, selection],
    }));

    act(() => { result.current.navigation.handleGutterClick(1, 87, '           MOVE WS-A TO WS-B.'); });

    expect(result.current.pinnedCode).toMatchObject({ filepath: 'app/main.cbl', line: 87 });
    expect(result.current.activeMobileTab).toBe('chat');
  });

  it('PS-21: fehlt an der Panel-Grenze das Chat-Panel, bekommt der Nutzer eine Rückmeldung (D-2)', () => {
    const selection: PanelSelection = { selectedFile: 'app/main.cbl', selectedDoc: null, selectedEntity: null, selectedLine: null };
    const { result } = renderHook(() => useNavigationHarness({
      panelConfigs: ['code', 'doc', 'graph', 'callgraph'],
      panelSelections: [selection, EMPTY, EMPTY, EMPTY],
    }));
    result.current.ensurePanelType.mockReturnValue(false);

    act(() => { result.current.navigation.handleGutterClick(0, 87, '           MOVE WS-A TO WS-B.'); });

    expect(result.current.showToast).toHaveBeenCalledWith('page.toast.noPanelSpace', 'error');
  });
});
