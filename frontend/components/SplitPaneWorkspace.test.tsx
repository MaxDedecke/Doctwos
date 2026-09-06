import type { EditorProps, OnMount } from '@monaco-editor/react';
import type { KnowledgeGraphView } from './KnowledgeGraphView';
/**
 * O-061 (Teil 2): `SplitPaneWorkspace` entscheidet als zweite Stufe der
 * Panel-Weiche, welcher Inhalt im rechten Bereich landet -- Graph-Ansicht,
 * Web-Original als iframe, Dokument (PDF/Bild/Markdown/HTML/Text) oder der
 * Code-Editor. Geprüft wird genau diese Zuordnung `activeRightTab` +
 * Auswahl → gerenderter Inhalt, samt der Regel, dass der ganze Bereich ohne
 * Datei, ohne Dokument und außerhalb des Graph-Tabs gar nicht erscheint.
 *
 * Monaco und die Graph-Ansicht sind gestubbt (kein Canvas/WebGL in jsdom), der
 * axios-`api`-Wrapper ebenfalls -- die Inhalte selbst kommen hier über die
 * `fileContent`/`fileContentFormat`-Props herein, die im Bauteil Vorrang vor
 * dem selbst geladenen Zustand haben.
 */
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SplitPaneWorkspace } from './SplitPaneWorkspace';

const graphProps: Partial<React.ComponentProps<typeof KnowledgeGraphView>> = {};

// Der Editor meldet sich -- wie das echte Monaco -- erst NACH dem ersten
// Render über `onMount` zurück. Genau dieses Timing ist der Kern des
// Zeilensprung-Tests weiter unten.
const editorStub = {
  revealLineInCenter: vi.fn(),
  setPosition: vi.fn(),
  deltaDecorations: vi.fn(() => []),
  getModel: () => null,
  getLayoutInfo: () => ({ contentLeft: 53 }),
  // Alle Ereignis-Registrierungen, die handleEditorDidMountLocal vornimmt --
  // sie liefern im echten Monaco ein Disposable zurueck.
  onMouseMove: vi.fn(() => ({ dispose: vi.fn() })),
  onMouseLeave: vi.fn(() => ({ dispose: vi.fn() })),
  onMouseDown: vi.fn(() => ({ dispose: vi.fn() })),
  onDidChangeModel: vi.fn(() => ({ dispose: vi.fn() })),
  onDidScrollChange: vi.fn(() => ({ dispose: vi.fn() })),
  onDidChangeCursorPosition: vi.fn(() => ({ dispose: vi.fn() })),
  onDidChangeModelContent: vi.fn(() => ({ dispose: vi.fn() })),
};

const monacoStub = {
  languages: { getLanguages: () => [], register: vi.fn(), setMonarchTokensProvider: vi.fn(), setLanguageConfiguration: vi.fn() },
  editor: { defineTheme: vi.fn(), setTheme: vi.fn() },
  Range: class {},
};

function MonacoStub(props: EditorProps) {
  // Bewusst per setTimeout und nicht im Effekt: React fuehrt Kind-Effekte VOR
  // Eltern-Effekten aus, ein onMount im Effekt waere also schon fertig, bevor
  // der Sprung-Effekt der Werkbank ueberhaupt laeuft -- und wuerde das echte
  // Timing (Monaco laedt asynchron nach) gerade nicht nachbilden.
  // Genau einmal melden. `onMount` ist im Bauteil nicht memoisiert, haengt man
  // den Effekt daran, meldet sich der Stub nach jedem Render erneut -- und der
  // Mount-Zaehler im Bauteil loest dann eine Render-Schleife aus.
  const onMountRef = React.useRef(props.onMount);
  const mountedRef = React.useRef(false);
  React.useEffect(() => {
    onMountRef.current = props.onMount;
  });
  React.useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;
    const timer = setTimeout(() => onMountRef.current?.(editorStub as unknown as Parameters<OnMount>[0], monacoStub as unknown as Parameters<OnMount>[1]), 0);
    return () => clearTimeout(timer);
  }, []);
  return <div data-testid="monaco-editor" data-language={props.defaultLanguage}>{props.value}</div>;
}

