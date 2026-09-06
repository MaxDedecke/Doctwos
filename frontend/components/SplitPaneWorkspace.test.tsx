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
import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { SplitPaneWorkspace } from './SplitPaneWorkspace';

const graphProps: Record<string, any> = {};

vi.mock('@monaco-editor/react', () => ({
  default: (props: any) => <div data-testid="monaco-editor" data-language={props.defaultLanguage}>{props.value}</div>,
}));

vi.mock('./KnowledgeGraphView', () => ({
  KnowledgeGraphView: (props: any) => {
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

function makeProps(overrides: Partial<React.ComponentProps<typeof SplitPaneWorkspace>> = {}) {
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
      <SplitPaneWorkspace {...(props as any)} />
    </LanguageProvider>
  );
  return { ...view, props };
}

describe('SplitPaneWorkspace', () => {
  afterEach(() => {
    for (const key of Object.keys(graphProps)) delete graphProps[key];
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
    ])('%s: benennt beim Laden die richtige Inhaltsart', (tab, label) => {
      renderWorkspace({
        activeRightTab: tab as any,
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
        selectedEntity: { id: 42 },
        layoutMode: '4-grid',
        onDocFocus: vi.fn(),
      });

      expect(graphProps.selectedProject).toEqual(expect.objectContaining({ id: 3 }));
      expect(graphProps.selectedEntity).toEqual({ id: 42 });
      expect(graphProps.selectedFile).toBe('src/ZAHLUNG.cbl');
      expect(graphProps.layoutMode).toBe('4-grid');
      expect(graphProps.onFileSelect).toBe(props.handleFileSelect);
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
