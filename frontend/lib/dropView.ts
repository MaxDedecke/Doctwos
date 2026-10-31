/** Drop-Ansicht (O-387): Typen und reine Hilfen; die Daten liefert `GET /entities/{id}/drop` (wie das MCP-Werkzeug `drop`). */

export type DropKind = 'control' | 'data' | 'includes';
export type DropDirection = 'down' | 'up';
export type DropOrientation = 'vertical' | 'horizontal';

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

type Box = { left: number; right: number; top: number; bottom: number };

/**
 * Kurve zwischen zwei Knoten verschiedener Ebenen, relativ zur Zeichenfläche. Quer zur Ebene: untereinander
 * vom unteren zum oberen Rand, nebeneinander vom rechten zum linken. `reversed`: Das Ziel liegt vor der Quelle;
 * das richtet sich nach der Lage, nicht nach der Kantenrichtung. `null`: beide liegen auf derselben Höhe.
 */
export function connectorPath(from: Box, to: Box, base: { left: number; top: number }, orientation: DropOrientation): { d: string; reversed: boolean } | null {
  const horizontal = orientation === 'horizontal';
  const reversed = horizontal ? from.left > to.left : from.top > to.top;
  const first = reversed ? to : from;
  const second = reversed ? from : to;
  if (horizontal) {
    const y1 = (first.top + first.bottom) / 2 - base.top;
    const y2 = (second.top + second.bottom) / 2 - base.top;
    const x1 = first.right - base.left;
    const x2 = second.left - base.left;
    if (x2 <= x1) return null;
    const bend = (x2 - x1) / 2;
    return { d: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`, reversed };
  }
  const x1 = (first.left + first.right) / 2 - base.left;
  const x2 = (second.left + second.right) / 2 - base.left;
  const y1 = first.bottom - base.top;
  const y2 = second.top - base.top;
  if (y2 <= y1) return null;
  const bend = (y2 - y1) / 2;
  return { d: `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`, reversed };
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
