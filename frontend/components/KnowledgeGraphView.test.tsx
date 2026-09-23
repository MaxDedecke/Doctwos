import type { GraphNode, GraphEdge } from './KnowledgeGraphView';
/**
 * O-053: GET /graph (Knowledge-Graph-Übersicht) lud bisher jede sichtbare
 * Code-Entity und jeden Dokument-Chunk unbegrenzt. Diese Tests decken die
 * Frontend-Seite der Behebung ab: die Übersicht zeigt eine Kapp-Warnung, wenn
 * der Server `truncated: true` meldet, und ein neuer "Nur Nachbarschaft
 * laden"-Button lädt über GET /graph/focus die tatsächliche, ungekappte
 * Nachbarschaft eines Knotens (der Endpunkt existierte im Backend schon
 * länger, wurde vom Frontend aber nie aufgerufen).
 *
 * react-force-graph-2d wird dynamisch importiert und braucht Canvas-Maschinerie,
 * die jsdom nicht hat -- gemockt durch eine Stub-Komponente, die pro Knoten
 * einen klickbaren Button rendert (treibt onNodeClick ohne echtes Canvas an).
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { KnowledgeGraphView } from './KnowledgeGraphView';

const centerAt = vi.fn();

type GraphStubProps = {
  graphData: { nodes: GraphNode[]; links: GraphEdge[] };
  onNodeClick: (node: GraphNode) => void;
  linkDirectionalArrowLength?: (link: GraphEdge) => number;
  linkDirectionalArrowRelPos?: (link: GraphEdge) => number;
  linkCurvature?: (link: GraphEdge) => number;
};
const ForceGraph2DStub = React.forwardRef<{ zoom: () => number; zoomToFit: () => void }, GraphStubProps>((props, ref) => {
  React.useImperativeHandle(ref, () => ({
    zoom: () => 1,
    centerAt,
    d3Force: () => undefined,
    d3ReheatSimulation: () => {},
    zoomToFit: () => {},
  }));
  return (
    <div data-testid="force-graph-stub">
      {props.graphData.nodes.map((node) => (
        <button key={node.id} data-testid={`node-${node.id}`} onClick={() => props.onNodeClick(node)}>
          {node.label}
        </button>
      ))}
      {props.graphData.links.map((link) => (
        <span
          key={link.id}
          data-testid={`link-${link.id}`}
          data-arrow-length={props.linkDirectionalArrowLength ? props.linkDirectionalArrowLength(link) : undefined}
          data-arrow-rel-pos={props.linkDirectionalArrowRelPos ? props.linkDirectionalArrowRelPos(link) : undefined}
          data-curvature={props.linkCurvature ? props.linkCurvature(link) : undefined}
        />
      ))}
    </div>
  );
});
ForceGraph2DStub.displayName = 'ForceGraph2DStub';

vi.mock('react-force-graph-2d', () => ({ default: ForceGraph2DStub }));

// Real ResizeObservers always defer their first callback to a later microtask,
// never invoke synchronously inside observe() -- calling back synchronously
// here trips React's "too many re-renders" loop guard against a pre-existing
// render-time setState pattern further down in this component that a real
// browser's async timing never triggers.
class ResizeObserverStub {
  private cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) { this.cb = cb; }
  observe() {
    queueMicrotask(() => this.cb([{ contentRect: { width: 800, height: 600 } }] as ResizeObserverEntry[], this as unknown as ResizeObserver));
  }
  unobserve() {}
  disconnect() {}
}

function renderGraph() {
  return render(
    <LanguageProvider>
      <KnowledgeGraphView theme="dark" selectedProject={{ id: 1, name: 'Testprojekt' }} />
    </LanguageProvider>
  );
}

describe('KnowledgeGraphView overview truncation & neighborhood focus (O-053)', () => {
  beforeEach(() => {
    centerAt.mockClear();
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('centers a selected node once simulation coordinates arrive, without a graphData ref method', async () => {
    const node: GraphNode = { id: 'entity:1', type: 'entity', label: 'PROG1' };
    const docNode: GraphNode = { id: 'doc:1', type: 'document', label: 'DOC1' };
    const edge: GraphEdge = { id: 'link:1', source: 'entity:1', target: 'doc:1', link_type: 'semantic', score: 0.9, context: null };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [node, docNode], edges: [edge] }),
    }));
    renderGraph();
    fireEvent.click(await screen.findByTestId('node-entity:1'));
    // The force simulation mutates these same objects after the initial selection.
    node.x = 12;
    node.y = 34;
    await waitFor(() => expect(centerAt).toHaveBeenCalledWith(12, 34, 800));
  });

  it('shows a code node language and parser limitation in its details (O-253)', async () => {
    const javaNode: GraphNode = {
      id: 'entity:language-aware',
      type: 'entity',
      label: 'ReportTransform',
      entity_type: 'xslt_stylesheet',
      language: 'xslt',
      file_path: 'resources/report.xsl',
      start_line: 1,
      analysis_status: 'partial',
      analysis_reasons: ['unterminated template'],
    };
    const docNode: GraphNode = { id: 'doc:runbook', type: 'document', label: 'Runbook' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [javaNode, docNode],
        edges: [{ id: 'link:1', source: javaNode.id, target: docNode.id, link_type: 'semantic', score: 1, context: null }],
      }),
    }));

    renderGraph();
    fireEvent.click(await screen.findByTestId(`node-${javaNode.id}`));

    expect(screen.getByText('xslt')).toBeTruthy();
    expect(screen.getByText('Teilweise analysiert')).toBeTruthy();
    expect(screen.getByText('resources/report.xsl:1')).toBeTruthy();
    expect(screen.getByText('Teilweise analysiert').getAttribute('title')).toContain('unterminated template');
  });

  it('shows a truncation notice with the true totals when the backend caps the overview', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [{ id: 'entity:1', type: 'entity', label: 'PROG1' }],
        edges: [],
        truncated: true,
        total_nodes: 5000,
        total_edges: 3000,
      }),
    }));

    renderGraph();

    await waitFor(() => expect(screen.getByText(/5000/)).toBeTruthy());
  });

  it('shows no truncation notice when the overview fits under the cap', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [
          { id: 'entity:1', type: 'entity', label: 'PROG1' },
          { id: 'doc:1', type: 'document', label: 'DOC1' },
        ],
        edges: [{ id: 'link:1', source: 'entity:1', target: 'doc:1', link_type: 'semantic', score: 0.9, context: null }],
        truncated: false,
        total_nodes: 2,
        total_edges: 1,
      }),
    }));

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    expect(screen.queryByText(/Zu groß für die Übersicht/)).toBeNull();
  });

  it('shows all relationship types initially and lets each type be toggled', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [
          { id: 'entity:1', type: 'entity', label: 'PROG1' },
          { id: 'doc:runbook', type: 'document', label: 'Runbook' },
        ],
        edges: [
          { id: 'semantic:1', source: 'entity:1', target: 'doc:runbook', link_type: 'semantic', score: 0.9, context: null },
          { id: 'documented:1', source: 'entity:1', target: 'doc:runbook', link_type: 'documented', score: 0.8, context: null },
        ],
      }),
    }));

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('link-semantic:1')).toBeTruthy());
    expect(screen.getByTestId('link-documented:1')).toBeTruthy();

    fireEvent.click(screen.getAllByText('dokumentiert')[0]);
    await waitFor(() => expect(screen.queryByTestId('link-documented:1')).toBeNull());

    fireEvent.click(screen.getAllByText('dokumentiert')[0]);
    await waitFor(() => expect(screen.getByTestId('link-documented:1')).toBeTruthy());
  });

  it('exposes indexed PDF nodes through the shared Datei badge', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [
          { id: 'doc:scanned-handbook.pdf', type: 'document', label: 'scanned-handbook.pdf', file_path: 'scanned-handbook.pdf' },
          { id: 'entity:1', type: 'entity', label: 'PROG1' },
        ],
        edges: [{ id: 'link:1', source: 'entity:1', target: 'doc:scanned-handbook.pdf', link_type: 'semantic', score: 0.9, context: null }],
      }),
    }));

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-doc:scanned-handbook.pdf')).toBeTruthy());
    expect(screen.getAllByText('Datei').length).toBeGreaterThan(0);
  });

  it('navigates from a Java entity node while preserving its file, line and source', async () => {
    const javaNode: GraphNode = {
      id: 'entity:101',
      type: 'entity',
      entity_type: 'method',
      label: 'calculate',
      file_path: 'src/main/java/com/acme/PaymentService.java',
      start_line: 24,
      source_id: 5,
      project_id: 1,
    };
    const targetNode: GraphNode = { id: 'doc:1', type: 'document', label: 'DOC1' };
    const edge: GraphEdge = { id: 'link:1', source: 'entity:101', target: 'doc:1', link_type: 'semantic', score: 0.9, context: null };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [javaNode, targetNode], edges: [edge] }),
    }));
    const onFileSelect = vi.fn();

    render(
      <LanguageProvider>
        <KnowledgeGraphView
          theme="dark"
          selectedProject={{ id: 1, name: 'Testprojekt' }}
          onFileSelect={onFileSelect}
        />
      </LanguageProvider>,
    );

    fireEvent.click(await screen.findByTestId('node-entity:101'));

    expect(onFileSelect).toHaveBeenCalledWith(javaNode.file_path, javaNode.start_line, javaNode.source_id, false);
  });

  it('loads the real neighborhood via GET /graph/focus and replaces the (possibly truncated) overview', async () => {
    const overviewResponse = {
      nodes: [
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
        { id: 'doc:init', type: 'document', label: 'InitDoc' },
      ],
      edges: [{ id: 'link:0', source: 'entity:1', target: 'doc:init', link_type: 'semantic', score: 0.9, context: null }],
      truncated: true,
      total_nodes: 5000,
      total_edges: 3000,
    };
    const focusResponse = {
      focus_id: 'entity:1',
      nodes: [
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
        { id: 'doc:Runbook', type: 'document', label: 'Runbook' },
      ],
      edges: [{ id: 'edl:1', source: 'entity:1', target: 'doc:Runbook', link_type: 'semantic', score: 0.9, context: null }],
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => overviewResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => focusResponse });
    vi.stubGlobal('fetch', fetchMock);

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    fireEvent.click(screen.getByTestId('node-entity:1'));

    const loadNeighborhoodButton = await screen.findByText('Nur Nachbarschaft laden');
    fireEvent.click(loadNeighborhoodButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const focusCallUrl = String(fetchMock.mock.calls[1][0]);
    expect(focusCallUrl).toContain('/graph/focus');
    expect(focusCallUrl).toContain('entity_id=1');
    expect(focusCallUrl).toContain('project_id=1');

    // The overview's truncation banner is gone -- this is now the real,
    // uncapped neighborhood, not a possibly-cut overview.
    await waitFor(() => expect(screen.getByTestId('node-doc:Runbook')).toBeTruthy());
    expect(screen.queryByText(/Zu groß für die Übersicht/)).toBeNull();
    expect(screen.getByText('Zurück zur Übersicht')).toBeTruthy();
  });

  it('restores the cached overview after a neighborhood focus without re-fetching GET /graph', async () => {
    const overviewResponse = {
      nodes: [
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
        { id: 'doc:init', type: 'document', label: 'InitDoc' },
      ],
      edges: [{ id: 'link:0', source: 'entity:1', target: 'doc:init', link_type: 'semantic', score: 0.9, context: null }],
      truncated: false,
      total_nodes: 2,
      total_edges: 1,
    };
    const focusResponse = {
      focus_id: 'entity:1',
      nodes: [
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
        { id: 'doc:Runbook', type: 'document', label: 'Runbook' },
      ],
      edges: [{ id: 'edl:1', source: 'entity:1', target: 'doc:Runbook', link_type: 'semantic', score: 0.9, context: null }],
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => overviewResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => focusResponse });
    vi.stubGlobal('fetch', fetchMock);

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    fireEvent.click(screen.getByTestId('node-entity:1'));
    fireEvent.click(await screen.findByText('Nur Nachbarschaft laden'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    fireEvent.click(await screen.findByText('Zurück zur Übersicht'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText('Zurück zur Übersicht')).toBeNull());
  });

  it('loads neighborhood with cursor pagination and expands more connections (O-298)', async () => {
    const overviewResponse = {
      nodes: [
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
        { id: 'doc:init', type: 'document', label: 'InitDoc' },
      ],
      edges: [{ id: 'link:0', source: 'entity:1', target: 'doc:init', link_type: 'semantic', score: 0.9, context: null }],
    };
    const focusPage1 = {
      focus_id: 'entity:1',
      nodes: [
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
        { id: 'entity:2', type: 'entity', label: 'PROG2', project_id: 1 },
      ],
      edges: [{ id: 'cd:1', source: 'entity:1', target: 'entity:2', link_type: 'code_dependency', direction: 'undirected' }],
      has_more: true,
      next_cursor: '1',
    };
    const focusPage2 = {
      focus_id: 'entity:1',
      nodes: [
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
        { id: 'entity:3', type: 'entity', label: 'PROG3', project_id: 1 },
      ],
      edges: [{ id: 'cd:2', source: 'entity:1', target: 'entity:3', link_type: 'code_dependency', direction: 'undirected' }],
      has_more: false,
      next_cursor: null,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => overviewResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => focusPage1 })
      .mockResolvedValueOnce({ ok: true, json: async () => focusPage2 });
    vi.stubGlobal('fetch', fetchMock);

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    fireEvent.click(screen.getByTestId('node-entity:1'));
    fireEvent.click(await screen.findByText('Nur Nachbarschaft laden'));

    await waitFor(() => expect(screen.getByTestId('node-entity:2')).toBeTruthy());
    const loadMoreButton = await screen.findAllByText('Weitere Verbindungen laden');
    expect(loadMoreButton.length).toBeGreaterThan(0);

    fireEvent.click(loadMoreButton[0]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const page2Url = String(fetchMock.mock.calls[2][0]);
    expect(page2Url).toContain('cursor=1');

    await waitFor(() => expect(screen.getByTestId('node-entity:3')).toBeTruthy());
    expect(screen.queryByText('Weitere Verbindungen laden')).toBeNull();
  });

  it('loads neighborhood for a document node via GET /graph/neighborhood (O-298)', async () => {
    const overviewResponse = {
      nodes: [
        { id: 'doc:Runbook', type: 'document', label: 'Runbook', project_id: 1 },
        { id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 },
      ],
      edges: [{ id: 'link:0', source: 'entity:1', target: 'doc:Runbook', link_type: 'semantic', score: 0.9, context: null }],
    };
    const docNeighborhoodResponse = {
      focus_id: 'doc:Runbook',
      nodes: [
        { id: 'doc:Runbook', type: 'document', label: 'Runbook', project_id: 1 },
        { id: 'entity:42', type: 'entity', label: 'AUTH_MODULE', project_id: 1 },
      ],
      edges: [{ id: 'edl:42', source: 'entity:42', target: 'doc:Runbook', link_type: 'documented', score: 0.95 }],
      has_more: false,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => overviewResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => docNeighborhoodResponse });
    vi.stubGlobal('fetch', fetchMock);

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-doc:Runbook')).toBeTruthy());
    fireEvent.click(screen.getByTestId('node-doc:Runbook'));

    const loadNeighborhoodButton = await screen.findByText('Nur Nachbarschaft laden');
    fireEvent.click(loadNeighborhoodButton);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const docCallUrl = String(fetchMock.mock.calls[1][0]);
    expect(docCallUrl).toContain('/graph/neighborhood');
    expect(docCallUrl).toContain('node_id=doc%3ARunbook');
    await waitFor(() => expect(screen.getByTestId('node-entity:42')).toBeTruthy());
  });
});

/**
 * O-091 (PS-15/PS-16 der Soll-Matrix, docs/PANEL_SYNCHRONISATION.md).
 *
 * Der Dokument-Zweig der Aktion "In passender Ansicht öffnen" feuerte früher
 * zwei voneinander unabhängige Navigationen: onFileSelect entschied den
 * Zieltyp an der Dateiendung und öffnete für einen Dokument-Knoten namens
 * SRC/CBACT01C.cbl einen Code-Editor, onDocFocus öffnete unmittelbar danach
 * unbedingt ein doc-Panel und setzte die globale Doc-Auswahl -- die den frisch
 * geöffneten Editor wieder leerte. Sichtbar wurde das als "Code landet in der
 * Doku-Ansicht, dazu geht ein leerer Editor auf".
 *
 * Der Zieltyp wird jetzt genau einmal bestimmt, hinter onFileSelect
 * (usePanelNavigation::handlePanelFileSelect). Diese Tests halten fest, dass
 * der Graph pro Klick genau einen Navigationsaufruf abgibt -- die Zielauflösung
 * selbst prüft hooks/panelSyncMatrix.test.tsx.
 */
