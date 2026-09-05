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
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { KnowledgeGraphView } from './KnowledgeGraphView';

const ForceGraph2DStub = React.forwardRef((props: any, ref: any) => {
  React.useImperativeHandle(ref, () => ({
    zoom: () => 1,
    centerAt: () => {},
    d3Force: () => undefined,
    d3ReheatSimulation: () => {},
    zoomToFit: () => {},
    graphData: () => ({ nodes: props.graphData.nodes, links: props.graphData.links }),
  }));
  return (
    <div data-testid="force-graph-stub">
      {props.graphData.nodes.map((node: any) => (
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
    queueMicrotask(() => this.cb([{ contentRect: { width: 800, height: 600 } }] as any, this as unknown as ResizeObserver));
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
    vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
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
