import { describe, expect, it } from 'vitest';
import type { CallFlowData } from './callFlow';
import { citeLocation, connectorPath, flowToDrop, layerWidthPercent, sameLayerPath, toggleExpanded, toggleKind } from './dropView';

describe('dropView', () => {
  it('keeps at least one edge kind and a fixed order', () => {
    expect(toggleKind(['control'], 'control')).toEqual(['control']);
    expect(toggleKind(['control'], 'includes')).toEqual(['control', 'includes']);
    expect(toggleKind(['data', 'includes'], 'control')).toEqual(['control', 'data', 'includes']);
  });
  it('widens the layers like a pyramid and never exceeds the container', () => {
    const widths = [0, 1, 2, 3].map(layer => layerWidthPercent(layer, 3));
    expect(widths).toEqual([...widths].sort((a, b) => a - b));
    expect(widths[0]).toBeLessThan(widths[3]);
    expect(Math.max(...widths)).toBe(100);
    expect(layerWidthPercent(0, 0)).toBe(100);
  });
  it('toggles expanded layers in a stable order', () => {
    expect(toggleExpanded([3], 1)).toEqual([1, 3]);
    expect(toggleExpanded([1, 3], 1)).toEqual([3]);
  });
});

describe('connectorPath', () => {
  const box = (left: number, top: number) => ({ left, top, right: left + 100, bottom: top + 20 });
  const base = { left: 10, top: 10 };

  it('verbindet untereinander vom unteren zum oberen Rand', () => {
    expect(connectorPath(box(10, 10), box(10, 110), base, 'vertical')).toEqual({ d: 'M 50 20 C 50 60, 50 60, 50 100', reversed: false });
  });

  it('verbindet nebeneinander vom rechten zum linken Rand', () => {
    expect(connectorPath(box(10, 10), box(210, 10), base, 'horizontal')).toEqual({ d: 'M 100 10 C 150 10, 150 10, 200 10', reversed: false });
  });

  it('merkt sich, wenn das Ziel vor der Quelle liegt, und zeichnet immer vorwärts', () => {
    const path = connectorPath(box(210, 10), box(10, 10), base, 'horizontal');
    expect(path?.reversed).toBe(true);
    expect(path?.d.startsWith('M 100 10')).toBe(true);
  });

  it('zeichnet nichts zwischen Knoten, die sich in Laufrichtung überlappen', () => {
    expect(connectorPath(box(10, 10), box(50, 100), base, 'horizontal')).toBeNull();
    expect(connectorPath(box(10, 10), box(200, 15), base, 'vertical')).toBeNull();
  });
});


describe('sameLayerPath', () => {
  const box = (left: number, top: number) => ({ left, right: left + 100, top, bottom: top + 20 });
  const base = { left: 0, top: 0 };

  it('arcs over neighbours when stacked and past them when side by side', () => {
    expect(sameLayerPath(box(0, 50), box(200, 50), base, 'vertical')).toBe('M 50 50 C 50 10, 250 10, 250 50');
    expect(sameLayerPath(box(0, 0), box(0, 100), base, 'horizontal')).toBe('M 100 10 C 133.33333333333334 10, 133.33333333333334 110, 100 110');
  });

  it('draws a loop when a node points at itself', () => {
    expect(sameLayerPath(box(0, 50), box(0, 50), base, 'vertical')).toBe('M 42 50 C 42 36, 58 36, 58 50');
  });
});

describe('citeLocation', () => {
  it('splits path and line, line 0 means unknown, a missing path yields nothing', () => {
    expect(citeLocation('src/a:b.cbl:12')).toEqual({ path: 'src/a:b.cbl', line: 12 });
    expect(citeLocation('src/a.cbl:0')).toEqual({ path: 'src/a.cbl', line: null });
    expect(citeLocation('None:0')).toBeNull();
    expect(citeLocation('')).toBeNull();
  });
});

describe('flowToDrop', () => {
  const flowNode = (id: number, name: string) => ({ id, name, type: 'paragraph', file_path: `${name}.cbl`, start_line: id });
  const flowEdge = (id: number, source: number, target: number | null, target_name = '') => ({ id, source, target, target_name, type: 'PERFORM', resolution: target == null ? 'unresolved' : 'resolved' });
  const flow = (overrides: Partial<CallFlowData>): CallFlowData => ({ root: flowNode(1, 'A'), hops: 2, direction: 'outgoing', truncated: false, nodes: [flowNode(1, 'A'), flowNode(2, 'B'), flowNode(3, 'C')], edges: [], ...overrides });
  const names = (result: ReturnType<typeof flowToDrop>) => result.layers.map(layer => layer.nodes.map(node => node.name));

  it('layers along the flow and keeps a cycle apart instead of placing its end next to the root', () => {
    const result = flowToDrop(flow({ edges: [flowEdge(10, 1, 2), flowEdge(11, 2, 3), flowEdge(12, 3, 1)] }));
    expect(names(result)).toEqual([['A'], ['B'], ['C']]);
    expect(result.layers[2].edges.map(edge => edge.id)).toEqual([11]);
    expect(result.back_edges?.map(edge => edge.id)).toEqual([12]);
  });

  it('walks against the edges for incoming flows', () => {
    const result = flowToDrop(flow({ direction: 'incoming', edges: [flowEdge(10, 2, 1), flowEdge(11, 3, 2)] }));
    expect(names(result)).toEqual([['A'], ['B'], ['C']]);
    expect(result.back_edges).toEqual([]);
    expect(result.direction).toBe('up');
  });

  it('shows an unresolved target as its own node and never loses an unconnected one', () => {
    const result = flowToDrop(flow({ edges: [flowEdge(10, 1, null, 'UNBEKANNT')] }));
    expect(names(result)).toEqual([['A'], ['UNBEKANNT'], ['B', 'C']]);
    const open = result.layers[1].nodes[0];
    expect(open).toMatchObject({ id: -10, unresolved: true, file_path: '' });
    expect(result.layers[1].edges[0]).toMatchObject({ from: 1, to: -10, cite: 'A.cbl:1' });
  });
});
