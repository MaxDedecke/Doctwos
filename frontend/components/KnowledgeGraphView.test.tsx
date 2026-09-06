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

type GraphStubProps = { graphData: { nodes: GraphNode[]; links: GraphEdge[] }; onNodeClick: (node: GraphNode) => void };
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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [node], edges: [] }),
    }));
    renderGraph();
    fireEvent.click(await screen.findByTestId('node-entity:1'));
    // The force simulation mutates these same objects after the initial selection.
    node.x = 12;
    node.y = 34;
    await waitFor(() => expect(centerAt).toHaveBeenCalledWith(12, 34, 800));
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
        nodes: [{ id: 'entity:1', type: 'entity', label: 'PROG1' }],
        edges: [],
        truncated: false,
        total_nodes: 1,
        total_edges: 0,
      }),
    }));

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    expect(screen.queryByText(/Zu groß für die Übersicht/)).toBeNull();
  });

  it('loads the real neighborhood via GET /graph/focus and replaces the (possibly truncated) overview', async () => {
    const overviewResponse = {
      nodes: [{ id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 }],
      edges: [],
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

  it('going back to the overview after a neighborhood focus re-fetches GET /graph', async () => {
    const overviewResponse = {
      nodes: [{ id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 }],
      edges: [],
      truncated: false,
      total_nodes: 1,
      total_edges: 0,
    };
    const focusResponse = {
      focus_id: 'entity:1',
      nodes: [{ id: 'entity:1', type: 'entity', label: 'PROG1', project_id: 1 }],
      edges: [],
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => overviewResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => focusResponse })
      .mockResolvedValueOnce({ ok: true, json: async () => overviewResponse });
    vi.stubGlobal('fetch', fetchMock);

    renderGraph();

    await waitFor(() => expect(screen.getByTestId('node-entity:1')).toBeTruthy());
    fireEvent.click(screen.getByTestId('node-entity:1'));
    fireEvent.click(await screen.findByText('Nur Nachbarschaft laden'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    fireEvent.click(await screen.findByText('Zurück zur Übersicht'));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(String(fetchMock.mock.calls[2][0])).toContain('/graph?');
    await waitFor(() => expect(screen.queryByText('Zurück zur Übersicht')).toBeNull());
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
      json: async () => ({ nodes: [docNode], edges: [] }),
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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nodes: [pageNode], edges: [] }),
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
