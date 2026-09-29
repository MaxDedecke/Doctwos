import type { EditorProps, OnMount } from '@monaco-editor/react';
import type { KnowledgeGraphView } from './KnowledgeGraphView';
import { axiosResponse } from '@/test/http';
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
import { api } from '@/app/services/api';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { detectLanguage, SplitPaneWorkspace } from './SplitPaneWorkspace';

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

vi.mock('@monaco-editor/react', () => ({
  default: (props: EditorProps) => <MonacoStub {...props} />,
  loader: { config: vi.fn() },
}));

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
    getProjectReferencesPage: vi.fn().mockResolvedValue({ data: { references: [], total: 0, has_more: false, offset: 0, limit: 15 } }),
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

describe('mixed-language editor detection', () => {
  it('uses Monaco modes for Java companion languages', () => {
    expect(detectLanguage('web/report.xsl')).toBe('xml');
    expect(detectLanguage('web/view.jsp')).toBe('html');
    expect(detectLanguage('bin/import.bash')).toBe('shell');
    expect(detectLanguage('config/messages.properties')).toBe('ini');
    expect(detectLanguage('web/report.xslt')).toBe('xml');
    expect(detectLanguage('web/report.jspf')).toBe('html');
    expect(detectLanguage('scripts/tool.mjs')).toBe('javascript');
    expect(detectLanguage('scripts/tool.mts')).toBe('typescript');
    expect(detectLanguage('db/schema.sql')).toBe('sql');
  });
});

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

  describe('Referenzen-Button', () => {
    const docReference = (id: number) => ({ id, title: `Doc ${id}`, source: 'Confluence', node_type: 'document' });

    it('zeigt nur das Link-Icon und die Anzahl, ohne die Beschriftung "Referenzen"', () => {
      renderWorkspace({
        activeRightTab: 'doc',
        selectedDoc: { id: 1, name: 'Handbuch.md', url: 'Handbuch.md' } as never,
        fileReferences: [docReference(1), docReference(2), docReference(3)] as never,
      });

      const button = screen.getByTitle('Referenzen & Verknüpfte Dokumente');
      expect(button.textContent).toBe('3');
      expect(button.querySelector('svg')).toBeTruthy();
      expect(screen.getByTestId('references-count').textContent).toBe('3');
      expect(button.getAttribute('aria-label')).toBe('Referenzen (3)');
      expect(button.className).toContain('h-7');
    });

    it('zeigt ohne Referenzen nur das Icon und bleibt über aria-label benannt', () => {
      renderWorkspace({
        activeRightTab: 'doc',
        selectedDoc: { id: 1, name: 'Handbuch.md', url: 'Handbuch.md' } as never,
        fileReferences: [],
      });

      const button = screen.getByTitle('Referenzen & Verknüpfte Dokumente');
      expect(button.textContent).toBe('');
      expect(screen.queryByTestId('references-count')).toBeNull();
      expect(button.getAttribute('aria-label')).toBe('Referenzen');
    });

    it('öffnet und schließt das Referenzen-Menü per Klick und meldet den Zustand über aria-expanded', () => {
      const setIsReferencesDropdownOpen = vi.fn();
      renderWorkspace({
        activeRightTab: 'doc',
        selectedDoc: { id: 1, name: 'Handbuch.md', url: 'Handbuch.md' } as never,
        fileReferences: [],
        setIsReferencesDropdownOpen,
      });

      const button = screen.getByTitle('Referenzen & Verknüpfte Dokumente');
      expect(button.getAttribute('aria-expanded')).toBe('false');
      fireEvent.click(button);

      expect(setIsReferencesDropdownOpen).toHaveBeenCalledWith(true);
    });
  });

  describe('Referenzen-Menü lädt seitenweise nach', () => {
    const ref = (id: number) => ({ id, node_type: 'entity', name: `Ref${id}`, title: `Ref${id}`, file_path: `src/f${id}.cbl`, line: id, source_id: 5, source: 'Git' });
    const refPage = (from: number, count: number, total: number) =>
      axiosResponse({ references: Array.from({ length: count }, (_, i) => ref(from + i)), total, has_more: from + count < total, offset: from, limit: 15 });
    const docTabProps = {
      activeRightTab: 'doc' as const,
      selectedFile: 'src/main.cbl',
      selectedDoc: { id: 5, name: 'src/main.cbl' },
      fileReferences: undefined,
      isReferencesDropdownOpen: true,
    };

    it('zeigt im Dokument-Tab zunächst 15 Referenzen, den Gesamtstand im Badge und lädt erst auf Klick weitere', async () => {
      vi.mocked(api.getProjectReferencesPage)
        .mockResolvedValueOnce(refPage(0, 15, 40))
        .mockResolvedValueOnce(refPage(15, 15, 40));
      renderWorkspace(docTabProps);

      expect(await screen.findByRole('button', { name: /Ref14/ })).toBeTruthy();
      expect(screen.queryByRole('button', { name: /Ref15/ })).toBeNull();
      expect(screen.getByTestId('references-count').textContent).toBe('40');
      expect(screen.getByTestId('references-more').textContent).toContain('25');
      expect(api.getProjectReferencesPage).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByTestId('references-more'));

      expect(await screen.findByRole('button', { name: /Ref29/ })).toBeTruthy();
      expect(api.getProjectReferencesPage).toHaveBeenLastCalledWith(3, 'src/main.cbl', { offset: 15, limit: 15 });
      expect(screen.getByTestId('references-more').textContent).toContain('10');
    });

    it('bietet keinen Nachlade-Button, wenn alle Referenzen der Datei geladen sind', async () => {
      vi.mocked(api.getProjectReferencesPage).mockResolvedValueOnce(refPage(0, 3, 3));
      renderWorkspace(docTabProps);

      expect(await screen.findByRole('button', { name: /Ref2/ })).toBeTruthy();
      expect(screen.queryByTestId('references-more')).toBeNull();
    });

    it('lädt im Referenzen-Dialog erst die erste Seite und weitere nur auf Klick', async () => {
      vi.mocked(api.getProjectReferencesPage)
        .mockResolvedValueOnce(refPage(0, 1, 1)) // Liste des Menüs
        .mockResolvedValueOnce(axiosResponse({ references: Array.from({ length: 15 }, (_, i) => ref(100 + i)), total: 33, has_more: true, offset: 0, limit: 15 })) // Dialog: erste Seite
        .mockResolvedValueOnce(axiosResponse({ references: Array.from({ length: 15 }, (_, i) => ref(115 + i)), total: 33, has_more: true, offset: 15, limit: 15 })); // Dialog: zweite Seite
      renderWorkspace(docTabProps);

      fireEvent.click(await screen.findByRole('button', { name: /Ref0/ }));
      await waitFor(() => expect(api.getProjectReferencesPage).toHaveBeenLastCalledWith(3, 'src/f0.cbl', { offset: 0, limit: 15 }));

      const more = await screen.findByTestId('focused-references-more');
      expect(more.textContent).toContain('18');
      expect(screen.queryByText('Ref115')).toBeNull();
      fireEvent.click(more);

      expect(await screen.findByText('Ref129')).toBeTruthy();
      expect(api.getProjectReferencesPage).toHaveBeenLastCalledWith(3, 'src/f0.cbl', { offset: 15, limit: 15 });
    });

    const neighbor = (id: number) => ({
      edge_id: id, type: 'CALLS', direction: 'out', resolution: 'resolved', dst_name: `callee${id}`,
      entity: { id: 1000 + id, name: `callee${id}`, type: 'method', file_path: 'src/A.java', start_line: id, source_id: 5 },
      reference: null, start_line: id, end_line: id,
    });
    const codeTabProps = {
      activeRightTab: 'code' as const,
      selectedFile: 'src/A.java',
      fileContent: 'class A {}',
      selectedEntity: { id: 101, name: 'A', type: 'class', file_path: 'src/A.java', start_line: 1, source_id: 5 },
      isReferencesDropdownOpen: true,
    };

    it('lädt Nachbargruppen mit 15 Einträgen, zeigt Gesamtzahl im Badge und lädt eine Gruppe erst auf Klick nach', async () => {
      vi.mocked(api.getEntityNeighbors)
        .mockResolvedValueOnce(axiosResponse({
          entity: codeTabProps.selectedEntity,
          groups: { 'CALLS:out': Array.from({ length: 15 }, (_, i) => neighbor(i + 1)), 'COPY:out': [neighbor(900)] },
          page: {
            'CALLS:out': { total: 40, has_more: true, next_after: 15 },
            'COPY:out': { total: 1, has_more: false, next_after: 900 },
          },
        }))
        .mockResolvedValueOnce(axiosResponse({
          entity: codeTabProps.selectedEntity,
          groups: { 'CALLS:out': Array.from({ length: 15 }, (_, i) => neighbor(i + 16)) },
          page: { 'CALLS:out': { total: 40, has_more: true, next_after: 30 } },
        }));
      renderWorkspace(codeTabProps);

      expect(await screen.findByRole('button', { name: /callee15/ })).toBeTruthy();
      expect(screen.queryByRole('button', { name: /callee16/ })).toBeNull();
      expect(screen.getByTestId('references-count').textContent).toBe('41');
      expect(screen.queryByTestId('neighbors-more-COPY:out')).toBeNull();
      expect(screen.getByTestId('neighbors-more-CALLS:out').textContent).toContain('25');

      fireEvent.click(screen.getByTestId('neighbors-more-CALLS:out'));

      expect(await screen.findByRole('button', { name: /callee30/ })).toBeTruthy();
      expect(api.getEntityNeighbors).toHaveBeenLastCalledWith(101, { projectId: 3, limit: 15, group: 'CALLS:out', after: 15 });
      // die andere Gruppe bleibt unverändert
      expect(screen.getByRole('button', { name: /callee900/ })).toBeTruthy();
      expect(screen.getByTestId('neighbors-more-CALLS:out').textContent).toContain('10');
    });

    it('kennzeichnet die Anzahl mit "+", wenn eine Gruppe ohne bekannte Gesamtzahl weitere Einträge hat', async () => {
      vi.mocked(api.getEntityNeighbors).mockResolvedValueOnce(axiosResponse({
        entity: codeTabProps.selectedEntity,
        groups: { 'DOC:out': Array.from({ length: 15 }, (_, i) => neighbor(i + 1)) },
        page: { 'DOC:out': { total: null, has_more: true, next_after: 15 } },
      }));
      renderWorkspace(codeTabProps);

      await screen.findByTestId('neighbors-more-DOC:out');
      expect(screen.getAllByText(/^callee\d+$/)).toHaveLength(15);
      expect(screen.getByTestId('references-count').textContent).toBe('15+');
      expect(screen.getByTestId('neighbors-more-DOC:out').textContent).toBe('Weitere laden …');
    });

    it('beendet das Nachladen einer Gruppe, wenn die Anfrage fehlschlägt', async () => {
      vi.mocked(api.getEntityNeighbors)
        .mockResolvedValueOnce(axiosResponse({
          entity: codeTabProps.selectedEntity,
          groups: { 'CALLS:out': Array.from({ length: 15 }, (_, i) => neighbor(i + 1)) },
          page: { 'CALLS:out': { total: 40, has_more: true, next_after: 15 } },
        }))
        .mockRejectedValueOnce(new Error('down'));
      renderWorkspace(codeTabProps);
      fireEvent.click(await screen.findByTestId('neighbors-more-CALLS:out'));

      await waitFor(() => expect(screen.queryByTestId('neighbors-more-CALLS:out')).toBeNull());
      expect(screen.getByRole('button', { name: /callee15/ })).toBeTruthy();
    });
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

    it('code: erkennt Java-Dateien und zeigt ihren Originalinhalt im Editor', () => {
      renderWorkspace({
        activeRightTab: 'code',
        selectedFile: 'src/main/java/com/acme/PaymentService.java',
        fileContent: 'package com.acme;\npublic record PaymentService(int id) {}',
      });

      const editor = screen.getByTestId('monaco-editor');
      expect(editor.getAttribute('data-language')).toBe('java');
      expect(editor.textContent).toContain('public record PaymentService');
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
      expect(api.getProjectReferencesPage).not.toHaveBeenCalled();
    });

    it('lädt die Referenzen einer Datei nur für Code- und Dokument-Panels', async () => {
      const { api } = await import('@/app/services/api');

      const { unmount } = renderWorkspace({ activeRightTab: 'code', selectedFile: 'src/ZAHLUNG.cbl', fileReferences: undefined });
      await waitFor(() => expect(api.getProjectReferencesPage).toHaveBeenCalledWith(3, 'src/ZAHLUNG.cbl', { offset: 0, limit: 15 }));
      unmount();

      vi.mocked(api.getProjectReferencesPage).mockClear();
      renderWorkspace({ activeRightTab: 'weborigin', selectedFile: 'src/ZAHLUNG.cbl', fileReferences: undefined });
      await waitFor(() => expect(screen.getByTestId('monaco-editor')).toBeTruthy());
      expect(api.getProjectReferencesPage).not.toHaveBeenCalled();
    });

    it('lädt Java-Entity-Nachbarschaften und öffnet das Ziel mit Zeile und Quelle', async () => {
      const javaEntity = {
        id: 101,
        name: 'PaymentService',
        type: 'class',
        file_path: 'src/main/java/com/acme/PaymentService.java',
        start_line: 8,
        source_id: 5,
      };
      const javaMethod = {
        id: 102,
        name: 'calculate',
        type: 'method',
        file_path: 'src/main/java/com/acme/PaymentService.java',
        start_line: 24,
        source_id: 5,
      };
      vi.mocked(api.getEntityNeighbors).mockResolvedValueOnce(axiosResponse({
          entity: javaEntity,
          groups: {
            'CALLS:out': [{
              edge_id: 9001,
              type: 'CALLS',
              direction: 'out',
              resolution: 'resolved',
              dst_name: 'calculate',
              entity: javaMethod,
              reference: {
                entity_id: 101,
                name: 'PaymentService',
                file_path: javaEntity.file_path,
                source_id: 5,
                start_line: 42,
                end_line: 44,
              },
              start_line: 24,
              end_line: 30,
            }],
          },
        }));
      const handleFileSelect = vi.fn();

      renderWorkspace({
        activeRightTab: 'code',
        selectedFile: javaEntity.file_path,
        fileContent: 'class PaymentService {}',
        selectedEntity: javaEntity,
        isReferencesDropdownOpen: true,
        handleFileSelect,
      });

      const target = await screen.findByRole('button', { name: /calculate/ });
      expect(api.getEntityNeighbors).toHaveBeenCalledWith(101, { projectId: 3, limit: 15 });

      target.click();

      expect(handleFileSelect).toHaveBeenCalledWith(javaMethod.file_path, javaMethod.start_line, javaMethod.source_id);

      fireEvent.click(screen.getByRole('button', { name: /Referenz in .* \(Zeile 42\)/ }));
      expect(handleFileSelect).toHaveBeenCalledWith(javaEntity.file_path, 42, 5);
    });

    it('öffnet eine Java-Entity in der Referenzansicht und drillt zur verknüpften Zeile weiter', async () => {
      const javaReference = {
        id: 102,
        node_type: 'entity',
        name: 'PaymentRepository',
        file_path: 'src/main/java/com/acme/PaymentRepository.java',
        line: 31,
        source_id: 5,
        source: 'Git',
      };
      const handleFileSelect = vi.fn();
      vi.mocked(api.getProjectReferencesPage).mockResolvedValue(axiosResponse({ references: [javaReference], total: 1, has_more: false, offset: 0, limit: 15 }));

      renderWorkspace({
        activeRightTab: 'doc',
        selectedFile: 'src/main/java/com/acme/PaymentService.java',
        selectedDoc: { id: 5, name: 'src/main/java/com/acme/PaymentService.java' },
        fileReferences: [javaReference],
        isReferencesDropdownOpen: true,
        handleFileSelect,
      });

      fireEvent.click(await screen.findByRole('button', { name: /PaymentRepository/ }));
      await waitFor(() => expect(api.getProjectReferencesPage).toHaveBeenCalledWith(3, javaReference.file_path, { offset: 0, limit: 15 }));

      const drilldownTarget = (await screen.findByText(javaReference.file_path, { exact: true })).closest('[class*="cursor-pointer"]');
      expect(drilldownTarget).not.toBeNull();
      fireEvent.click(drilldownTarget!);

      expect(handleFileSelect).toHaveBeenCalledWith(javaReference.file_path, javaReference.line, javaReference.source_id);
    });
  });
});