describe('KnowledgeGraphView: ein Klick = eine Ansicht (O-091)', () => {
  const docNode: GraphNode = {
    id: 'doc:12',
    type: 'document',
    label: 'CBACT01C.cbl',
    file_path: 'SRC/CBACT01C.cbl',
    source_id: 7,
    source_type: 'git',
    project_id: 1,
  };

  function renderGraphWithNavigation(onFileSelect: (...args: unknown[]) => void) {
    return render(
      <LanguageProvider>
        <KnowledgeGraphView
          theme="dark"
          selectedProject={{ id: 1, name: 'Testprojekt' }}
          onFileSelect={onFileSelect}
        />
      </LanguageProvider>
    );
  }

  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [docNode, { id: 'entity:1', type: 'entity', label: 'CBACT01C' }],
        edges: [{ id: 'link:1', source: 'entity:1', target: 'doc:12', link_type: 'semantic', score: 0.9, context: null }],
      }),
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('PS-16: der Einfachklick auf einen Dokument-Knoten gibt genau einen Navigationsaufruf ab', async () => {
    const onFileSelect = vi.fn();
    renderGraphWithNavigation(onFileSelect);

    fireEvent.click(await screen.findByTestId('node-doc:12'));

    expect(onFileSelect).toHaveBeenCalledTimes(1);
    // openIfMissing=false: der Einfachklick stupst nur an, er öffnet nichts.
    expect(onFileSelect).toHaveBeenCalledWith('SRC/CBACT01C.cbl', null, 7, false);
  });

  it('PS-15: "In passender Ansicht öffnen" gibt genau einen Navigationsaufruf ab', async () => {
    const onFileSelect = vi.fn();
    renderGraphWithNavigation(onFileSelect);

    fireEvent.click(await screen.findByTestId('node-doc:12'));
    onFileSelect.mockClear();

    fireEvent.click(await screen.findByText('In passender Ansicht öffnen'));

    expect(onFileSelect).toHaveBeenCalledTimes(1);
    expect(onFileSelect).toHaveBeenCalledWith('SRC/CBACT01C.cbl', null, 7);
  });

  // Die drei Tests oben zählen Aufrufe EINER Rückrufschnittstelle; der Fehler
  // von O-091 bestand aber gerade darin, dass eine ZWEITE danebenstand. Deshalb
  // zusätzlich strukturell: im Graphen darf es keinen zweiten Navigationsweg
  // mehr geben. (Erwähnungen in Kommentaren sind erlaubt, Aufrufe nicht.)
  it('O-091: der Graph kennt keinen zweiten Navigationsweg neben onFileSelect', () => {
    // Vitest läuft mit dem Frontend-Verzeichnis als Wurzel (vitest.config.ts).
    const source = readFileSync(resolve(process.cwd(), 'components/KnowledgeGraphView.tsx'), 'utf-8');

    expect(source).not.toMatch(/onDocFocus\s*\??\.?\(/);
  });

  it('PS-15: eine Confluence-Seite geht denselben einen Weg -- über url statt file_path', async () => {
    const pageNode: GraphNode = {
      id: 'doc:44',
      type: 'document',
      label: 'Fachkonzept',
      file_path: 'RAUM/Fachkonzept',
      url: 'https://confluence.test/RAUM/Fachkonzept',
      source_id: 4,
      source_type: 'confluence',
      project_id: 1,
    };
    const targetNode: GraphNode = { id: 'entity:1', type: 'entity', label: 'PROG1' };
    const edge: GraphEdge = { id: 'link:1', source: 'entity:1', target: 'doc:44', link_type: 'semantic', score: 0.9, context: null };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [pageNode, targetNode], edges: [edge] }),
    }));
    const onFileSelect = vi.fn();
    renderGraphWithNavigation(onFileSelect);

    fireEvent.click(await screen.findByTestId('node-doc:44'));
    onFileSelect.mockClear();

    fireEvent.click(await screen.findByText('In passender Ansicht öffnen'));

    expect(onFileSelect).toHaveBeenCalledTimes(1);
    expect(onFileSelect).toHaveBeenCalledWith('https://confluence.test/RAUM/Fachkonzept', null, 4);
  });
});

