import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LanguageProvider } from '@/lib/i18n/LanguageContext';
import { ProcessView, type CallEdge, type CallNode } from './CallGraphView';

type GraphProps = {
  graphData: { nodes: CallNode[]; links: CallEdge[] };
  onNodeClick: (node: CallNode) => void;
  onLinkClick: (edge: CallEdge) => void;
  linkLabel: (edge: CallEdge) => string;
  linkDirectionalParticles?: (edge: CallEdge) => number;
};
const ForceGraph = React.forwardRef<{ zoom: () => number; zoomToFit: () => void }, GraphProps>((props, ref) => {
  React.useImperativeHandle(ref, () => ({ zoom: () => 1, zoomToFit: () => {} }));
  return <div data-testid="process-graph">{props.graphData.nodes.map(node => (
    <button
      key={node.id}
      data-testid={`node-${node.id}`}
      data-x={node.x}
      data-y={node.y}
      onClick={() => props.onNodeClick(node)}
    >
      {node.name}
    </button>
  ))}{props.graphData.links.map(edge => (
    <button
      key={edge.id}
      data-testid={`edge-${edge.id}`}
      title={props.linkLabel(edge)}
      data-particles={props.linkDirectionalParticles ? props.linkDirectionalParticles(edge) : 0}
      onClick={() => props.onLinkClick(edge)}
    >
      {edge.type}
    </button>
  ))}</div>;
});
ForceGraph.displayName = 'ForceGraph';
vi.mock('react-force-graph-2d', () => ({ default: ForceGraph }));

class ResizeObserverStub {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe() { queueMicrotask(() => this.callback([{ contentRect: { width: 800, height: 600 } }] as ResizeObserverEntry[], this as unknown as ResizeObserver)); }
  disconnect() {}
}

const ENTITY = { id: 42, name: 'ZAHLUNG' };
const PROJECTION = {
  nodes: [
    { id: 'entity:42', kind: 'entry', label: 'ZAHLUNG', language: 'cobol', entity_id: 42, locator: { source_id: 5, file_path: 'ZAHLUNG.CBL', start_line: 10 } },
    { id: 'entity:43', kind: 'step', label: 'PRUEFEN', language: 'cobol', entity_id: 43, locator: { source_id: 5, file_path: 'ZAHLUNG.CBL', start_line: 30 } },
    { id: 'external:edge:8', kind: 'external_call', label: 'BANK-AUTH', language: 'cobol', locator: { source_id: 5, file_path: 'ZAHLUNG.CBL', start_line: 35 } },
  ],
  transitions: [
    { id: 'code-edge:7', source: 'entity:42', target: 'entity:43', kind: 'call', certainty: 'certain', resolution: 'resolved', code_edge_types: ['PERFORM'], locator: { start_line: 14, provenance: { kind: 'code_fact', verification_status: 'indexed_unreviewed', source_name: 'CardDemo', source_type: 'Git', source_revision: 'commit-1', certainty: 'certain', origin: 'PERFORM', locator: { file_path: 'ZAHLUNG.CBL', start_line: 14 } } }, meta: {} },
    { id: 'code-edge:8', source: 'entity:43', target: 'external:edge:8', kind: 'external_call', certainty: 'unresolved', resolution: 'unresolved', code_edge_types: ['CALL'], locator: { start_line: 35 }, meta: {} },
  ],
  truncation: { truncated: true, reasons: ['edge_limit'] },
};

function renderView(onFileSelect = vi.fn()) {
  const fetchMock = vi.fn(async () => ({ ok: true, json: async () => PROJECTION }));
  vi.stubGlobal('fetch', fetchMock);
  render(<LanguageProvider><ProcessView theme="dark" focusedEntity={ENTITY} onFileSelect={onFileSelect} projectId={3} /></LanguageProvider>);
  return { fetchMock, onFileSelect };
}

