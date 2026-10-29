import type { GraphEdge, GraphNode } from './knowledgeGraphTypes';
import { graphEndId } from './knowledgeGraphRendering';

/** What one in-place expansion added, so collapsing removes exactly that again. */
export type GraphExpansion = { nodeIds: Set<string>; edgeIds: Set<string>; cursor: string | null; hasMore: boolean };
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[] };

/** In-place expansion uses GET /graph/neighborhood, which resolves files and documents. */
export function canExpandInPlace(node: GraphNode): boolean {
  return node.type === 'code_file' || node.type === 'document' || node.id.startsWith('doc:');
}

/**
 * What a node hides: for a group its contents, for other nodes the connections that exist on the
 * server (`degree`) but are not loaded individually. Bundled edges into a collapsed group count as
 * hidden, since they do not show which object is connected.
 */
export function hiddenEdgeCounts(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const loaded = new Map<string, number>();
  for (const edge of edges) {
    if (edge.meta?.bundled) continue;
    for (const end of [graphEndId(edge.source), graphEndId(edge.target)]) loaded.set(end, (loaded.get(end) ?? 0) + 1);
  }
  const hidden = new Map<string, number>();
  for (const node of nodes) {
    if (node.type === 'group') {
      const contents = (node.file_count ?? 0) + (node.doc_count ?? 0);
      if (contents > 0) hidden.set(node.id, contents);
      continue;
    }
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

// Abstand der Startplätze aufgeklappter Inhalte (Sonnenblumen-Spirale): so dicht, wie die
// Kollisionsabstände des Layouts es ohnehin zulassen.
const GROUP_SEED_GAP = 90;

const insideGroup = (parent: string | null | undefined, key: string) => parent === key || !!parent?.startsWith(`${key}.`);

/** Collapsing removes the group itself and every expanded subgroup below it. */
export function collapseGroupKeys(expanded: string[], key: string): string[] {
  return expanded.filter(k => k !== key && !k.startsWith(`${key}.`));
}

/**
 * Start positions after expanding or collapsing a group: what the layout already placed keeps its
 * position, the contents of an expanded group start around the spot where the group was, and a
 * collapsed group returns to the centre of what it contained.
 */
export function seedGroupPositions(nodes: GraphNode[], previous: GraphNode[], collapsedKey?: string | null): GraphNode[] {
  const placed = new Map(previous.filter(n => n.x != null && n.y != null).map(n => [n.id, n]));
  const slots = new Map<string, number>();
  return nodes.map(node => {
    if (placed.has(node.id)) return node;
    if (collapsedKey && node.type === 'group' && node.group_key === collapsedKey) {
      const inside = previous.filter(n => n.x != null && n.y != null && insideGroup(n.group_parent, collapsedKey));
      if (!inside.length) return node;
      return { ...node, x: inside.reduce((sum, n) => sum + n.x!, 0) / inside.length,
        y: inside.reduce((sum, n) => sum + n.y!, 0) / inside.length };
    }
    const parent = node.group_parent ? placed.get(`group:${node.group_parent}`) : undefined;
    if (!parent) return node;
    const slot = slots.get(parent.id) ?? 0;
    slots.set(parent.id, slot + 1);
    const angle = slot * 2.39996, distance = GROUP_SEED_GAP * Math.sqrt(slot + 1);
    return { ...node, x: parent.x! + Math.cos(angle) * distance, y: parent.y! + Math.sin(angle) * distance };
  });
}
