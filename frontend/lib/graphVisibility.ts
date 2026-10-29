type EndRef = string | { id: string };

const endId = (end: EndRef) => (typeof end === 'object' ? end.id : end);

/**
 * Blendet Knoten und Kanten nach den Legenden-Filtern aus.
 *
 * Ausgeblendete Knotenarten verschwinden nicht spurlos: Ein ausgeblendeter Knoten, der über eine
 * sichtbare Kante mit einem sichtbaren Knoten verbunden ist, bleibt als Platzhalter ("ghost") im Graphen
 * und wird nur ausgegraut gezeichnet. So sieht man, womit ein System verwoben ist, auch wenn dessen
 * Knotenart ausgeblendet ist (z. B. Jira-Tickets mit ihren Code-Dateien). Kanten zwischen zwei
 * Platzhaltern entfallen.
 *
 * "Nur verknüpfte" entfernt Knoten ohne jede Verbindung; ausgeblendete Nachbarn zählen dabei mit.
 * Erkenntnisse, Gruppen und der Inhalt aufgeklappter Gruppen bleiben auch ohne Verbindung: Sie sind
 * Teil des Bestands, den man auf- und zuklappt, auch wenn gerade keine Kante sichtbar ist.
 */
export function filterVisibleGraph<N extends { id: string; type?: string; group_parent?: string | null }, E extends { source: EndRef; target: EndRef }>(
  nodes: N[],
  edges: E[],
  options: { isNodeHidden: (node: N) => boolean; isEdgeHidden: (edge: E) => boolean; onlyLinked: boolean },
): { nodes: N[]; links: E[]; ghostIds: Set<string> } {
  const shownByFilter = edges.filter(edge => !options.isEdgeHidden(edge));
  const solidIds = new Set(nodes.filter(node => !options.isNodeHidden(node)).map(node => node.id));
  const ghostIds = new Set<string>();
  for (const edge of shownByFilter) {
    const [src, tgt] = [endId(edge.source), endId(edge.target)];
    if (solidIds.has(src) && !solidIds.has(tgt)) ghostIds.add(tgt);
    if (solidIds.has(tgt) && !solidIds.has(src)) ghostIds.add(src);
  }

  const keptIds = new Set([...solidIds, ...ghostIds]);
  const links = shownByFilter.filter(edge => {
    const [src, tgt] = [endId(edge.source), endId(edge.target)];
    return keptIds.has(src) && keptIds.has(tgt) && (solidIds.has(src) || solidIds.has(tgt));
  });
  const candidates = nodes.filter(node => keptIds.has(node.id));
  if (!options.onlyLinked) return { nodes: candidates, links, ghostIds };

  const connected = new Set<string>();
  for (const edge of shownByFilter) {
    connected.add(endId(edge.source));
    connected.add(endId(edge.target));
  }
  const alwaysShown = (node: N) => (node.type === 'insight' || node.type === 'group' || !!node.group_parent) && solidIds.has(node.id);
  return { nodes: candidates.filter(node => connected.has(node.id) || alwaysShown(node)), links, ghostIds };
}
