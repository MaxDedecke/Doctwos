/**
 * Kenngrößen für Layout und Kantenrichtung des Wissensgraphen. Die Werte sind hier
 * gebündelt, damit sie testbar sind und an einer Stelle nachgestellt werden können.
 *
 * Frühere Werte (zu dicht, Pfeile kaum erkennbar): Link-Abstand 100–360, Abstoßung
 * 120–1000 (+ bis 500 je Knotengrad), Radialring 130–900, Kollisionsrand 24, Pfeil 4 px.
 */

/** Pfeilspitze einer gerichteten Kante in Graph-Einheiten (skaliert mit dem Zoom). */
export const ARROW_LENGTH = 10;
/** Pfeilspitze der ausgewählten Kante. */
export const ARROW_LENGTH_SELECTED = 14;
/** Halbe Breite des zusätzlichen Pfeils am Quellknoten bidirektionaler Kanten relativ zur Pfeillänge. */
export const BIDIRECTIONAL_ARROW_HALF_WIDTH_RATIO = 0.4;

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
