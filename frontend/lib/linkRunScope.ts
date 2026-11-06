// Einschränkung eines Entity-Link-Laufs auf zwei Mengen: Code-Entitäten gewählter Typen (je Sprache gruppiert)
// gegen Dokumentation gewählter Wissensquellen. Spiegelt `GET /projects/{id}/link-recommendations/scope-options`
// und die Query-Parameter `entity_types`/`doc_source_ids` von Schätzung und Start.

export interface LinkScopeType { type: string; count: number }
export interface LinkScopeLanguage { language: string; count: number; types: LinkScopeType[] }
export interface LinkScopeSource { id: number; name: string; type: string; chunk_count: number }
export interface LinkScopeFilter { entity_types: string[]; doc_source_ids: number[] }
export interface LinkScopeOptions {
  languages: LinkScopeLanguage[];
  doc_sources: LinkScopeSource[];
  last_filter: LinkScopeFilter | null;
}

/** Leere Listen heißen: keine Einschränkung auf dieser Seite. */
export interface LinkRunScope { entityTypes: string[]; docSourceIds: number[] }

export const EMPTY_LINK_RUN_SCOPE: LinkRunScope = { entityTypes: [], docSourceIds: [] };

export function isTargetedScope(scope: LinkRunScope): boolean {
  return scope.entityTypes.length > 0 || scope.docSourceIds.length > 0;
}

/** Auswahl aus dem letzten Lauf übernehmen, aber nur, was es im Projekt noch gibt. */
export function scopeFromFilter(filter: LinkScopeFilter | null | undefined, options: LinkScopeOptions): LinkRunScope {
  if (!filter) return EMPTY_LINK_RUN_SCOPE;
  const types = new Set(options.languages.flatMap(language => language.types.map(item => item.type)));
  const sources = new Set(options.doc_sources.map(source => source.id));
  return {
    entityTypes: (filter.entity_types ?? []).filter(type => types.has(type)),
    docSourceIds: (filter.doc_source_ids ?? []).filter(id => sources.has(id)),
  };
}

export function linkRunScopeQuery(scope: LinkRunScope): string {
  const params = new URLSearchParams();
  [...scope.entityTypes].sort().forEach(type => params.append('entity_types', type));
  [...scope.docSourceIds].sort((a, b) => a - b).forEach(id => params.append('doc_source_ids', String(id)));
  return params.toString();
}

export function toggleValue<T>(values: T[], value: T, checked: boolean): T[] {
  if (checked) return values.includes(value) ? values : [...values, value];
  return values.filter(item => item !== value);
}

/** Alle Typen einer Sprache an- oder abwählen; die Auswahl anderer Sprachen bleibt. */
export function setLanguageTypes(selected: string[], language: LinkScopeLanguage, checked: boolean): string[] {
  const own = new Set(language.types.map(item => item.type));
  const rest = selected.filter(type => !own.has(type));
  return checked ? [...rest, ...language.types.map(item => item.type)] : rest;
}

/** Entitäten, die der Lauf auf der Code-Seite prüft (ohne Auswahl: alle). */
export function selectedEntityCount(options: LinkScopeOptions, scope: LinkRunScope): number {
  const all = options.languages.flatMap(language => language.types);
  const chosen = scope.entityTypes.length ? all.filter(item => scope.entityTypes.includes(item.type)) : all;
  return chosen.reduce((sum, item) => sum + item.count, 0);
}

/** Dokument-Abschnitte, gegen die der Lauf prüft (ohne Auswahl: alle). */
export function selectedChunkCount(options: LinkScopeOptions, scope: LinkRunScope): number {
  const chosen = scope.docSourceIds.length
    ? options.doc_sources.filter(source => scope.docSourceIds.includes(source.id))
    : options.doc_sources;
  return chosen.reduce((sum, source) => sum + source.chunk_count, 0);
}
