import { describe, expect, it } from 'vitest';
import {
  addItem, allSet, emptyCustomSet, hasItem, isEmptySet, itemKey, removeItem, setFacetGroup, setForApi, setsFromServer,
  toggleFacetValue, type FacetGroup, type Pairing,
} from './linkSets';

const codeDocs: Pairing = { key: 'code_docs', a: 'code', b: 'docs', task_type: 'entity_links' };
const cobol: FacetGroup = { key: 'cobol', count: 60, values: [{ value: 'paragraph', count: 50 }, { value: 'section', count: 8 }, { value: 'program', count: 2 }] };

describe('linkSets', () => {
  it('erkennt Objekte an ihren Schlüsselfeldern, nicht an der Anzeige', () => {
    expect(itemKey({ kind: 'entity', id: 4, label: 'A' })).toBe(itemKey({ kind: 'entity', id: 4, label: 'B', group: 'cobol' }));
    expect(itemKey({ kind: 'document', source_id: 1, file_path: 'a.pdf' })).not.toBe(itemKey({ kind: 'document', source_id: 2, file_path: 'a.pdf' }));
    // Eine künftige Objektart ohne bekannte Schlüssel: alle Nicht-Anzeigefelder zählen.
    expect(itemKey({ kind: 'issue', key: 'X-1', label: 'a' })).toBe(itemKey({ kind: 'issue', key: 'X-1', label: 'b' }));
  });

  it('eine eigene Auswahl beginnt leer und wächst über Suche und Filter', () => {
    let set = emptyCustomSet('code');
    expect(isEmptySet(set)).toBe(true);
    expect(isEmptySet(allSet('code'))).toBe(false);
    set = addItem(set, { kind: 'entity', id: 7, label: 'PAYCALC' });
    set = addItem(set, { kind: 'entity', id: 7, label: 'doppelt' });
    expect(set.items).toHaveLength(1);
    expect(hasItem(set, { kind: 'entity', id: 7 })).toBe(true);
    set = removeItem(set, { kind: 'entity', id: 7 });
    expect(isEmptySet(set)).toBe(true);
    set = toggleFacetValue(set, 'entity_type', 'program', true);
    expect(isEmptySet(set)).toBe(false);
    expect(isEmptySet(toggleFacetValue(set, 'entity_type', 'program', false))).toBe(true);
  });

  it('wählt eine ganze Gruppe an oder ab und lässt andere Werte stehen', () => {
    const set = toggleFacetValue(emptyCustomSet('code'), 'entity_type', 'method', true);
    expect(setFacetGroup(set, 'entity_type', cobol, true).facets.entity_type).toEqual(['method', 'paragraph', 'section', 'program']);
    expect(setFacetGroup(setFacetGroup(set, 'entity_type', cobol, true), 'entity_type', cobol, false).facets.entity_type).toEqual(['method']);
  });

  it('schickt der API nur Schlüssel, Bezeichnung und Detail und keine leeren Facetten', () => {
    const set = addItem(toggleFacetValue(emptyCustomSet('code'), 'source', '3', false),
      { kind: 'entity', id: 7, label: 'PAYCALC', detail: 'Programm', group: 'cobol', entity_type: 'program' });
    expect(setForApi(set)).toEqual({ kind: 'code', mode: 'custom', facets: {}, items: [{ kind: 'entity', id: 7, label: 'PAYCALC', detail: 'Programm' }] });
    expect(setForApi({ ...set, mode: 'all' })).toEqual(allSet('code'));
  });

  it('übernimmt die letzte Auswahl nur, wenn sie zur Analyseart passt', () => {
    expect(setsFromServer(codeDocs, null)).toEqual({ pairing: 'code_docs', a: allSet('code'), b: allSet('docs') });
    const restored = setsFromServer(codeDocs, {
      a: { kind: 'code', mode: 'custom', facets: { entity_type: ['section'] }, items: [] },
      b: { kind: 'code', mode: 'custom', facets: {}, items: [] },
    });
    expect(restored.a.facets).toEqual({ entity_type: ['section'] });
    expect(restored.b).toEqual(allSet('docs'));
  });
});