describe('KnowledgeGraphView directed edge rendering (O-266)', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders arrows on directed code edges and suppresses arrows on undirected links', async () => {
    const nodeA: GraphNode = { id: 'entity:1', type: 'entity', label: 'PROG_A' };
    const nodeB: GraphNode = { id: 'entity:2', type: 'entity', label: 'PROG_B' };
    const directedEdge: GraphEdge = {
      id: 'code:101',
      source: 'entity:1',
      target: 'entity:2',
      link_type: 'CALLS',
      direction: 'directed',
      score: null,
      context: null,
    };
    const undirectedEdge: GraphEdge = {
      id: 'kl:202',
      source: 'entity:1',
      target: 'entity:2',
      link_type: 'CALLS',
      direction: 'undirected',
      score: 0.8,
      context: null,
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [nodeA, nodeB], edges: [directedEdge, undirectedEdge] }),
    }));

    renderGraph();

    const dirLinkEl = await screen.findByTestId('link-code:101');
    const undirLinkEl = await screen.findByTestId('link-kl:202');

    expect(Number(dirLinkEl.getAttribute('data-arrow-length'))).toBeGreaterThan(0);
    expect(Number(undirLinkEl.getAttribute('data-arrow-length'))).toBe(0);
  });

  it('applies curvature to opposing edges between the same two nodes', async () => {
    const nodeA: GraphNode = { id: 'entity:1', type: 'entity', label: 'PROG_A' };
    const nodeB: GraphNode = { id: 'entity:2', type: 'entity', label: 'PROG_B' };
    const forwardEdge: GraphEdge = {
      id: 'code:1',
      source: 'entity:1',
      target: 'entity:2',
      link_type: 'CALLS',
      direction: 'directed',
      score: null,
      context: null,
    };
    const reverseEdge: GraphEdge = {
      id: 'code:2',
      source: 'entity:2',
      target: 'entity:1',
      link_type: 'CALLS',
      direction: 'directed',
      score: null,
      context: null,
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [nodeA, nodeB], edges: [forwardEdge, reverseEdge] }),
    }));

    renderGraph();

    const forwardEl = await screen.findByTestId('link-code:1');
    const reverseEl = await screen.findByTestId('link-code:2');

    expect(Number(forwardEl.getAttribute('data-curvature'))).toBe(0.2);
    expect(Number(reverseEl.getAttribute('data-curvature'))).toBe(0.2);
  });

  it('positions arrow tips relative to target node perimeter when coordinates are present', async () => {
    const nodeA: GraphNode = { id: 'entity:1', type: 'entity', label: 'PROG_A', x: 0, y: 0 };
    const nodeB: GraphNode = { id: 'entity:2', type: 'entity', label: 'PROG_B', x: 100, y: 0 };
    const edge: GraphEdge = {
      id: 'code:1',
      source: nodeA,
      target: nodeB,
      link_type: 'CALLS',
      direction: 'directed',
      score: null,
      context: null,
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [nodeA, nodeB], edges: [edge] }),
    }));

    renderGraph();

    const linkEl = await screen.findByTestId('link-code:1');
    // Distance = 100px. Target radius for entity = 8px. Offset = 9px.
    // Relative position = 1 - 9/100 = 0.91
    const relPos = Number(linkEl.getAttribute('data-arrow-rel-pos'));
    expect(relPos).toBeCloseTo(0.91, 2);
  });
});

