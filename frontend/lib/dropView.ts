/** Drop-Ansicht (O-387): Typen und reine Hilfen; die Daten liefert `GET /entities/{id}/drop` (wie das MCP-Werkzeug `drop`). */

export type DropKind = 'control' | 'data' | 'includes';
export type DropDirection = 'down' | 'up';

export const DROP_KINDS: DropKind[] = ['control', 'data', 'includes'];
export const DROP_DEFAULT_LAYERS = 3;
export const DROP_MAX_LAYERS = 6;

export interface DropNode {
  id: number;
  name: string;
  qualified_name?: string | null;
  type: string;
  role?: 'container' | 'routine' | 'data' | null;
  source_id?: number | null;
  file_path: string;
  start_line?: number | null;
  cite: string;
  layer: number;
}

export interface DropEdge {
  from: number;
  to: number;
  type: string;
  resolution: string;
  cite: string;
}

export interface DropLayer {
  layer: number;
  count: number;
  unresolved: number;
  nodes: DropNode[];
  edges: DropEdge[];
  collapsed?: boolean;
  truncated?: boolean;
}

export interface DropResult {
  root: DropNode;
  direction: DropDirection;
  kinds: DropKind[];
  layers: DropLayer[];
  stopped: 'end' | 'collapsed' | null;
  collapse_above: number;
}

/** Schaltet eine Kantenart um; mindestens eine bleibt aktiv, die Reihenfolge ist stets die feste der Liste. */
export function toggleKind(active: DropKind[], kind: DropKind): DropKind[] {
  const next = active.includes(kind) ? active.filter(item => item !== kind) : [...active, kind];
  return next.length === 0 ? active : DROP_KINDS.filter(item => next.includes(item));
}

/** Breite einer Ebene in Prozent: oben schmal, nach unten breiter (Pyramide), nie über 100. */
export function layerWidthPercent(layer: number, layers: number): number {
  if (layers <= 0) return 100;
  return Math.min(100, Math.round(34 + (66 * layer) / layers));
}

/** Ebenen, die der Nutzer nach dem Einklappen geöffnet hat, in stabiler Reihenfolge. */
export function toggleExpanded(expanded: number[], layer: number): number[] {
  return (expanded.includes(layer) ? expanded.filter(item => item !== layer) : [...expanded, layer]).sort((a, b) => a - b);
}
