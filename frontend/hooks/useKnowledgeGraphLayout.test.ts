import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ForceGraphMethods } from 'react-force-graph-2d';
import { useKnowledgeGraphLayout } from './useKnowledgeGraphLayout';
import type { GraphNode, GraphEdge } from '@/lib/knowledgeGraphTypes';
import type { LayoutRequest, LayoutResult } from '@/lib/knowledgeGraphLayout';
import { createGraphScene } from '@/lib/knowledgeGraphLayout';

class WorkerStub {
  static instances: WorkerStub[] = [];
  onmessage?: (event: MessageEvent<LayoutResult>) => void;
  onerror?: (event: ErrorEvent) => void;
  postMessage = vi.fn<(request: LayoutRequest) => void>();
  terminate = vi.fn();
  constructor() { WorkerStub.instances.push(this); }
  reply(x: number, done = true) {
    this.onmessage?.({ data: { done, positions: [{ id: 'a', x, y: 10 }] } } as MessageEvent<LayoutResult>);
  }
}

function setup() {
  WorkerStub.instances = [];
  vi.stubGlobal('Worker', WorkerStub);
  const graph = { d3Force: vi.fn(), d3ReheatSimulation: vi.fn() };
  const graphRef = { current: graph as unknown as ForceGraphMethods<GraphNode, GraphEdge> };
  const nodes: GraphNode[] = [{ id: 'a', type: 'entity', label: 'A' }, { id: 'b', type: 'entity', label: 'B' }];
  const links: GraphEdge[] = [{ id: 'e', source: 'a', target: 'b', link_type: 'manual', score: null, context: null }];
  const scene = createGraphScene({ nodes, links });
  const props = { graphRef, ready: true, ...scene, degrees: new Map<string, number>(),
    mode: 'overview' as const, direction: 'both' as const };
  const hook = renderHook(options => useKnowledgeGraphLayout(options), { initialProps: props });
  return { ...hook, props, graph, ...scene, worker: WorkerStub.instances[0] };
}

afterEach(() => vi.unstubAllGlobals());

describe('knowledge graph worker lifecycle', () => {
  it('binds string endpoints and applies worker positions without main-thread force ticks', () => {
    const { nodes, links, worker, graph } = setup();
    expect(links[0].source).toBe(nodes[0]);
    expect(graph.d3Force).toHaveBeenCalledWith('charge', null);
    act(() => worker.reply(450));
    expect(nodes[0]).toMatchObject({ x: 450, y: 10, fx: 450, fy: 10 });
    expect(worker.terminate).toHaveBeenCalled();
  });

  it('terminates obsolete work and ignores late replies after switching the dataset', () => {
    const { rerender, props, worker, nodes } = setup();
    rerender({ ...props, nodes: [{ id: 'c', type: 'entity', label: 'C' }], links: [] });
    const oldX = nodes[0].x;
    act(() => worker.reply(999));
    expect(worker.terminate).toHaveBeenCalled();
    expect(nodes[0].x).toBe(oldX);
  });

  it('keeps a position changed by dragging instead of overwriting it with a worker reply', () => {
    const { worker, nodes } = setup();
    act(() => worker.reply(450, false));
    Object.assign(nodes[0], { x: 700, y: 800, fx: 700, fy: 800 });
    act(() => worker.reply(999));
    expect(nodes[0]).toMatchObject({ x: 700, y: 800, fx: 700, fy: 800 });
  });

  it('terminates a worker when its view unmounts', () => {
    const { unmount, worker } = setup();
    unmount();
    expect(worker.terminate).toHaveBeenCalled();
  });

  it('restarts unfinished layout after a filter reset instead of caching seed positions as final', () => {
    const { rerender, props, worker } = setup();
    const scene = createGraphScene({ nodes: [
      { id: 'a', type: 'entity' as const, label: 'A' }, { id: 'b', type: 'entity' as const, label: 'B' },
    ], links: [{ ...props.links[0], source: 'a', target: 'b' }] });
    rerender({ ...props, ...scene });
    expect(worker.terminate).toHaveBeenCalled();
    expect(WorkerStub.instances).toHaveLength(2);
    act(() => WorkerStub.instances[1].reply(450));
    expect((scene.nodes[0] as GraphNode).x).toBe(450);
  });
});