describe('KnowledgeGraphView isolated node filtering (O-285)', () => {
  beforeEach(() => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('keeps isolated inventory out of the relationship view', async () => {
    const linkedNode: GraphNode = { id: 'entity:1', type: 'entity', label: 'LINKED_PROG' };
    const docNode: GraphNode = { id: 'doc:1', type: 'document', label: 'Doc1' };
    const isolatedNode: GraphNode = { id: 'entity:2', type: 'entity', label: 'ISOLATED_PROG' };
    const edge: GraphEdge = { id: 'code:1', source: 'entity:1', target: 'doc:1', link_type: 'CALLS', direction: 'directed', score: null, context: null };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [linkedNode, docNode, isolatedNode],
        edges: [edge],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    renderGraph();

    // Connected nodes are rendered
    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    expect(screen.getByTestId('node-doc:1')).toBeTruthy();
    // Degree 0 node is hidden by default
    expect(screen.queryByTestId('node-entity:2')).toBeNull();

    // Inventory expansion is intentionally absent from the graph view.
    expect(screen.queryByTestId('toggle-only-linked')).toBeNull();
  });

  it('hiding a link type that disconnects a node hides that node when onlyLinked is active', async () => {
    const nodeA: GraphNode = { id: 'entity:1', type: 'entity', label: 'PROG_A' };
    const nodeB: GraphNode = { id: 'entity:2', type: 'entity', label: 'PROG_B' };
    const edge: GraphEdge = { id: 'code:1', source: 'entity:1', target: 'entity:2', link_type: 'CALLS', score: null, context: null };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nodes: [nodeA, nodeB],
        edges: [edge],
      }),
    }));

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    expect(screen.getByTestId('node-entity:2')).toBeTruthy();

    // Hide the CALLS link type chip
    const callsChip = screen.getAllByText('Aufruf')[0];
    fireEvent.click(callsChip);

    // When the only link is hidden, visible degree becomes 0 so both nodes are hidden
    await waitFor(() => {
      expect(screen.queryByTestId('node-entity:1')).toBeNull();
      expect(screen.queryByTestId('node-entity:2')).toBeNull();
    });
  });
});
