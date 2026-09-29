/**
 * Kenngrößen für Layout und Kantenrichtung des Wissensgraphen. Die Werte sind hier
 * gebündelt, damit sie testbar sind und an einer Stelle nachgestellt werden können.
 *
 * Frühere Werte (zu dicht, Pfeile kaum erkennbar): Link-Abstand 100–360, Abstoßung
 * 120–1000 (+ bis 500 je Knotengrad), Radialring 130–900, Kollisionsrand 24, Pfeil 4 px.
 */

/**
 * Richtungspfeile. Ihre Länge folgt drei Regeln, damit die Richtung auch weit herausgezoomt
 * lesbar bleibt und der Pfeil im fairen Verhältnis zur Kante steht:
 *  1. Mindestlänge in Graph-Einheiten (ARROW_LENGTH / ARROW_LENGTH_SELECTED) und mindestens
 *     das ARROW_LINE_WIDTH_RATIO-Fache der Linienbreite, dicke (hoch bewertete) Kanten
 *     bekommen also größere Pfeile.
 *  2. Zoomkompensation: Auf dem Bildschirm soll der Pfeil mindestens ARROW_MIN_SCREEN_PX
 *     lang sein, die Länge in Graph-Einheiten wächst daher beim Herauszoomen.
 *  3. Deckel: Ein Pfeil darf höchstens ARROW_MAX_EDGE_FRACTION der sichtbaren Kantenlänge
 *     (zwischen den Knotenrändern) einnehmen, sonst verdeckt er kurze Kanten.
 * Frühere Werte: fest 4 px (6,5 px ausgewählt), ohne Zoomkompensation.
 */
export const ARROW_LENGTH = 12;
export const ARROW_LENGTH_SELECTED = 18;
export const ARROW_LINE_WIDTH_RATIO = 6;
export const ARROW_MIN_SCREEN_PX = 14;
/** Die ausgewählte Kante darf auf dem Bildschirm entsprechend größer sein. */
export const ARROW_MIN_SCREEN_PX_SELECTED_FACTOR = 1.4;
export const ARROW_MAX_EDGE_FRACTION = 0.4;
/** Halbe Breite des zusätzlichen Pfeils am Quellknoten bidirektionaler Kanten relativ zur Pfeillänge. */
export const BIDIRECTIONAL_ARROW_HALF_WIDTH_RATIO = 0.4;

/** Linienbreite einer Kante in Graph-Einheiten (Bewertung 0..1, ausgewählt am breitesten). */
export function edgeLineWidth(selected: boolean, score: number | null | undefined): number {
  return selected ? 4.5 : Math.max(1.2, (score ?? 0.5) * 3);
}

export function arrowLength(options: {
  selected: boolean;
  lineWidth: number;
  /** Aktueller Zoomfaktor des Graphen (1 = unskaliert, kleiner = herausgezoomt). */
  zoom: number;
  /** Sichtbare Kantenlänge zwischen den Knotenrändern; unbekannt = kein Deckel. */
  exposedLength?: number | null;
}): number {
  const { selected, lineWidth, zoom, exposedLength } = options;
  const base = Math.max(selected ? ARROW_LENGTH_SELECTED : ARROW_LENGTH, lineWidth * ARROW_LINE_WIDTH_RATIO);
  const minScreen = ARROW_MIN_SCREEN_PX * (selected ? ARROW_MIN_SCREEN_PX_SELECTED_FACTOR : 1);
  const zoomed = Math.max(base, minScreen / Math.max(zoom, 0.02));
  if (exposedLength != null && exposedLength > 0) {
    return Math.min(zoomed, exposedLength * ARROW_MAX_EDGE_FRACTION);
  }
  return zoomed;
}

/** Abstand der Schichten und Zeilen im festen Nachbarschaftslayout. */
export const NEIGHBORHOOD_LAYER_GAP = 190;
export const NEIGHBORHOOD_ROW_GAP = 100;

/** Simulationsdauer: Das weitere Auseinanderziehen braucht mehr Zeit, bis es zur Ruhe kommt. */
export const GRAPH_COOLDOWN_MS = 6000;
export const GRAPH_ALPHA_DECAY = 0.015;

/** Mindestabstand zweier Knoten (Radius + Rand für die Beschriftung) gegen Überlappung. */
export function collisionRadius(nodeRadius: number, degree: number): number {
  return nodeRadius + 40 + Math.sqrt(degree) * 6;
}

/** Abstoßung (negativ): wächst mit der Knotenzahl und dem Grad, damit große Graphen sich ausbreiten. */
export function chargeStrength(nodeCount: number, degree: number): number {
  return -Math.min(1700, (120 + nodeCount * 1.8) * 1.7) - Math.min(850, degree * 30);
}

/** Reichweite der Abstoßung. */
export const CHARGE_DISTANCE_MAX = 3000;

/** Sollradius im Übersichtsmodus: Knoten mit hohem Grad sitzen weiter außen. */
export function radialRadius(degree: number): number {
  return 220 + Math.min(1300, Math.sqrt(degree) * 125);
}

/** Ruhelänge einer Kante: verbundene Knoten mit vielen Nachbarn bekommen mehr Raum. */
export function linkDistance(sourceDegree: number, targetDegree: number): number {
  const endpointDegrees = Math.sqrt(sourceDegree) + Math.sqrt(targetDegree);
  return 170 + Math.min(440, endpointDegrees * 40);
}
