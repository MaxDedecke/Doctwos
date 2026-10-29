import type { GraphViewport } from './knowledgeGraphRendering';

/**
 * Gruppen klappen beim Hereinzoomen von selbst auf. Beim Herauszoomen bleibt alles Geladene
 * stehen: Man zoomt heraus, um den Überblick über das Aufgeklappte zu bekommen. Zurück geht es
 * über „Schritt zurück“ oder den Ausgangszustand.
 *
 * Aufklappen erst, wenn eine Gruppe einen großen Teil des Bildes füllt und ihre Mitte im Bild
 * liegt, damit Zoomen zum Lesen von Namen nichts verändert. Von Hand oder per „Schritt zurück“
 * Zugeklapptes öffnet sich erst wieder, nachdem es einmal klein war.
 */
export const AUTO_EXPAND_SHARE = 1 / 3;
export const AUTO_RELEASE_SHARE = 1 / 8;
export const AUTO_EXPAND_DELAY_MS = 400;

export type VisibleGroup = { key: string; x: number; y: number; r: number };

const screenDiameter = (r: number, view: GraphViewport) => 2 * r * view.k;
const shortSide = (view: GraphViewport) => Math.min(view.width, view.height);
const centreInView = (group: VisibleGroup, view: GraphViewport) =>
  Math.abs(group.x - view.x) <= view.width / (2 * view.k) && Math.abs(group.y - view.y) <= view.height / (2 * view.k);

export function decideAutoGroups(groups: VisibleGroup[], view: GraphViewport, suppressed: Set<string>) {
  const released = groups.filter(group => suppressed.has(group.key)
    && screenDiameter(group.r, view) < AUTO_RELEASE_SHARE * shortSide(view)).map(group => group.key);
  const expand = groups
    .filter(group => !suppressed.has(group.key) && centreInView(group, view)
      && screenDiameter(group.r, view) >= AUTO_EXPAND_SHARE * shortSide(view))
    .sort((a, b) => b.r - a.r || a.key.localeCompare(b.key))[0];
  return { released, expand };
}
