/**
 * O-061 (Teil 1): die Zuordnung Panel-Konfiguration → gerenderter Inhalt war
 * ungetestet. `PanelContentRenderer` ist die Weiche: aus dem `contentType`
 * eines Panels wird entweder eine eigene Ansicht (Chat, Call-Graph,
 * Link-Manager) oder `SplitPaneWorkspace` mit einem daraus abgeleiteten
 * `activeRightTab`. Die abgeleiteten Werte sind der eigentliche Prüfpunkt --
 * `webview` wird zu `weborigin`, alles Unbekannte fällt auf `code` zurück, und
 * `layoutMode` bzw. `onDocFocus` werden bewusst nur für bestimmte Typen
 * durchgereicht.
 *
 * Alle vier Zielansichten sind durch Stubs ersetzt, die ihre Props festhalten:
 * geprüft wird die Verdrahtung, nicht das Innenleben der Ansichten (die haben
 * ihre eigenen Tests). Das hält den Test auch frei von Monaco, Canvas und
 * Netzwerkaufrufen.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PanelContentRenderer } from './PanelContentRenderer';

const captured: Record<string, any> = {};

function stub(name: string) {
  const Stub = (props: any) => {
    captured[name] = props;
    return <div data-testid={name} />;
  };
  Stub.displayName = name;
  return Stub;
}

vi.mock('@/components/ChatView', () => ({ ChatView: stub('chat-view') }));
vi.mock('@/components/CallGraphView', () => ({ CallGraphView: stub('callgraph-view') }));
vi.mock('@/components/LinkManagerView', () => ({ LinkManagerView: stub('linkmanager-view') }));
vi.mock('@/components/SplitPaneWorkspace', () => ({ SplitPaneWorkspace: stub('split-pane') }));

const SELECTION = {
  selectedFile: 'src/ZAHLUNG.cbl',
  selectedDoc: { id: 9, name: 'Handbuch.pdf' },
  selectedEntity: { id: 42, name: 'ZAHLUNG', source_id: 5 },
  selectedLine: 12,
};

function makeProps(overrides: Partial<React.ComponentProps<typeof PanelContentRenderer>> = {}) {
  return {
    index: 2,
    contentType: 'chat',
    selection: SELECTION,
    theme: 'dark',
    isSidebarOpen: true,
    selectedProject: { id: 3, name: 'Rentenkasse', repo_id: 5 },
    handleProjectSelect: vi.fn(),
    pinnedCode: null,
    setPinnedCode: vi.fn(),
    chatMessages: [],
    currentMessage: '',
    setCurrentMessage: vi.fn(),
    isLoading: false,
    handleSendChat: vi.fn(),
    handleRetryMessage: vi.fn(),
    handleFeedback: vi.fn(),
    addAssistantHint: vi.fn(),
    handlePanelFileSelect: vi.fn(),
    activeProfileId: 'p1',
    setActiveProfileId: vi.fn(),
    llmProfiles: [{ id: 'p1', name: 'Mistral', model: 'mistral-nemo' }],
    showToast: vi.fn(),
    selectedSource: null,
    setSelectedSource: vi.fn(),
    connectedSources: [],
    activeLlmModel: 'mistral-nemo',
    activeEmbeddingModel: 'bge-m3',
    editorFontSize: 13,
    editorFontFamily: 'JetBrains Mono',
    editorMinimap: false,
    isReferencesDropdownOpen: false,
    setIsReferencesDropdownOpen: vi.fn(),
    referencesTab: 'code' as const,
    setReferencesTab: vi.fn(),
    handlePanelEntitySelect: vi.fn(),
    handleGutterClick: vi.fn(),
    handleGutterAskEntity: vi.fn(),
    projectEntities: [],
    fileNavStack: [],
    handleNavigateBack: vi.fn(),
    handleDocFocusRequest: vi.fn(),
    layoutMode: '4-grid' as const,
    chatEndRef: React.createRef<HTMLDivElement>(),
    currentUser: { is_admin: true },
    ...overrides,
  };
}

function renderPanel(overrides: Partial<React.ComponentProps<typeof PanelContentRenderer>> = {}) {
  const props = makeProps(overrides);
  const view = render(<PanelContentRenderer {...(props as any)} />);
  return { ...view, props };
}

describe('PanelContentRenderer', () => {
  beforeEach(() => {
    for (const key of Object.keys(captured)) delete captured[key];
  });

  describe('Panel-Typ → Ansicht', () => {
    it('rendert für "chat" die Chat-Ansicht', () => {
      renderPanel({ contentType: 'chat' });

      expect(screen.getByTestId('chat-view')).toBeTruthy();
      expect(screen.queryByTestId('split-pane')).toBeNull();
    });

    it('rendert für "callgraph" die Call-Graph-Ansicht mit dem fokussierten Objekt', () => {
      renderPanel({ contentType: 'callgraph' });

      expect(screen.getByTestId('callgraph-view')).toBeTruthy();
      expect(captured['callgraph-view'].focusedEntity).toBe(SELECTION.selectedEntity);
      expect(captured['callgraph-view'].projectId).toBe(3);
    });

    it('rendert für "linkmanager" den Link-Manager samt Nutzerrolle', () => {
      renderPanel({ contentType: 'linkmanager' });

      expect(screen.getByTestId('linkmanager-view')).toBeTruthy();
      expect(captured['linkmanager-view'].currentUser).toEqual({ is_admin: true });
      expect(captured['linkmanager-view'].selectedProject).toEqual(expect.objectContaining({ id: 3 }));
    });

    it.each([
      ['code', 'code'],
      ['doc', 'doc'],
      ['graph', 'graph'],
      ['webview', 'weborigin'],
    ])('rendert für "%s" den Split-Pane mit activeRightTab "%s"', (contentType, expectedTab) => {
      renderPanel({ contentType });

      expect(screen.getByTestId('split-pane')).toBeTruthy();
      expect(captured['split-pane'].activeRightTab).toBe(expectedTab);
    });

    it('fällt bei einem unbekannten Panel-Typ auf die Code-Ansicht zurück', () => {
      renderPanel({ contentType: 'gibtsnicht' });

      expect(screen.getByTestId('split-pane')).toBeTruthy();
      expect(captured['split-pane'].activeRightTab).toBe('code');
    });

    it('reicht die Auswahl des Panels an den Split-Pane durch', () => {
      renderPanel({ contentType: 'code' });

      expect(captured['split-pane'].selectedFile).toBe('src/ZAHLUNG.cbl');
      expect(captured['split-pane'].selectedDoc).toEqual({ id: 9, name: 'Handbuch.pdf' });
      expect(captured['split-pane'].selectedEntity).toBe(SELECTION.selectedEntity);
      expect(captured['split-pane'].selectedLine).toBe(12);
    });
  });

  describe('typabhängig durchgereichte Props', () => {
    it('gibt den Layoutmodus nur an das Graph-Panel weiter', () => {
      const { unmount } = renderPanel({ contentType: 'graph' });
      expect(captured['split-pane'].layoutMode).toBe('4-grid');
      unmount();

      renderPanel({ contentType: 'code' });
      expect(captured['split-pane'].layoutMode).toBeUndefined();
    });

    it('nimmt dem Webview-Panel den Dokument-Fokus-Handler', () => {
      const { unmount, props } = renderPanel({ contentType: 'doc' });
      expect(captured['split-pane'].onDocFocus).toBe(props.handleDocFocusRequest);
      unmount();

      renderPanel({ contentType: 'webview' });
      expect(captured['split-pane'].onDocFocus).toBeUndefined();
    });
  });

  describe('Verdrahtung der Rückrufe auf den Panel-Index', () => {
    it('bindet die Dateiauswahl der Chat-Ansicht an das eigene Panel', () => {
      const { props } = renderPanel({ contentType: 'chat' });

      captured['chat-view'].handleFileSelect('src/UNTER.cbl', 20, '5');

      expect(props.handlePanelFileSelect).toHaveBeenCalledWith(2, 'src/UNTER.cbl', 20, '5');
    });

    it('öffnet einen Call-Graph-Sprung in einem eigenen Panel, statt ein eingefrorenes zu überschreiben', () => {
      const { props } = renderPanel({ contentType: 'callgraph' });

      captured['callgraph-view'].onFileSelect('src/UNTER.cbl', 20, 5);

      // openIfMissing=true -- ein Sprung aus dem Call-Graph darf ein Zielpanel
      // aufmachen. Der frühere Zusatzparameter preserveFrozenTarget ist mit
      // Entscheidung D-1 entfallen: seither zielt kein Pfad mehr auf ein
      // eingefrorenes Panel (siehe docs/PANEL_SYNCHRONISATION.md).
      expect(props.handlePanelFileSelect).toHaveBeenCalledWith(2, 'src/UNTER.cbl', 20, 5, true);
    });

    it('übersetzt die Dokumentauswahl des Split-Pane in Name und Quellen-ID', () => {
      const { props } = renderPanel({ contentType: 'doc' });

      captured['split-pane'].setSelectedDoc({ id: 9, name: 'Handbuch.pdf' });

      expect(props.handlePanelFileSelect).toHaveBeenCalledWith(2, 'Handbuch.pdf', null, 9);
    });

    it('räumt eine abgewählte Datei über denselben Weg ab', () => {
      const { props } = renderPanel({ contentType: 'code' });

      captured['split-pane'].setSelectedFile(null);
      captured['split-pane'].setSelectedDoc(null);

      expect(props.handlePanelFileSelect).toHaveBeenNthCalledWith(1, 2, null);
      expect(props.handlePanelFileSelect).toHaveBeenNthCalledWith(2, 2, null, null, null);
    });

    it('bindet Gutter-Klicks und Entity-Auswahl an das eigene Panel', () => {
      const { props } = renderPanel({ contentType: 'code' });

      captured['split-pane'].handleEntitySelect({ id: 42 });
      captured['split-pane'].onGutterClick(7, 'MOVE A TO B');
      captured['split-pane'].onGutterAskEntity({ id: 42 });

      expect(props.handlePanelEntitySelect).toHaveBeenCalledWith(2, { id: 42 });
      expect(props.handleGutterClick).toHaveBeenCalledWith(2, 7, 'MOVE A TO B');
      expect(props.handleGutterAskEntity).toHaveBeenCalledWith(2, { id: 42 });
    });
  });
});
