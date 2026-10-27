import { useEffect, useRef, type RefObject } from 'react';
import type { ForceGraphMethods } from 'react-force-graph-2d';
import type { GraphNode, GraphEdge } from '@/lib/knowledgeGraphTypes';
import { graphEndId, nodeRadius } from '@/lib/knowledgeGraphRendering';
import { neighborhoodPositions, seedPositions, type LayoutRequest, type LayoutResult } from '@/lib/knowledgeGraphLayout';

type Options = {
  graphRef: RefObject<ForceGraphMethods<GraphNode, GraphEdge> | undefined>;
  ready: boolean; nodes: GraphNode[]; links: GraphEdge[]; degrees: Map<string, number>;
  mode: 'overview' | 'neighborhood'; focusId?: string;
  direction: 'incoming' | 'outgoing' | 'both';
};

export function useKnowledgeGraphLayout({ graphRef, ready, nodes, links, degrees, mode, focusId, direction }: Options) {
  const cached = useRef(new Map<string, { x: number; y: number }>());
  useEffect(() => {
    if (!ready || !nodes.length || !graphRef.current) return;
    const graph = graphRef.current;
    let active = true;
    let worker: Worker | undefined;
    let cancelFallback: (() => void) | undefined;
    const byId = new Map(nodes.map(node => [node.id, node]));
    const lastApplied = new Map<string, { x: number; y: number }>();
    // Physics is computed outside the renderer. A reheat now requests a paint, not a force tick.
    for (const force of ['charge', 'collide', 'radial', 'link', 'center']) graph.d3Force(force, null);
    function apply(result: LayoutResult) {
      if (!active) return;
      for (const position of result.positions) {
        const node = byId.get(position.id);
        if (!node) continue;
        const previous = lastApplied.get(node.id);
        if (previous && (node.fx !== previous.x || node.fy !== previous.y)) {
          if (mode === 'overview' && node.fx != null && node.fy != null) {
            cached.current.set(node.id, { x: node.fx, y: node.fy });
          }
          continue;
        }
        Object.assign(node, { x: position.x, y: position.y, fx: position.x, fy: position.y });
        lastApplied.set(node.id, position);
        if (mode === 'overview' && result.done) cached.current.set(node.id, position);
      }
      graph.d3ReheatSimulation();
    }
    if (mode === 'neighborhood' && focusId) {
      const positions = neighborhoodPositions(nodes, links, focusId, direction);
      apply({ done: true, positions: [...positions].map(([id, position]) => ({ id, ...position })) });
      return () => { active = false; };
    }
    // Keep only the current overview, rather than retaining every project ever visited.
    for (const id of cached.current.keys()) if (!byId.has(id)) cached.current.delete(id);
    const request: LayoutRequest = {
      nodes: nodes.map(node => {
        const position = cached.current.get(node.id);
        return { id: node.id, degree: degrees.get(node.id) ?? 0,
          radius: nodeRadius(node, degrees.get(node.id) ?? 0),
          ...(position ? { x: position.x, y: position.y, fx: position.x, fy: position.y }
            : { x: node.x, y: node.y, fx: node.fx, fy: node.fy }) };
      }),
      links: links.map(edge => ({ source: graphEndId(edge.source), target: graphEndId(edge.target) })),
    };
    seedPositions(request.nodes);
    apply({ done: false, positions: request.nodes.map(node => ({ id: node.id, x: node.x!, y: node.y! })) });
    if (request.nodes.every(node => node.fx != null && node.fy != null)) return () => { active = false; };
    const fallback = () => {
      worker?.terminate();
      import('@/lib/knowledgeGraphSimulation').then(({ simulateGraph }) => {
        if (active) cancelFallback = simulateGraph(request, apply);
      });
    };
    try {
      if (typeof Worker === 'undefined') fallback();
      else {
        worker = new Worker(new URL('../lib/knowledgeGraph.worker.ts', import.meta.url), { type: 'module' });
        worker.onmessage = (event: MessageEvent<LayoutResult>) => {
          apply(event.data);
          if (event.data.done) worker?.terminate();
        };
        worker.onerror = event => { event.preventDefault(); fallback(); };
        worker.postMessage(request);
      }
    } catch { fallback(); }
    return () => { active = false; worker?.terminate(); cancelFallback?.(); };
  }, [graphRef, ready, nodes, links, degrees, mode, focusId, direction]);
}
