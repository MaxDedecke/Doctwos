import type { GraphViewport } from './knowledgeGraphRendering';

/**
 * Gruppen klappen beim Hereinzoomen von selbst auf und beim Herauszoomen wieder zu.
 *
 * Aufklappen erst, wenn eine Gruppe einen großen Teil des Bildes füllt und ihre Mitte im Bild
 * liegt, damit Zoomen zum Lesen von Namen nichts verändert. Zuklappen bei einer deutlich kleineren
 * Schwelle (Hysterese), sonst flackert eine Gruppe an der Grenze. Von Hand Aufgeklapptes zählt
 * nicht dazu; von Hand Zugeklapptes öffnet sich erst wieder, nachdem es einmal klein war.
 */
export const AUTO_EXPAND_SHARE = 1 / 3;
export const AUTO_COLLAPSE_SHARE = 1 / 8;
export const AUTO_EXPAND_MAX = 3;
export const AUTO_EXPAND_DELAY_MS = 400;

/** Where an automatically expanded group was, so it can be collapsed by its former size. */
export type GroupFootprint = { x: number; y: number; r: number };
export type AutoGroupState = { auto: Map<string, GroupFootprint>; suppressed: Set<string> };
export type VisibleGroup = GroupFootprint & { key: string };

const screenDiameter = (r: number, view: GraphViewport) => 2 * r * view.k;
const shortSide = (view: GraphViewport) => Math.min(view.width, view.height);
const centreInView = (group: GroupFootprint, view: GraphViewport) =>
  Math.abs(group.x - view.x) <= view.width / (2 * view.k) && Math.abs(group.y - view.y) <= view.height / (2 * view.k);

export function decideAutoGroups(groups: VisibleGroup[], view: GraphViewport, state: AutoGroupState) {
  const collapse = [...state.auto].filter(([, group]) =>
    screenDiameter(group.r, view) < AUTO_COLLAPSE_SHARE * shortSide(view) || !centreInView(group, view)).map(([key]) => key);
  const released = groups.filter(group => state.suppressed.has(group.key)
    && screenDiameter(group.r, view) < AUTO_COLLAPSE_SHARE * shortSide(view)).map(group => group.key);
  const stillOpen = state.auto.size - collapse.length;
  const candidate = stillOpen >= AUTO_EXPAND_MAX ? undefined : groups
    .filter(group => !state.suppressed.has(group.key) && !state.auto.has(group.key) && centreInView(group, view)
      && screenDiameter(group.r, view) >= AUTO_EXPAND_SHARE * shortSide(view))
    .sort((a, b) => b.r - a.r || a.key.localeCompare(b.key))[0];
  return { collapse, released, expand: candidate };
}
