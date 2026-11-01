/** Ansicht „Abhängigkeiten“ (O-387): Typen und reine Hilfen; die Daten liefert `GET /entities/{id}/drop` (wie das MCP-Werkzeug `drop`) oder ein Ablauf aus dem Chat (`flowToDrop`). */

import type { AnalysisStatus } from '@/lib/analysisStatus';
import type { CallFlowData, CallFlowNode } from '@/lib/callFlow';

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
  source_id?: number | string | null;
  file_path: string;
  start_line?: number | null;
  cite: string;
  layer: number;
  /** Ziel ohne Fundstelle im Index; nur Abläufe aus dem Chat zeigen es als Knoten. */
  unresolved?: boolean;
  analysis_status?: AnalysisStatus;
  analysis_reasons?: string[];
}

export interface DropEdge {
  from: number;
  to: number;
  type: string;
  resolution: string;
  cite: string;
  id?: number;
  reason?: string;
  condition?: string;
  provenance?: Record<string, unknown>;
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
  /** Kanten zurück zu einem bereits gezeigten Knoten: innerhalb einer Ebene, nach oben, Zyklen. */
  back_edges?: DropEdge[];
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

/**
 * Bogen zwischen zwei Knoten derselben Ebene, wo `connectorPath` keinen Platz findet: untereinander über die
 * Knoten hinweg, nebeneinander rechts an ihnen vorbei. Zeigt ein Knoten auf sich selbst, wird daraus eine Schleife.
 */
export function sameLayerPath(from: Box, to: Box, base: { left: number; top: number }, orientation: DropOrientation): string {
  const loop = (a: number, b: number) => (a === b ? [a - 8, b + 8] : [a, b]);
  if (orientation === 'horizontal') {
    const x = Math.max(from.right, to.right) - base.left;
    const [y1, y2] = loop((from.top + from.bottom) / 2 - base.top, (to.top + to.bottom) / 2 - base.top);
    const bulge = Math.min(40, Math.max(14, Math.abs(y2 - y1) / 3));
    return `M ${x} ${y1} C ${x + bulge} ${y1}, ${x + bulge} ${y2}, ${x} ${y2}`;
  }
  const y = Math.min(from.top, to.top) - base.top;
  const [x1, x2] = loop((from.left + from.right) / 2 - base.left, (to.left + to.right) / 2 - base.left);
  const bulge = Math.min(40, Math.max(14, Math.abs(x2 - x1) / 4));
  return `M ${x1} ${y} C ${x1} ${y - bulge}, ${x2} ${y - bulge}, ${x2} ${y}`;
}

/** Datei und Zeile aus `pfad/datei.ext:zeile`; Zeile 0 heißt: unbekannt. */
export function citeLocation(cite: string): { path: string; line: number | null } | null {
  const match = /^(.+):(\d+)$/.exec(cite);
  if (!match || match[1] === 'None' || match[1] === 'null') return null;
  return { path: match[1], line: Number(match[2]) || null };
}

/**
 * Ein Ablauf oder Betroffenengraph aus dem Chat als Ebenen um seine Wurzel: Ebene ist der kürzeste Weg in
 * Richtung des Ablaufs. Was so nicht erreichbar ist, folgt über die Gegenrichtung, Unverbundenes zuletzt,
 * damit kein Knoten verloren geht. Nicht aufgelöste Ziele werden Knoten mit negativer Kennung.
 */
export function flowToDrop(flow: CallFlowData): DropResult {
  const known = new Map<number, CallFlowNode>(flow.nodes.map(node => [node.id, node]));
  if (!known.has(flow.root.id)) known.set(flow.root.id, flow.root);
  const links = flow.edges.map(edge => ({ edge, from: edge.source, to: edge.target ?? -edge.id }));
  const names = new Map(flow.edges.filter(edge => edge.target == null).map(edge => [-edge.id, edge.target_name]));

  const layerOf = new Map<number, number>([[flow.root.id, 0]]);
  const walk = (followed: (from: number, to: number) => [number, number][]) => {
    const next = new Map<number, number[]>();
    for (const { from, to } of links) {
      for (const [a, b] of followed(from, to)) next.set(a, [...(next.get(a) ?? []), b]);
    }
    const queue = [...layerOf.keys()];
    for (let index = 0; index < queue.length; index += 1) {
      for (const neighbour of next.get(queue[index]) ?? []) {
        if (!layerOf.has(neighbour)) {
          layerOf.set(neighbour, (layerOf.get(queue[index]) ?? 0) + 1);
          queue.push(neighbour);
        }
      }
    }
  };
  const both = (from: number, to: number): [number, number][] => [[from, to], [to, from]];
  walk(flow.direction === 'outgoing' ? (from, to) => [[from, to]] : flow.direction === 'incoming' ? (from, to) => [[to, from]] : both);
  walk(both);
  const placed = Math.max(...layerOf.values());
  for (const id of [...known.keys(), ...names.keys()]) if (!layerOf.has(id)) layerOf.set(id, placed + 1);

  const toNode = (id: number): DropNode => {
    const node = known.get(id);
    const layer = layerOf.get(id) ?? 0;
    if (!node) return { id, name: names.get(id) ?? String(id), type: 'unresolved', role: null, file_path: '', cite: '', layer, unresolved: true };
    return {
      id, name: node.name, qualified_name: node.qualified_name, type: node.type ?? 'entity', role: null, source_id: node.source_id,
      file_path: node.file_path ?? '', start_line: node.start_line, cite: node.file_path ? `${node.file_path}:${node.start_line ?? 0}` : '', layer,
      analysis_status: node.analysis_status, analysis_reasons: node.analysis_reasons,
    };
  };

  const depth = Math.max(...layerOf.values());
  const layers: DropLayer[] = Array.from({ length: depth + 1 }, (_, layer) => ({ layer, count: 0, unresolved: 0, nodes: [], edges: [] }));
  for (const [id, layer] of layerOf) {
    if (known.has(id) || names.has(id)) { layers[layer].nodes.push(toNode(id)); layers[layer].count += 1; }
  }
  const backEdges: DropEdge[] = [];
  for (const { edge, from, to } of links) {
    const step = (layerOf.get(to) ?? 0) - (layerOf.get(from) ?? 0);
    const source = known.get(from);
    const path = edge.meta?.source_file_path ?? source?.file_path;
    const line = edge.start_line ?? source?.start_line ?? 0;
    const shown: DropEdge = {
      id: edge.id, from, to, type: edge.type, resolution: edge.resolution, cite: path ? `${path}:${line}` : '',
      ...(edge.meta?.resolution_reason ? { reason: edge.meta.resolution_reason } : {}),
    };
    const forward = flow.direction === 'outgoing' ? step === 1 : flow.direction === 'incoming' ? step === -1 : Math.abs(step) === 1;
    if (forward) layers[Math.max(layerOf.get(to) ?? 0, layerOf.get(from) ?? 0)].edges.push(shown);
    else backEdges.push(shown);
  }
  return { root: toNode(flow.root.id), direction: flow.direction === 'incoming' ? 'up' : 'down', kinds: [], layers, back_edges: backEdges, stopped: null, collapse_above: 0 };
}

const ZOOM_LEVELS = [0.25, 0.33, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2];
export const ZOOM_MIN = ZOOM_LEVELS[0];
export const ZOOM_MAX = ZOOM_LEVELS[ZOOM_LEVELS.length - 1];

/** Nächste Zoomstufe; ein eingepasster Wert zwischen zwei Stufen springt auf die nächste in dieser Richtung. */
export function nextZoom(zoom: number, direction: 1 | -1): number {
  const candidates = direction > 0 ? ZOOM_LEVELS.filter(level => level > zoom) : ZOOM_LEVELS.filter(level => level < zoom).reverse();
  return candidates[0] ?? zoom;
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
