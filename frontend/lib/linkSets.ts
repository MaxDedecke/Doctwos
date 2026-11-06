// Mengen eines Link-Laufs (Menge A gegen Menge B). Spiegelt `doctus_models/link_sets.py` und die Antworten von
// `/projects/{id}/link-runs/*`. Mengenarten, Facetten, Objektarten und Analysearten kommen vom Server; hier steht
// nichts Sprach- oder Quellenspezifisches, damit neue Sprachen und Quelltypen ohne Frontend-Änderung erscheinen.

export type SetMode = 'all' | 'custom';

/** Ein explizit gewähltes Objekt. Schlüsselfelder je Art (z. B. `id` oder `source_id` + `file_path`) plus Anzeige. */
export interface LinkSetItem {
  kind: string;
  label?: string;
  detail?: string;
  /** Nur Anzeige: Gruppe (Sprache, Quelltyp), Entitätstyp, Zahl der Abschnitte. */
  group?: string;
  entity_type?: string;
  chunk_count?: number;
  [key: string]: unknown;
}

export interface LinkSetDef {
  kind: string;
  mode: SetMode;
  facets: Record<string, string[]>;
  items: LinkSetItem[];
}

export interface FacetValue { value: string; count: number; label?: string }
export interface FacetGroup { key: string; count: number; values: FacetValue[] }
export interface Facet { name: string; groups: FacetGroup[] }
export interface KindOptions { total: number; facets: Facet[] }
export interface Pairing { key: string; a: string; b: string; task_type: string }
export interface RunSetsDef { pairing: string; a: LinkSetDef; b: LinkSetDef }

export interface WorkspaceOptions {
  project_id: number;
  pairings: Pairing[];
  kinds: Record<string, KindOptions>;
  last: Record<string, Partial<RunSetsDef> | null>;
}

export interface SetPreview { count: number; documents?: number; sample: LinkSetItem[] }

export interface RunEstimate {
  pairing: string;
  task_type: string;
  targeted: boolean;
  is_bootstrap: boolean;
  a_count: number;
  b_count: number;
  reviews_max: number;
  embedding_calls_max: number;
  has_active_run: boolean;
}

/** Felder, die ein Objekt identifizieren; alle übrigen sind Anzeige. Unbekannte Arten: alle Nicht-Anzeigefelder. */
const ITEM_KEY_FIELDS: Record<string, string[]> = { entity: ['id'], document: ['source_id', 'file_path'] };
const DISPLAY_FIELDS = new Set(['label', 'detail', 'group', 'entity_type', 'chunk_count']);

export function itemKey(item: LinkSetItem): string {
  const fields = ITEM_KEY_FIELDS[item.kind] ?? Object.keys(item).filter(name => name !== 'kind' && !DISPLAY_FIELDS.has(name)).sort();
  return JSON.stringify([item.kind, ...fields.map(name => item[name] ?? null)]);
}

export function allSet(kind: string): LinkSetDef {
  return { kind, mode: 'all', facets: {}, items: [] };
}

export function emptyCustomSet(kind: string): LinkSetDef {
  return { kind, mode: 'custom', facets: {}, items: [] };
}

export function defaultSets(pairing: Pairing): RunSetsDef {
  return { pairing: pairing.key, a: allSet(pairing.a), b: allSet(pairing.b) };
}

function normalizeSet(raw: Partial<LinkSetDef> | undefined, kind: string): LinkSetDef {
  if (!raw || raw.kind !== kind || raw.mode !== 'custom') return allSet(kind);
  return {
    kind,
    mode: 'custom',
    facets: Object.fromEntries(Object.entries(raw.facets ?? {}).map(([name, values]) => [name, (values ?? []).map(String)])),
    items: Array.isArray(raw.items) ? raw.items.filter(item => item && typeof item.kind === 'string') : [],
  };
}

/** Auswahl des letzten Laufs dieser Analyseart übernehmen; Unpassendes wird zu „Alle“. */
export function setsFromServer(pairing: Pairing, raw: Partial<RunSetsDef> | null | undefined): RunSetsDef {
  if (!raw) return defaultSets(pairing);
  return { pairing: pairing.key, a: normalizeSet(raw.a, pairing.a), b: normalizeSet(raw.b, pairing.b) };
}

export function isEmptySet(set: LinkSetDef): boolean {
  return set.mode === 'custom' && set.items.length === 0 && Object.values(set.facets).every(values => values.length === 0);
}

export function selectionCount(set: LinkSetDef): number {
  return set.items.length + Object.values(set.facets).reduce((sum, values) => sum + values.length, 0);
}

export function withMode(set: LinkSetDef, mode: SetMode): LinkSetDef {
  return { ...set, mode };
}

export function toggleFacetValue(set: LinkSetDef, facet: string, value: string, checked: boolean): LinkSetDef {
  const current = set.facets[facet] ?? [];
  const next = checked ? (current.includes(value) ? current : [...current, value]) : current.filter(item => item !== value);
  return { ...set, mode: 'custom', facets: { ...set.facets, [facet]: next } };
}

/** Alle Werte einer Gruppe (z. B. alle COBOL-Typen, alle Jira-Quellen) an- oder abwählen. */
export function setFacetGroup(set: LinkSetDef, facet: string, group: FacetGroup, checked: boolean): LinkSetDef {
  const own = new Set(group.values.map(value => value.value));
  const rest = (set.facets[facet] ?? []).filter(value => !own.has(value));
  return { ...set, mode: 'custom', facets: { ...set.facets, [facet]: checked ? [...rest, ...own] : rest } };
}

export function hasItem(set: LinkSetDef, item: LinkSetItem): boolean {
  const key = itemKey(item);
  return set.items.some(existing => itemKey(existing) === key);
}

export function addItem(set: LinkSetDef, item: LinkSetItem): LinkSetDef {
  return hasItem(set, item) ? set : { ...set, mode: 'custom', items: [...set.items, item] };
}

export function removeItem(set: LinkSetDef, item: LinkSetItem): LinkSetDef {
  const key = itemKey(item);
  return { ...set, items: set.items.filter(existing => itemKey(existing) !== key) };
}

export function clearSelection(set: LinkSetDef): LinkSetDef {
  return { ...set, facets: {}, items: [] };
}

/** Form für die API: Anzeige-Felder außer Bezeichnung und Detail weglassen, leere Facetten entfernen. */
export function setForApi(set: LinkSetDef): LinkSetDef {
  if (set.mode === 'all') return allSet(set.kind);
  return {
    kind: set.kind,
    mode: 'custom',
    facets: Object.fromEntries(Object.entries(set.facets).filter(([, values]) => values.length > 0)),
    items: set.items.map(item => Object.fromEntries(Object.entries(item).filter(([name]) => !DISPLAY_FIELDS.has(name) || name === 'label' || name === 'detail')) as LinkSetItem),
  };
}

export function setsForApi(sets: RunSetsDef): RunSetsDef {
  return { pairing: sets.pairing, a: setForApi(sets.a), b: setForApi(sets.b) };
}
