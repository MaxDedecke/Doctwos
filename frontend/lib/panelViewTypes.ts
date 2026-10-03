/**
 * Einzige Quelle für die wählbaren Ansichtsarten (Panel-Typen). Sowohl das
 * Menü "Ansicht hinzufügen" (GlobalSearch) als auch der Typ-Umschalter innerhalb
 * einer Ansicht (PanelRenderer) lesen diese Liste, damit beide immer dieselben
 * Ansichten anbieten. Reihenfolge = Reihenfolge in beiden Menüs.
 */
export const PANEL_VIEW_TYPES = [
  'chat',
  'code',
  'doc',
  'graph',
  'callgraph',
  'webview',
  'linkmanager',
  'insights',
] as const;

export type PanelViewType = (typeof PANEL_VIEW_TYPES)[number];

/** Der Link-Manager steht nur bereit, wenn das Feature aktiv und der Nutzer Admin ist. */
export function getAvailablePanelViewTypes(options: { linkManagerEnabled: boolean }): PanelViewType[] {
  return PANEL_VIEW_TYPES.filter((type) => type !== 'linkmanager' || options.linkManagerEnabled);
}