vi.mock('@monaco-editor/react', () => ({ default: (props: EditorProps) => <MonacoStub {...props} /> }));

vi.mock('./KnowledgeGraphView', () => ({
  KnowledgeGraphView: (props: React.ComponentProps<typeof KnowledgeGraphView>) => {
    Object.assign(graphProps, props);
    return <div data-testid="knowledge-graph" />;
  },
}));

vi.mock('@/app/services/api', () => ({
  API_URL: 'http://backend',
  api: {
    getEntityNeighbors: vi.fn().mockResolvedValue({ data: { groups: {} } }),
    getProjectReferences: vi.fn().mockResolvedValue({ data: [] }),
    getKnowledgeSourceContent: vi.fn().mockResolvedValue({ data: { content: '', format: 'text' } }),
    resolveWebOrigin: vi.fn().mockResolvedValue({ data: { content: '' } }),
  },
}));

function makeProps(overrides: Partial<React.ComponentProps<typeof SplitPaneWorkspace>> = {}): React.ComponentProps<typeof SplitPaneWorkspace> {
  return {
    theme: 'dark',
    selectedFile: null,
    selectedDoc: null,
    activeRightTab: 'code' as const,
    setActiveRightTab: vi.fn(),
    // repo_id ist die KnowledgeSource-ID der Git-Quelle -- ohne sie holt das
    // Bauteil gar keinen Dateiinhalt, der Graph-Tab-Test wäre dann wirkungslos.
    selectedProject: { id: 3, name: 'Rentenkasse', repo_id: 5 },
    isEditorMaximized: false,
    setIsEditorMaximized: vi.fn(),
    setSelectedFile: vi.fn(),
    setSelectedDoc: vi.fn(),
    fileContent: '',
    fileContentFormat: 'text',
    handleFileSelect: vi.fn(),
    isLoadingFile: false,
    fileReferences: [],
    isLoadingReferences: false,
    isReferencesDropdownOpen: false,
    setIsReferencesDropdownOpen: vi.fn(),
    referencesTab: 'code' as const,
    setReferencesTab: vi.fn(),
    selectedEntity: null,
    splitClasses: { chat: 'w-full', editor: 'w-full' },
    activeLlmModel: 'mistral-nemo',
    activeEmbeddingModel: 'bge-m3',
    editorFontSize: 13,
    editorFontFamily: 'JetBrains Mono',
    editorMinimap: false,
    projectEntities: [],
    ...overrides,
  };
}

function renderWorkspace(overrides: Partial<React.ComponentProps<typeof SplitPaneWorkspace>> = {}) {
  const props = makeProps(overrides);
  const view = render(
    <LanguageProvider>
      <SplitPaneWorkspace {...(props)} />
    </LanguageProvider>
  );
  return { ...view, props };
}

