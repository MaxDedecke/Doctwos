import { describe, expect, it } from 'vitest';
import { buildFlowRows, dataVerb, type FlowNode, type FlowProjection, type FlowTransition } from './processFlow';

const loc = (line: number) => ({ file_path: 'A.CBL', start_line: line, source_id: 1 });
const node = (id: string, label: string, kind = 'step', entity = true): FlowNode =>
  ({ id, kind, label, entity_id: entity ? Number(id.split(':')[1]) : null, locator: loc(1) });
const tr = (id: string, source: string, target: string, kind: string, line: number, types: string[], extra: Partial<FlowTransition> = {}): FlowTransition =>
  ({ id, source, target, kind, certainty: 'certain', code_edge_types: types, locator: loc(line), ...extra });

const MAIN: FlowProjection = {
  nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'INIT'), node('entity:3', 'WRITE'), node('entity:9', 'FIELD-A', 'data_access'), node('entity:8', 'FIELD-B', 'data_access'), node('external:edge:5', 'BANK', 'external_call', false)],
  transitions: [
    tr('e3', 'entity:1', 'entity:3', 'call', 30, ['PERFORM']),
    tr('e1', 'entity:1', 'entity:9', 'data_access', 10, ['USES']),
    tr('e2', 'entity:1', 'entity:8', 'data_access', 11, ['WRITES']),
    tr('e4', 'entity:1', 'entity:2', 'call', 20, ['PERFORM']),
    tr('e5', 'entity:1', 'external:edge:5', 'external_call', 40, ['CALL'], { certainty: 'unresolved' }),
    tr('e6', 'entity:1', 'entity:9', 'data_access', 50, ['READS']),
  ],
};

describe('buildFlowRows', () => {
  it('ordnet nach Aufrufzeile und fasst Datenzugriffe zwischen Schritten zusammen', () => {
    const { rows } = buildFlowRows('entity:1', new Map([['entity:1', MAIN]]), new Set());
    expect(rows.map(r => [r.lane, r.lane === 'data' ? r.line : r.label])).toEqual([
      ['control', 'MAIN'], ['data', 10], ['control', 'INIT'], ['control', 'WRITE'], ['external', 'BANK'], ['data', 50],
    ]);
    const firstData = rows[1];
    expect(firstData.counts).toEqual({ read: 0, write: 1, use: 1 });
    expect(firstData.targets).toEqual(['FIELD-A', 'FIELD-B']);
    expect(firstData.accesses).toHaveLength(2);
  });

  it('klappt Unterschritte nur auf Wunsch auf und meldet fehlende Daten als needsLoad', () => {
    const sub: FlowProjection = { nodes: [node('entity:2', 'INIT'), node('entity:4', 'OPEN')], transitions: [tr('s1', 'entity:2', 'entity:4', 'call', 5, ['PERFORM'])] };
    const key = 'root/e4';
    const closed = buildFlowRows('entity:1', new Map([['entity:1', MAIN]]), new Set());
    expect(closed.rows.find(r => r.label === 'INIT')).toMatchObject({ expandable: true, expanded: false });

    const notLoaded = buildFlowRows('entity:1', new Map([['entity:1', MAIN]]), new Set([key]));
    expect(notLoaded.rows.find(r => r.label === 'INIT')).toMatchObject({ expanded: true, needsLoad: true });

    const open = buildFlowRows('entity:1', new Map([['entity:1', MAIN], ['entity:2', sub]]), new Set([key]));
    const labels = open.rows.map(r => r.label);
    expect(labels.indexOf('OPEN')).toBe(labels.indexOf('INIT') + 1);
    expect(open.rows.find(r => r.label === 'OPEN')!.depth).toBe(2);
  });

  it('markiert Rekursion und Zyklen und klappt sie nicht auf; offene Aufrufe sind nicht aufklappbar', () => {
    const loop: FlowProjection = {
      nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'A')],
      transitions: [
        tr('a', 'entity:1', 'entity:2', 'call', 1, ['PERFORM']),
        tr('b', 'entity:2', 'entity:1', 'call', 2, ['PERFORM']),
        tr('c', 'entity:2', 'entity:2', 'call', 3, ['PERFORM']),
      ],
    };
    const { rows } = buildFlowRows('entity:1', new Map([['entity:1', loop], ['entity:2', loop]]), new Set(['root/a']));
    expect(rows.find(r => r.key === 'root/a/b')).toMatchObject({ cycle: 'cycle', expandable: false });
    expect(rows.find(r => r.key === 'root/a/c')).toMatchObject({ cycle: 'recursion', expandable: false });
    const ext = buildFlowRows('entity:1', new Map([['entity:1', MAIN]]), new Set()).rows.find(r => r.label === 'BANK')!;
    expect(ext).toMatchObject({ lane: 'external', expandable: false, unresolved: true, certainty: 'unresolved' });
  });

  it('leitet das Verb der Datenzugriffe ab und liefert ohne Wurzel nichts', () => {
    expect(dataVerb(['WRITES'])).toBe('write');
    expect(dataVerb(['READS'])).toBe('read');
    expect(dataVerb(['USES'])).toBe('use');
    expect(buildFlowRows('entity:404', new Map(), new Set()).rows).toEqual([]);
  });

  it('setzt Wächterzeilen für Bedingungen und Schleifen und rückt darunterliegende Schritte ein', () => {
    const ifThen = { type: 'IF', branch: 'THEN', condition: "WS-A = 'Y'" };
    const ifElse = { ...ifThen, branch: 'ELSE' };
    const loop = { type: 'LOOP', kind: 'UNTIL', text: 'X > 5' };
    const inline = { type: 'LOOP', kind: 'INLINE', text: '' };
    const flow: FlowProjection = {
      nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'A'), node('entity:3', 'B'), node('entity:4', 'C'), node('entity:5', 'D'), node('entity:6', 'E')],
      transitions: [
        tr('a', 'entity:1', 'entity:2', 'call', 10, ['PERFORM'], { meta: { control_path: [ifThen] } }),
        tr('b', 'entity:1', 'entity:3', 'call', 11, ['PERFORM'], { meta: { control_path: [ifThen] } }),
        tr('c', 'entity:1', 'entity:4', 'call', 12, ['PERFORM'], { meta: { control_path: [ifElse] } }),
        tr('d', 'entity:1', 'entity:5', 'call', 13, ['PERFORM'], { meta: { control_path: [loop, inline] } }),
        tr('e', 'entity:1', 'entity:6', 'iteration', 14, ['PERFORM'], { meta: { loop: { kind: 'TIMES', text: '3' } } }),
      ],
    };
    const { rows } = buildFlowRows('entity:1', new Map([['entity:1', flow]]), new Set());
    expect(rows.map(r => (r.guard ? `guard:${r.guard.branch ?? r.guard.kind}` : r.label))).toEqual([
      'MAIN', 'guard:THEN', 'A', 'B', 'guard:ELSE', 'C', 'guard:UNTIL', 'D', 'E',
    ]);
    const byLabel = (label: string) => rows.find(r => r.label === label)!;
    expect(byLabel('MAIN').indent).toBe(0);
    expect(byLabel('A').indent).toBe(2);
    expect(rows[1].indent).toBe(1);
    expect(byLabel('D').indent).toBe(2);
    expect(byLabel('E')).toMatchObject({ indent: 1, loop: { kind: 'TIMES', text: '3' } });
  });
});
