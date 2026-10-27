import type { GraphEdge, GraphNode } from './knowledgeGraphTypes';
import { NEIGHBORHOOD_LAYER_GAP, NEIGHBORHOOD_ROW_GAP } from './graphLayout';

const endId = (end: GraphEdge['source']) => typeof end === 'object' ? end.id : end;
const directed = (edge: GraphEdge) => edge.direction
  ? edge.direction !== 'undirected' : /^(code:|edl:|ref:)/.test(edge.id);

/** d3 owns mutable positions/endpoints; keep them separate from React's API state. */
export function createGraphScene<T extends { nodes: GraphNode[]; links: GraphEdge[] }>(data: T): T {
  const nodes = data.nodes.map(node => ({ ...node }));
  const byId = new Map(nodes.map(node => [node.id, node]));
  const links = data.links.map(edge => ({ ...edge,
    source: byId.get(endId(edge.source))!, target: byId.get(endId(edge.target))! }));
  return { ...data, nodes, links };
}

/** Each edge is indexed once, each reachable node is visited once. Cycles are safe. */
export function neighborhoodPositions(nodes: GraphNode[], links: GraphEdge[], root: string,
  direction: 'incoming' | 'outgoing' | 'both') {
  const neighbors = new Map<string, string[]>();
  function add(from: string, to: string) {
    if (!neighbors.has(from)) neighbors.set(from, []);
    neighbors.get(from)!.push(to);
  }
  for (const edge of links) {
    const source = endId(edge.source), target = endId(edge.target);
    if (!directed(edge) || direction === 'both' || direction === 'outgoing') add(source, target);
    if (!directed(edge) || direction === 'both' || direction === 'incoming') add(target, source);
  }
  const layers = new Map([[root, 0]]);
  const queue = [root];
  for (let i = 0; i < queue.length; i++) {
    for (const next of neighbors.get(queue[i]) ?? []) {
      if (layers.has(next)) continue;
      layers.set(next, layers.get(queue[i])! + 1);
      queue.push(next);
    }
  }
  const counts = new Map<number, number>();
  const positions = new Map<string, { x: number; y: number }>();
  for (const node of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    const layer = layers.get(node.id) ?? 0;
    const index = counts.get(layer) ?? 0;
    counts.set(layer, index + 1);
    positions.set(node.id, { x: (direction === 'incoming' ? -1 : 1) * layer * NEIGHBORHOOD_LAYER_GAP,
      y: index * NEIGHBORHOOD_ROW_GAP });
  }
  return positions;
}

export type LayoutNode = { id: string; degree: number; radius: number; x?: number; y?: number; fx?: number; fy?: number };
export type LayoutRequest = { nodes: LayoutNode[]; links: { source: string; target: string }[] };
export type LayoutResult = { positions: { id: string; x: number; y: number }[]; done: boolean };

/** Deterministic spacing before the first worker result, rather than a dense origin cloud. */
export function seedPositions(nodes: LayoutNode[]) {
  const spacing = 200;
  const width = Math.ceil(Math.sqrt(nodes.length));
  nodes.forEach((node, index) => {
    if (node.fx != null && node.fy != null) {
      node.x = node.fx;
      node.y = node.fy;
    } else if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) {
      node.x = ((index % width) - width / 2) * spacing;
      node.y = (Math.floor(index / width) - width / 2) * spacing;
    }
  });
}