describe('SplitPaneWorkspace', () => {
  afterEach(() => {
    for (const key of Object.keys(graphProps)) delete graphProps[key as keyof typeof graphProps];
    editorStub.revealLineInCenter.mockClear();
    editorStub.setPosition.mockClear();
    vi.clearAllMocks();
  });

  describe('Sichtbarkeit des rechten Bereichs', () => {
    it('bleibt leer, solange weder Datei noch Dokument gewählt sind', () => {
      const { container } = renderWorkspace();

      expect(container.textContent).toBe('');
      expect(screen.queryByTestId('monaco-editor')).toBeNull();
    });

    it('erscheint im Graph-Tab auch ohne Datei und Dokument', () => {
      renderWorkspace({ activeRightTab: 'graph' });

      expect(screen.getByTestId('knowledge-graph')).toBeTruthy();
    });
  });

  describe('activeRightTab → Inhalt', () => {
    it('graph: zeigt die Wissensgraph-Ansicht statt eines Editors', () => {
      renderWorkspace({ activeRightTab: 'graph', selectedFile: 'src/ZAHLUNG.cbl' });

      expect(screen.getByTestId('knowledge-graph')).toBeTruthy();
      expect(screen.queryByTestId('monaco-editor')).toBeNull();
    });

    it('code: zeigt den Editor mit dem Dateiinhalt und der erkannten Sprache', () => {
      renderWorkspace({
        activeRightTab: 'code',
        selectedFile: 'src/ZAHLUNG.cbl',
        fileContent: 'IDENTIFICATION DIVISION.',
      });

      const editor = screen.getByTestId('monaco-editor');
      expect(editor.textContent).toBe('IDENTIFICATION DIVISION.');
      // .cbl → COBOL, nicht der text-Standard.
      expect(editor.getAttribute('data-language')).toBe('cobol');
    });

    it('code: erkennt die Sprache auch für andere Endungen', () => {
      renderWorkspace({ activeRightTab: 'code', selectedFile: 'build.py', fileContent: 'print(1)' });

      expect(screen.getByTestId('monaco-editor').getAttribute('data-language')).toBe('python');
    });

    it('code: fällt bei unbekannter Endung auf Klartext zurück', () => {
      renderWorkspace({ activeRightTab: 'code', selectedFile: 'DATEI.xyz', fileContent: 'inhalt' });

      expect(screen.getByTestId('monaco-editor').getAttribute('data-language')).toBe('text');
    });

    it('weborigin: bettet die aufbereitete Seite als iframe ein, ohne Editor', () => {
      const { container } = renderWorkspace({
        activeRightTab: 'weborigin',
        selectedDoc: { id: 9, name: 'Confluence-Seite', type: 'confluence' },
        fileContent: '<p>Originalseite</p>',
        fileContentFormat: 'html',
      });

      const frame = container.querySelector('iframe')!;
      expect(frame.getAttribute('srcdoc')).toBe('<p>Originalseite</p>');
      // Kein allow-same-origin: die Fremdseite bleibt vom App-Origin getrennt.
      expect(frame.getAttribute('sandbox')).toBe('allow-popups allow-popups-to-escape-sandbox allow-scripts');
      expect(screen.queryByTestId('monaco-editor')).toBeNull();
    });

    it('doc: rendert Markdown als Text, nicht im Editor', () => {
      renderWorkspace({
        activeRightTab: 'doc',
        selectedDoc: { id: 9, name: 'Handbuch.md' },
        fileContent: '# Zahlungslauf',
        fileContentFormat: 'markdown',
      });

      expect(screen.getByText('Zahlungslauf')).toBeTruthy();
      // Der Dateiname steht sowohl in der Kopfzeile als auch als Überschrift
      // des Dokuments -- hier zählt nur, dass die Dokumentansicht greift.
      expect(screen.getByRole('heading', { name: 'Handbuch.md' })).toBeTruthy();
      expect(screen.queryByTestId('monaco-editor')).toBeNull();
    });

    it('doc: zeigt Klartext unverändert an', () => {
      renderWorkspace({
        activeRightTab: 'doc',
        selectedDoc: { id: 9, name: 'Notiz.txt' },
        fileContent: 'Einfach nur Text',
        fileContentFormat: 'text',
      });

      expect(screen.getByText('Einfach nur Text')).toBeTruthy();
    });

    it('doc: holt ein PDF direkt über den Rohdaten-Endpunkt', () => {
      const { container } = renderWorkspace({
        activeRightTab: 'doc',
        selectedDoc: { id: 9, name: 'Handbuch.pdf' },
      });

      const frame = container.querySelector('iframe')!;
      expect(frame.getAttribute('src')).toContain('/knowledge-sources/9/raw?path=Handbuch.pdf');
    });

    it('doc: zeigt ein Bild als <img> statt als Text', () => {
      const { container } = renderWorkspace({
        activeRightTab: 'doc',
        selectedDoc: { id: 9, name: 'Diagramm.png' },
        fileContentFormat: 'image',
      });

      const image = container.querySelector('img')!;
      expect(image.getAttribute('src')).toContain('/knowledge-sources/9/raw?path=Diagramm.png');
      expect(image.getAttribute('alt')).toBe('Diagramm.png');
    });
  });

  describe('Ladeanzeige je Tab', () => {
    it.each([
      ['code', 'Code-Datei wird geladen...'],
      ['weborigin', 'Web-Originalquelle wird geladen...'],
      ['doc', 'Dokument wird geladen...'],
    ] as const)('%s: benennt beim Laden die richtige Inhaltsart', (tab, label) => {
      renderWorkspace({
        activeRightTab: tab,
        selectedFile: 'src/ZAHLUNG.cbl',
        selectedDoc: { id: 9, name: 'Handbuch.md' },
        isLoadingFile: true,
      });

      expect(screen.getByText(label)).toBeTruthy();
      expect(screen.queryByTestId('monaco-editor')).toBeNull();
    });
  });

  describe('Weitergabe an die Graph-Ansicht', () => {
    it('reicht Auswahl, Layoutmodus und Rückrufe durch', () => {
      const { props } = renderWorkspace({
        activeRightTab: 'graph',
        selectedFile: 'src/ZAHLUNG.cbl',
        selectedEntity: { id: 42, name: 'ZAHLUNG', file_path: 'src/ZAHLUNG.cbl', start_line: 1 },
        layoutMode: '4-grid',
        onDocFocus: vi.fn(),
      });

      expect(graphProps.selectedProject).toEqual(expect.objectContaining({ id: 3 }));
      expect(graphProps.selectedEntity).toEqual(props.selectedEntity);
      expect(graphProps.selectedFile).toBe('src/ZAHLUNG.cbl');
      expect(graphProps.layoutMode).toBe('4-grid');
      expect(graphProps.onFileSelect).toBe(props.handleFileSelect);
    });
  });

  describe('Sprung zur Zielzeile', () => {
    it('springt zur Zielzeile, auch wenn der Editor erst nach dem ersten Render bereitsteht', async () => {
      // Beim erstmaligen Oeffnen einer Datei (Suchtreffer, Quellenverweis aus
      // dem Chat) ist Monaco beim ersten Lauf des Effekts noch nicht montiert.
      // Ohne den Mount-Zaehler in den Abhaengigkeiten lief der Effekt genau
      // einmal ins Leere und der Editor blieb in Zeile 1 stehen -- gefunden
      // ueber den O-062-E2E-Test.
      renderWorkspace({ activeRightTab: 'code', selectedFile: 'src/ZAHLUNG.cbl', fileContent: 'A\nB\nC', selectedLine: 13 });

      await waitFor(() => expect(editorStub.revealLineInCenter).toHaveBeenCalledWith(13), { timeout: 2000 });
      expect(editorStub.setPosition).toHaveBeenCalledWith({ lineNumber: 13, column: 1 });
    });

    it('springt nicht, wenn keine Zeile vorgegeben ist', async () => {
      renderWorkspace({ activeRightTab: 'code', selectedFile: 'src/ZAHLUNG.cbl', fileContent: 'A\nB\nC' });

      await waitFor(() => expect(screen.getByTestId('monaco-editor')).toBeTruthy());
      await new Promise(resolve => setTimeout(resolve, 250));
      expect(editorStub.revealLineInCenter).not.toHaveBeenCalled();
    });
  });

  describe('Nebenabrufe je Tab', () => {
    it('lädt im Graph-Tab weder Dateiinhalt noch Referenzen', async () => {
      const { api } = await import('@/app/services/api');

      renderWorkspace({ activeRightTab: 'graph', selectedFile: 'src/ZAHLUNG.cbl', fileContent: undefined });

      await waitFor(() => expect(screen.getByTestId('knowledge-graph')).toBeTruthy());
      expect(api.getKnowledgeSourceContent).not.toHaveBeenCalled();
      expect(api.getProjectReferences).not.toHaveBeenCalled();
    });

    it('lädt die Referenzen einer Datei nur für Code- und Dokument-Panels', async () => {
      const { api } = await import('@/app/services/api');

      const { unmount } = renderWorkspace({ activeRightTab: 'code', selectedFile: 'src/ZAHLUNG.cbl', fileReferences: undefined });
      await waitFor(() => expect(api.getProjectReferences).toHaveBeenCalledWith(3, 'src/ZAHLUNG.cbl'));
      unmount();

      vi.mocked(api.getProjectReferences).mockClear();
      renderWorkspace({ activeRightTab: 'weborigin', selectedFile: 'src/ZAHLUNG.cbl', fileReferences: undefined });
      await waitFor(() => expect(screen.getByTestId('monaco-editor')).toBeTruthy());
      expect(api.getProjectReferences).not.toHaveBeenCalled();
    });
  });
});
