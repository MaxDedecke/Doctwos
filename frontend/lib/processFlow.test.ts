import { describe, expect, it } from 'vitest';
import { buildFlowRows, dataVerb, nextExpansion, type FlowNode, type FlowProjection, type FlowTransition } from './processFlow';

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

  it('startet beim Einstiegsparagraphen, wenn die Antwort für ein Programm ihn als Wurzel nennt', () => {
    const entry: FlowProjection = {
      rootNodeId: 'entity:1',
      nodes: [node('entity:1', '0000-MAIN', 'entry'), node('entity:2', 'INIT')],
      transitions: [tr('a', 'entity:1', 'entity:2', 'call', 10, ['PERFORM'])],
    };
    const job: FlowProjection = {
      nodes: [node('entity:7', 'JOB', 'entry'), node('entity:5', 'PROGRAMM')],
      transitions: [tr('p', 'entity:7', 'entity:5', 'call', 3, ['EXECUTES'])],
    };

    const direct = buildFlowRows('entity:5', new Map([['entity:5', entry]]), new Set());
    expect(direct.rows.map(row => row.label)).toEqual(['0000-MAIN', 'INIT']);

    const nested = buildFlowRows('entity:7', new Map([['entity:7', job], ['entity:5', entry]]), new Set(['root/p']));
    expect(nested.rows.map(row => row.label)).toEqual(['JOB', 'PROGRAMM', 'INIT']);
  });

  it('zeigt Bedingungen auch ohne Aufruf und setzt sie nach Datenzeilen nicht erneut', () => {
    const then = { type: 'IF', branch: 'THEN', condition: 'WS-A' };
    const flow: FlowProjection = {
      nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'A'), node('entity:9', 'FELD')],
      transitions: [
        tr('d1', 'entity:1', 'entity:9', 'data_access', 10, ['READS']),
        tr('d2', 'entity:1', 'entity:9', 'data_access', 11, ['WRITES'], { meta: { control_path: [then] } }),
        tr('d3', 'entity:1', 'entity:9', 'data_access', 12, ['WRITES'], { meta: { control_path: [then] } }),
        tr('a', 'entity:1', 'entity:2', 'call', 13, ['PERFORM'], { meta: { control_path: [then] } }),
      ],
    };
    const { rows } = buildFlowRows('entity:1', new Map([['entity:1', flow]]), new Set());
    expect(rows.map(row => (row.guard ? 'wenn' : row.lane === 'data' ? `daten:${row.accesses!.length}` : row.label))).toEqual([
      'MAIN', 'daten:1', 'wenn', 'daten:2', 'A',
    ]);
    const data = rows.filter(row => row.lane === 'data');
    expect(data[1].indent).toBe(data[0].indent + 1);
  });

  it('macht das Ende eines Laufs nicht aufklappbar und reicht Art und Kandidaten des Aufrufs weiter', () => {
    const flow: FlowProjection = {
      nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'CICS RETURN', 'step'), node('external:edge:5', 'CDEMO-TO-PROGRAM', 'external_call', false)],
      transitions: [
        tr('r', 'entity:1', 'entity:2', 'exit', 20, ['CONTAINS']),
        tr('x', 'entity:1', 'external:edge:5', 'external_call', 10, ['CALL'], {
          certainty: 'possible', meta: { invocation_kind: 'cics_xctl', candidate_targets: ['COMEN01C'] },
        }),
      ],
    };
    const { rows } = buildFlowRows('entity:1', new Map([['entity:1', flow]]), new Set());
    expect(rows[1].invocationKind).toBe('cics_xctl');
    expect(rows[1].candidateTargets).toEqual(['COMEN01C']);
    expect(rows[2].expandable).toBe(false);
  });

  it('blendet Hilfsaufrufe auf Wunsch aus, nennt ihre Zahl und trennt damit keine Datenläufe', () => {
    const flow: FlowProjection = {
      nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'getName'), node('entity:3', 'save'), node('entity:9', 'FELD')],
      transitions: [
        tr('d1', 'entity:1', 'entity:9', 'data_access', 10, ['READS']),
        tr('g', 'entity:1', 'entity:2', 'call', 11, ['CALLS'], { meta: { helper: 'accessor' } }),
        tr('d2', 'entity:1', 'entity:9', 'data_access', 12, ['READS']),
        tr('s', 'entity:1', 'entity:3', 'call', 13, ['CALLS']),
      ],
    };
    const projections = new Map([['entity:1', flow]]);

    const hidden = buildFlowRows('entity:1', projections, new Set(), { hideHelpers: true });
    expect(hidden.hiddenHelpers).toBe(1);
    expect(hidden.rows.map(row => (row.lane === 'data' ? `daten:${row.accesses!.length}` : row.label))).toEqual(['MAIN', 'daten:2', 'save']);

    const shown = buildFlowRows('entity:1', projections, new Set());
    expect(shown.hiddenHelpers).toBe(0);
    expect(shown.rows.map(row => row.label)).toContain('getName');
  });

  it('klappt einen Unterablauf nur beim ersten Vorkommen auf und markiert die übrigen', () => {
    const flow: FlowProjection = {
      nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'SEND'), node('entity:3', 'CICS READ')],
      transitions: [
        tr('a', 'entity:1', 'entity:2', 'call', 10, ['PERFORM']),
        tr('b', 'entity:1', 'entity:2', 'call', 20, ['PERFORM']),
        tr('c', 'entity:1', 'entity:3', 'step', 30, ['CONTAINS']),
      ],
    };
    const projections = new Map([['entity:1', flow], ['entity:2', { nodes: [node('entity:2', 'SEND')], transitions: [] }]]);

    const first = buildFlowRows('entity:1', projections, new Set()).rows;
    expect(nextExpansion(first).map(row => row.key)).toEqual(['root/a']);

    const opened = buildFlowRows('entity:1', projections, new Set(['root/a'])).rows;
    expect(nextExpansion(opened)).toEqual([]);
    expect(opened.find(row => row.key === 'root/b')!.openElsewhere).toBe(true);
    expect(opened.find(row => row.key === 'root/a')!.openElsewhere).toBeUndefined();
  });

  describe('Weiterlaufen in den nächsten Paragraphen', () => {
    const onward = (id: number, next: number): FlowProjection => ({
      nodes: [node(`entity:${id}`, `P${id}`), node(`entity:${next}`, `P${next}`)],
      transitions: [tr(`f${id}`, `entity:${id}`, `entity:${next}`, 'step', next * 10, [], { meta: { fall_through: true } })],
    });
    const labels = (rows: { label: string }[]) => rows.map(row => row.label);

    it('zeigt es am Programmanfang und bleibt dabei auf derselben Ebene', () => {
      const entry = { ...onward(1, 2), rootNodeId: 'entity:1' };
      const projections = new Map([['entity:9', entry], ['entity:2', onward(2, 3)]]);
      const { rows } = buildFlowRows('entity:9', projections, new Set(['root/f1']));
      expect(labels(rows)).toEqual(['P1', 'P2', 'P3']);
      expect(rows[1].fallThrough).toBe(true);
      expect(rows[2].indent).toBe(rows[1].indent);
    });

    it('zeigt es nicht nach einem PERFORM, denn von dort kehrt der Lauf zurück', () => {
      const main: FlowProjection = {
        nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'P2')],
        transitions: [tr('p', 'entity:1', 'entity:2', 'call', 5, ['PERFORM'])],
      };
      const { rows } = buildFlowRows('entity:1', new Map([['entity:1', main], ['entity:2', onward(2, 3)]]), new Set(['root/p']));
      expect(labels(rows)).toEqual(['MAIN', 'P2']);
    });

    it('zeigt es nach GO TO und bei PERFORM THRU bis zum genannten Endpunkt', () => {
      const via = (kind: string, meta = {}): FlowProjection => ({
        nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'P2')],
        transitions: [tr('p', 'entity:1', 'entity:2', kind, 5, ['PERFORM'], { meta })],
      });
      const chain: [string, FlowProjection][] = [['entity:2', onward(2, 3)], ['entity:3', onward(3, 4)]];
      const open = new Set(['root/p', 'root/p/f2']);

      const jump = buildFlowRows('entity:1', new Map([['entity:1', via('jump')], ...chain]), open).rows;
      expect(labels(jump)).toEqual(['MAIN', 'P2', 'P3', 'P4']);

      const thru = buildFlowRows('entity:1', new Map([['entity:1', via('call', { thru: 'p3' })], ...chain]), open).rows;
      expect(labels(thru)).toEqual(['MAIN', 'P2', 'P3']);
      expect(thru[1].thru).toBe('p3');
    });
  });

  it('zählt ausgeblendete Datenzugriffe am Zweig und zeigt ihn trotzdem', () => {
    const then = { type: 'IF', branch: 'THEN', condition: 'WS-A' };
    const flow: FlowProjection = {
      nodes: [node('entity:1', 'MAIN', 'entry'), node('entity:2', 'A'), node('entity:9', 'FELD')],
      transitions: [
        tr('d1', 'entity:1', 'entity:9', 'data_access', 10, ['READS']),
        tr('d2', 'entity:1', 'entity:9', 'data_access', 11, ['WRITES'], { meta: { control_path: [then] } }),
        tr('d3', 'entity:1', 'entity:9', 'data_access', 12, ['WRITES'], { meta: { control_path: [then] } }),
        tr('a', 'entity:1', 'entity:2', 'call', 20, ['PERFORM']),
      ],
    };
    const { rows, hiddenData } = buildFlowRows('entity:1', new Map([['entity:1', flow]]), new Set(), { hideData: true });
    expect(hiddenData).toBe(3);
    expect(rows.map(row => (row.guard ? `wenn:${row.dataCount}` : row.label))).toEqual(['MAIN', 'wenn:2', 'A']);
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
