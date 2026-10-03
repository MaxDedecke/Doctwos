/**
 * O-381: Pfade für die Fluss-Animation der Process View.
 *
 * Gezeigt wird nur, was der Backendvertrag als Übergang liefert: jede Kante gehört zu einem
 * sichtbaren Übergang, es werden keine Kanten ergänzt. Ein Pfad ist die Folge von Kanten-IDs von der
 * Wurzel bis zu einem Knoten ohne weiteren Ausgang, bis zur Tiefengrenze oder bis zum Schließen eines
 * Zyklus (die schließende Kante gehört noch dazu, danach endet der Pfad: genau eine Runde).
 */

export type FlowLink = {
  id: string;
  source: string;
  target: string;
  sequence?: number | null;
};

export type FlowPaths = {
  /** Kanten-IDs je Pfad, in Reihenfolge der Durchläufe (zuerst die Ablaufreihenfolge `sequence`). */
  paths: string[][];
  /** true, wenn Pfadanzahl, Tiefe oder Suchaufwand begrenzt haben; es werden dann nicht alle Pfade gezeigt. */
  truncated: boolean;
};

export const FLOW_MAX_DEPTH = 14;
export const FLOW_MAX_PATHS = 24;
export const FLOW_MAX_EXPANSIONS = 5000;

type Limits = { maxDepth?: number; maxPaths?: number; maxExpansions?: number };

export function buildFlowPaths(links: FlowLink[], rootId: string, limits: Limits = {}): FlowPaths {
  const maxDepth = limits.maxDepth ?? FLOW_MAX_DEPTH;
  const maxPaths = limits.maxPaths ?? FLOW_MAX_PATHS;
  const maxExpansions = limits.maxExpansions ?? FLOW_MAX_EXPANSIONS;

  const outgoing = new Map<string, FlowLink[]>();
  for (const link of links) {
    if (link.source === link.target) continue; // Selbstschleifen tragen keinen Fluss
    const list = outgoing.get(link.source);
    if (list) list.push(link);
    else outgoing.set(link.source, [link]);
  }
  for (const list of outgoing.values()) {
    list.sort((a, b) => {
      const left = a.sequence ?? Number.POSITIVE_INFINITY;
      const right = b.sequence ?? Number.POSITIVE_INFINITY;
      return left === right ? a.id.localeCompare(b.id) : left - right;
    });
  }

  const paths: string[][] = [];
  const seen = new Set<string>();
  let truncated = false;
  let expansions = 0;

  const record = (path: string[]) => {
    if (path.length === 0) return;
    const key = path.join('>');
    if (seen.has(key)) return;
    seen.add(key);
    paths.push(path);
  };

  const walk = (node: string, edgeIds: string[], onPath: Set<string>): void => {
    if (paths.length >= maxPaths) {
      truncated = true;
      return;
    }
    const next = outgoing.get(node) ?? [];
    if (next.length === 0) {
      record(edgeIds);
      return;
    }
    if (edgeIds.length >= maxDepth) {
      truncated = true;
      record(edgeIds);
      return;
    }
    for (const link of next) {
      expansions += 1;
      if (expansions > maxExpansions) {
        truncated = true;
        return;
      }
      if (paths.length >= maxPaths) {
        truncated = true;
        return;
      }
      const extended = [...edgeIds, link.id];
      if (onPath.has(link.target)) {
        record(extended); // Zyklus: die schließende Kante zeigen, dann enden
        continue;
      }
      onPath.add(link.target);
      walk(link.target, extended, onPath);
      onPath.delete(link.target);
    }
  };

  walk(rootId, [], new Set([rootId]));
  return { paths, truncated };
}

export type FlowCursor = { path: number; step: number };

/**
 * Nächster Zustand der Dauerschleife. `step` zählt die bereits gezeigten Kanten des Pfads
 * (0 = noch keine). Nach der letzten Kante hält der Pfad einen Takt, dann beginnt der nächste;
 * mit `fixedPath` bleibt es bei einem Pfad.
 */
export function nextFlowCursor(paths: string[][], cursor: FlowCursor, fixedPath: number | null): FlowCursor {
  if (paths.length === 0) return { path: 0, step: 0 };
  const path = fixedPath != null ? Math.min(fixedPath, paths.length - 1) : Math.min(cursor.path, paths.length - 1);
  const length = paths[path].length;
  if (cursor.step < length) return { path, step: cursor.step + 1 };
  if (fixedPath != null) return { path, step: 0 };
  return { path: (path + 1) % paths.length, step: 0 };
}

export type FlowView = {
  activeEdgeId: string | null;
  trailEdgeIds: Set<string>;
  activeNodeId: string | null;
  trailNodeIds: Set<string>;
};

/** Welche Kanten/Knoten zum aktuellen Takt hervorgehoben werden. */
export function flowView(
  paths: string[][],
  cursor: FlowCursor,
  endpoints: Map<string, { source: string; target: string }>,
  rootId: string,
): FlowView {
  const view: FlowView = { activeEdgeId: null, trailEdgeIds: new Set(), activeNodeId: null, trailNodeIds: new Set([rootId]) };
  const path = paths[cursor.path];
  if (!path || cursor.step <= 0) {
    view.activeNodeId = rootId;
    return view;
  }
  for (let index = 0; index < Math.min(cursor.step, path.length); index += 1) {
    const edge = endpoints.get(path[index]);
    if (!edge) continue;
    view.trailEdgeIds.add(path[index]);
    view.trailNodeIds.add(edge.source);
    view.trailNodeIds.add(edge.target);
    view.activeEdgeId = path[index];
    view.activeNodeId = edge.target;
  }
  return view;
}
