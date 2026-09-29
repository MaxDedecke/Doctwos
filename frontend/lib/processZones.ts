/**
 * Zonen-Layout der Process-View: Knoten gleichen Typs stehen gemeinsam in einem
 * Rechteck ("hier sind alle externen Aufrufe"). Die Zonen folgen in
 * Leserichtung dem Prozessablauf (Einstieg → Schritte → Verzweigungen → Aufrufe
 * → Datenzugriffe → Externes → Ende); innerhalb einer Zone sortiert die
 * Ablaufnummer (`sequence`) der eingehenden Übergänge die Knoten.
 */

export const ZONE_ORDER = [
  'entry', 'step', 'branch', 'jump', 'iteration', 'call', 'data_access', 'external_call', 'exit',
] as const;

export interface ZoneNodeInput {
  id: string;
  type: string;
}
export interface ZoneEdgeInput {
  source: string;
  target: string;
  sequence?: number | null;
}
export interface Zone {
  type: string;
  x: number;
  y: number;
  w: number;
  h: number;
  count: number;
}
export interface ZoneLayout {
  zones: Zone[];
  positions: Map<string, { x: number; y: number }>;
  /** Kleinste Ablaufnummer der eingehenden Übergänge je Knoten. */
  order: Map<string, number>;
}

const NODE_SPACING = 54;
const ZONE_WIDTH_NODES = 4;
const ZONE_PAD = 22;
const ZONE_HEADER = 30;
const ZONE_GAP = 46;

function zoneRank(type: string): number {
  const index = (ZONE_ORDER as readonly string[]).indexOf(type);
  return index === -1 ? ZONE_ORDER.length : index;
}

export function layoutZones(
  nodes: ZoneNodeInput[],
  edges: ZoneEdgeInput[],
  aspect: number,
): ZoneLayout {
  const order = new Map<string, number>();
  for (const edge of edges) {
    if (edge.sequence == null) continue;
    const previous = order.get(edge.target);
    if (previous === undefined || edge.sequence < previous) order.set(edge.target, edge.sequence);
  }

  const byType = new Map<string, ZoneNodeInput[]>();
  nodes.forEach(node => {
    const list = byType.get(node.type) ?? [];
    list.push(node);
    byType.set(node.type, list);
  });
  const types = [...byType.keys()].sort((a, b) => zoneRank(a) - zoneRank(b) || a.localeCompare(b));
  if (types.length === 0) return { zones: [], positions: new Map(), order };

  const zoneW = ZONE_PAD * 2 + ZONE_WIDTH_NODES * NODE_SPACING;
  const sizes = types.map(type => {
    const count = byType.get(type)!.length;
    const rows = Math.ceil(count / ZONE_WIDTH_NODES);
    return { type, count, h: ZONE_HEADER + ZONE_PAD * 2 + rows * NODE_SPACING };
  });

  // Spaltenzahl aus dem Seitenverhältnis der Ansicht: breit → mehr Spalten.
  const cols = Math.max(1, Math.min(types.length, Math.round(Math.sqrt(types.length * Math.max(aspect, 0.3) * 0.75))));
  const rowsOfZones = Math.ceil(types.length / cols);
  const rowHeights = Array.from({ length: rowsOfZones }, (_, row) =>
    Math.max(...sizes.slice(row * cols, row * cols + cols).map(size => size.h)));

  const zones: Zone[] = [];
  const positions = new Map<string, { x: number; y: number }>();
  sizes.forEach((size, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const x = col * (zoneW + ZONE_GAP);
    const y = rowHeights.slice(0, row).reduce((sum, h) => sum + h + ZONE_GAP, 0);
    zones.push({ type: size.type, x, y, w: zoneW, h: rowHeights[row], count: size.count });

    const members = [...byType.get(size.type)!].sort((a, b) =>
      (order.get(a.id) ?? Number.MAX_SAFE_INTEGER) - (order.get(b.id) ?? Number.MAX_SAFE_INTEGER));
    members.forEach((node, i) => {
      positions.set(node.id, {
        x: x + ZONE_PAD + NODE_SPACING / 2 + (i % ZONE_WIDTH_NODES) * NODE_SPACING,
        y: y + ZONE_HEADER + ZONE_PAD + NODE_SPACING / 2 + Math.floor(i / ZONE_WIDTH_NODES) * NODE_SPACING - 8,
      });
    });
  });
  return { zones, positions, order };
}
