type EndRef = string | { id: string };

const endId = (end: EndRef) => (typeof end === 'object' ? end.id : end);

/**
 * Blendet Knoten und Kanten nach den Legenden-Filtern aus.
 *
 * "Nur verknüpfte" betrachtet die Kanten vor dem Ausblenden von Knotenarten: Ein Jira-Ticket, dessen
 * einzige Verbindung zu einer ausgeblendeten Code-Datei führt, bleibt sichtbar. Sonst verschwände der
 * ganze Graph, sobald man die Art ausblendet, an der die übrigen Knoten hängen.
 */
export function filterVisibleGraph<N extends { id: string }, E extends { source: EndRef; target: EndRef }>(
  nodes: N[],
  edges: E[],
  options: { isNodeHidden: (node: N) => boolean; isEdgeHidden: (edge: E) => boolean; onlyLinked: boolean },
): { nodes: N[]; links: E[] } {
  const candidateNodes = nodes.filter(node => !options.isNodeHidden(node));
  const candidateIds = new Set(candidateNodes.map(node => node.id));
  const shownByFilter = edges.filter(edge => !options.isEdgeHidden(edge));
  const links = shownByFilter.filter(edge => candidateIds.has(endId(edge.source)) && candidateIds.has(endId(edge.target)));
  if (!options.onlyLinked) return { nodes: candidateNodes, links };

  const connected = new Set<string>();
  for (const edge of shownByFilter) {
    connected.add(endId(edge.source));
    connected.add(endId(edge.target));
  }
  return { nodes: candidateNodes.filter(node => connected.has(node.id)), links };
}
