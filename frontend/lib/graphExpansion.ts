import type { GraphEdge, GraphNode } from './knowledgeGraphTypes';
import { graphEndId } from './knowledgeGraphRendering';

/** What one in-place expansion added, so collapsing removes exactly that again. */
export type GraphExpansion = { nodeIds: Set<string>; edgeIds: Set<string>; cursor: string | null; hasMore: boolean };
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };

/** In-place expansion uses GET /graph/neighborhood, which resolves files and documents. */
export function canExpandInPlace(node: GraphNode): boolean {
  return node.type === 'code_file' || node.type === 'document' || node.id.startsWith('doc:');
}

/** Connections of a node that exist on the server (`degree`) but are not loaded. */
export function hiddenEdgeCounts(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const loaded = new Map<string, number>();
  for (const edge of edges) {
    for (const end of [graphEndId(edge.source), graphEndId(edge.target)]) loaded.set(end, (loaded.get(end) ?? 0) + 1);
  }
  const hidden = new Map<string, number>();
  for (const node of nodes) {
    const missing = (node.degree ?? 0) - (loaded.get(node.id) ?? 0);
    if (missing > 0) hidden.set(node.id, missing);
  }
  return hidden;
}

/**
 * Adds a neighborhood page to the loaded graph. Known nodes keep their identity and position; new
 * nodes start on a spiral around the anchor, so the layout settles them next to it, not elsewhere.
 */
export function mergeExpansion(graph: GraphData, page: GraphData, anchor: { id: string; x?: number; y?: number },
  previous?: GraphExpansion): { graph: GraphData; added: GraphExpansion } {
  const knownNodes = new Set(graph.nodes.map(node => node.id));
  const knownEdges = new Set(graph.edges.map(edge => edge.id));
  const added: GraphExpansion = { nodeIds: new Set(previous?.nodeIds), edgeIds: new Set(previous?.edgeIds), cursor: null, hasMore: false };
  const ax = anchor.x ?? 0, ay = anchor.y ?? 0;
  const offset = added.nodeIds.size;
  const newNodes = page.nodes.filter(node => !knownNodes.has(node.id)).map((node, index) => {
    added.nodeIds.add(node.id);
    const slot = offset + index;
    const angle = slot * 2.39996;
    const distance = 260 + 70 * Math.sqrt(slot);
    return { ...node, x: ax + Math.cos(angle) * distance, y: ay + Math.sin(angle) * distance };
  });
  const present = new Set([...knownNodes, ...newNodes.map(node => node.id)]);
  const newEdges = page.edges.filter(edge => !knownEdges.has(edge.id)
    && present.has(graphEndId(edge.source)) && present.has(graphEndId(edge.target)));
  newEdges.forEach(edge => added.edgeIds.add(edge.id));
  return {
    graph: { nodes: newNodes.length ? [...graph.nodes, ...newNodes] : graph.nodes,
      edges: newEdges.length ? [...graph.edges, ...newEdges] : graph.edges },
    added,
  };
}

/**
 * Removes what an expansion added. Nodes stay when another expansion still connects them or when
 * they are themselves expanded, so collapsing one anchor never tears apart a later expansion.
 */
export function collapseExpansion(graph: GraphData, expansions: Map<string, GraphExpansion>, anchorId: string): GraphData {
  const expansion = expansions.get(anchorId);
  if (!expansion) return graph;
  const edges = graph.edges.filter(edge => !expansion.edgeIds.has(edge.id));
  const connected = new Set(edges.flatMap(edge => [graphEndId(edge.source), graphEndId(edge.target)]));
  const nodes = graph.nodes.filter(node => !expansion.nodeIds.has(node.id)
    || connected.has(node.id) || (node.id !== anchorId && expansions.has(node.id)));
  return { nodes, edges };
}
