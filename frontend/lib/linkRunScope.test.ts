import { describe, expect, it } from 'vitest';
import {
  EMPTY_LINK_RUN_SCOPE, isTargetedScope, linkRunScopeQuery, scopeFromFilter, selectedChunkCount, selectedEntityCount,
  setLanguageTypes, toggleValue, type LinkScopeOptions,
} from './linkRunScope';

const options: LinkScopeOptions = {
  languages: [
    { language: 'cobol', count: 150, types: [{ type: 'paragraph', count: 100 }, { type: 'section', count: 40 }, { type: 'program', count: 10 }] },
    { language: 'java', count: 30, types: [{ type: 'method', count: 25 }, { type: 'class', count: 5 }] },
  ],
  doc_sources: [
    { id: 7, name: 'Handbuch.pdf', type: 'Local', chunk_count: 12 },
    { id: 9, name: 'Jira', type: 'Jira', chunk_count: 30 },
  ],
  last_filter: null,
};

describe('linkRunScope', () => {
  it('sendet ohne Auswahl keine Einschränkung', () => {
    expect(linkRunScopeQuery(EMPTY_LINK_RUN_SCOPE)).toBe('');
    expect(isTargetedScope(EMPTY_LINK_RUN_SCOPE)).toBe(false);
  });

  it('sendet Typen und Quellen unter den Parameternamen der API', () => {
    const query = new URLSearchParams(linkRunScopeQuery({ entityTypes: ['section', 'program'], docSourceIds: [9, 7] }));
    expect(query.getAll('entity_types')).toEqual(['program', 'section']);
    expect(query.getAll('doc_source_ids')).toEqual(['7', '9']);
  });

  it('übernimmt aus dem letzten Lauf nur, was es im Projekt noch gibt', () => {
    const scope = scopeFromFilter({ entity_types: ['program', 'gone'], doc_source_ids: [7, 99] }, options);
    expect(scope).toEqual({ entityTypes: ['program'], docSourceIds: [7] });
    expect(scopeFromFilter(null, options)).toEqual(EMPTY_LINK_RUN_SCOPE);
  });

  it('wählt alle Typen einer Sprache an oder ab und lässt die anderen Sprachen stehen', () => {
    const cobol = options.languages[0];
    expect(setLanguageTypes(['method', 'section'], cobol, true)).toEqual(['method', 'paragraph', 'section', 'program']);
    expect(setLanguageTypes(['method', 'section'], cobol, false)).toEqual(['method']);
    expect(toggleValue(['a'], 'a', true)).toEqual(['a']);
    expect(toggleValue(['a', 'b'], 'a', false)).toEqual(['b']);
  });

  it('zählt beide Mengen; ohne Auswahl die ganze Seite', () => {
    const scope = { entityTypes: ['program', 'section'], docSourceIds: [7] };
    expect(selectedEntityCount(options, scope)).toBe(50);
    expect(selectedChunkCount(options, scope)).toBe(12);
    expect(selectedEntityCount(options, EMPTY_LINK_RUN_SCOPE)).toBe(180);
    expect(selectedChunkCount(options, EMPTY_LINK_RUN_SCOPE)).toBe(42);
  });
});
