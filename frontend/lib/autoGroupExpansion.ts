import type { GraphViewport } from './knowledgeGraphRendering';

/**
 * Gruppen klappen beim Hereinzoomen von selbst auf. Beim Herauszoomen bleibt alles Geladene
 * stehen: Man zoomt heraus, um den Überblick über das Aufgeklappte zu bekommen. Zurück geht es
 * über „Schritt zurück“ oder den Ausgangszustand.
 *
 * Aufgeklappt wird nur die Gruppe, auf die man zuzoomt (unter dem Zeiger, sonst in der Bildmitte),
 * sobald sie ein Achtel des Bildes füllt: früh genug, dass ihr Inhalt im Bild Platz findet
 * (Syncope: 40 % statt 12 % bei einem Drittel), ohne dass Nachbargruppen mit aufgehen. Von Hand oder
 * per „Schritt zurück“ Zugeklapptes öffnet sich erst wieder, nachdem es einmal klein war.
 */
export const AUTO_EXPAND_SHARE = 1 / 8;
export const AUTO_RELEASE_SHARE = 1 / 20;
export const AUTO_EXPAND_DELAY_MS = 400;

export type VisibleGroup = { key: string; x: number; y: number; r: number };

const screenDiameter = (r: number, view: GraphViewport) => 2 * r * view.k;
const shortSide = (view: GraphViewport) => Math.min(view.width, view.height);
/** `focus`: graph point zoomed towards (pointer); without it the centre of the view. */
export function decideAutoGroups(groups: VisibleGroup[], view: GraphViewport, suppressed: Set<string>,
  focus?: { x: number; y: number } | null) {
  const released = groups.filter(group => suppressed.has(group.key)
    && screenDiameter(group.r, view) < AUTO_RELEASE_SHARE * shortSide(view)).map(group => group.key);
  const point = focus ?? { x: view.x, y: view.y };
  const expand = groups
    .filter(group => !suppressed.has(group.key) && Math.hypot(group.x - point.x, group.y - point.y) <= group.r
      && screenDiameter(group.r, view) >= AUTO_EXPAND_SHARE * shortSide(view))
    .sort((a, b) => Math.hypot(a.x - point.x, a.y - point.y) - Math.hypot(b.x - point.x, b.y - point.y))[0];
  return { released, expand };
}