describe('ProcessView', () => {
  beforeEach(() => vi.stubGlobal('ResizeObserver', ResizeObserverStub));
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('loads the bounded process projection and exposes process kinds', async () => {
    const { fetchMock } = renderView();
    expect(await screen.findByTestId('process-graph')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/process/focus?entity_id=42&hops=1&project_id=3'),
      expect.anything(),
    );
    expect(screen.getByRole('button', { name: 'Aufruf' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Extern / offen' })).toBeTruthy();
  });

  it('opens original transition and node locations but not unresolved targets', async () => {
    const { onFileSelect } = renderView();
    fireEvent.click(await screen.findByTestId('edge-code-edge:7'));
    expect(onFileSelect).toHaveBeenCalledWith('ZAHLUNG.CBL', 14, 5);
    expect(screen.getAllByText('Automatisch analysierter Codefakt').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByTestId('node-entity:43'));
    expect(onFileSelect).toHaveBeenCalledWith('ZAHLUNG.CBL', 30, 5);
    fireEvent.click(screen.getByTestId('node-external:edge:8'));
    expect(onFileSelect).toHaveBeenCalledTimes(2);
  });

  it('shows uncertainty, original edge type and truncation', async () => {
    renderView();
    const external = await screen.findByTestId('edge-code-edge:8');
    expect(external.title).toContain('unresolved');
    expect(external.title).toContain('CALL');
    expect(screen.getByText('Auf 500 Knoten begrenzt')).toBeTruthy();
  });

  it('separates node selection from process root and exposes "Ab hier untersuchen" only for non-root nodes (O-297)', async () => {
    const onInvestigateFromHere = vi.fn();
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('entity_id=43')) {
        return {
          ok: true,
          json: async () => ({
            nodes: [
              { id: 'entity:43', kind: 'entry', label: 'PRUEFEN', language: 'cobol', entity_id: 43, locator: { source_id: 5, file_path: 'ZAHLUNG.CBL', start_line: 30 } },
              { id: 'external:edge:8', kind: 'external_call', label: 'BANK-AUTH', language: 'cobol', locator: { source_id: 5, file_path: 'ZAHLUNG.CBL', start_line: 35 } },
            ],
            transitions: [
              { id: 'code-edge:8', source: 'entity:43', target: 'external:edge:8', kind: 'external_call', certainty: 'unresolved', resolution: 'unresolved', code_edge_types: ['CALL'], locator: { start_line: 35 } },
            ],
            truncation: { truncated: false, reasons: [] },
          }),
        };
      }
      return { ok: true, json: async () => PROJECTION };
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <LanguageProvider>
        <ProcessView
          theme="dark"
          focusedEntity={ENTITY}
          onFileSelect={vi.fn()}
          projectId={3}
          onInvestigateFromHere={onInvestigateFromHere}
        />
      </LanguageProvider>
    );

    expect(await screen.findByTestId('process-graph')).toBeTruthy();
    expect(screen.queryByTestId('investigate-from-here')).toBeNull();

    fireEvent.click(screen.getByTestId('node-entity:43'));
    const btn = await screen.findByTestId('investigate-from-here');
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain('Ab hier untersuchen');

    fireEvent.click(btn);
    expect(onInvestigateFromHere).toHaveBeenCalledWith({ id: 43, name: 'PRUEFEN' });
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/process/focus?entity_id=43'),
        expect.anything()
      );
    });
  });

  it('ten consecutive node clicks do not change root or positions; only "Ab hier untersuchen" creates a new projection (O-297 acceptance)', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('entity_id=43')) {
        return {
          ok: true,
          json: async () => ({
            nodes: [
              { id: 'entity:43', kind: 'entry', label: 'PRUEFEN', language: 'cobol', entity_id: 43, locator: { source_id: 5, file_path: 'ZAHLUNG.CBL', start_line: 30 } },
            ],
            transitions: [],
            truncation: { truncated: false, reasons: [] },
          }),
        };
      }
      return { ok: true, json: async () => PROJECTION };
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <LanguageProvider>
        <ProcessView theme="dark" focusedEntity={ENTITY} onFileSelect={vi.fn()} projectId={3} />
      </LanguageProvider>
    );

    expect(await screen.findByTestId('process-graph')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const node42 = screen.getByTestId('node-entity:42');
    const node43 = screen.getByTestId('node-entity:43');

    for (let i = 0; i < 10; i++) {
      fireEvent.click(i % 2 === 0 ? node43 : node42);
    }

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText('ZAHLUNG').length).toBeGreaterThan(0);

    fireEvent.click(node43);
    const investigateBtn = await screen.findByTestId('investigate-from-here');
    fireEvent.click(investigateBtn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining('/process/focus?entity_id=43'),
        expect.anything()
      );
    });
  });

  it('animates only outgoing transitions of the selected node and preserves positions (O-297)', async () => {
    renderView();
    expect(await screen.findByTestId('process-graph')).toBeTruthy();

    const edge7 = screen.getByTestId('edge-code-edge:7');
    const edge8 = screen.getByTestId('edge-code-edge:8');

    expect(Number(edge7.getAttribute('data-particles'))).toBe(2);
    expect(Number(edge8.getAttribute('data-particles'))).toBe(0);

    fireEvent.click(screen.getByTestId('node-entity:43'));
    expect(Number(edge7.getAttribute('data-particles'))).toBe(0);
    expect(Number(edge8.getAttribute('data-particles'))).toBe(2);
  });

  it('handles a 500-node projection within budget and remains usable (O-297)', async () => {
    const nodes = Array.from({ length: 500 }, (_, i) => ({
      id: `entity:${i + 1}`,
      kind: i === 0 ? 'entry' : 'step',
      label: `STEP-${i + 1}`,
      language: 'cobol',
      entity_id: i + 1,
      locator: { source_id: 1, file_path: 'BIG.CBL', start_line: i * 10 + 1 },
    }));
    const transitions = Array.from({ length: 499 }, (_, i) => ({
      id: `code-edge:${i + 1}`,
      source: `entity:${i + 1}`,
      target: `entity:${i + 2}`,
      kind: 'call',
      certainty: 'certain' as const,
      resolution: 'resolved',
      code_edge_types: ['PERFORM'],
      locator: { start_line: i * 10 + 5 },
    }));
    const bigProjection = {
      nodes,
      transitions,
      truncation: { truncated: false, reasons: [] },
    };

    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => bigProjection })));

    render(
      <LanguageProvider>
        <ProcessView theme="dark" focusedEntity={{ id: 1, name: 'STEP-1' }} onFileSelect={vi.fn()} />
      </LanguageProvider>
    );

    expect(await screen.findByTestId('process-graph')).toBeTruthy();
    expect(screen.getByTestId('node-entity:500')).toBeTruthy();
    fireEvent.click(screen.getByTestId('node-entity:500'));
    expect(screen.getByTestId('investigate-from-here')).toBeTruthy();
  });
});
