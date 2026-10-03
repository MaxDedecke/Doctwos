import { describe, expect, it } from 'vitest';
import { buildFlowPaths, flowView, nextFlowCursor, type FlowLink } from './processFlowPaths';

const link = (id: string, source: string, target: string, sequence?: number): FlowLink => ({ id, source, target, sequence });

describe('buildFlowPaths', () => {
  it('liefert je Verzweigung einen Pfad von der Wurzel bis zum Ausgang, in Ablaufreihenfolge', () => {
    const { paths, truncated } = buildFlowPaths([
      link('b', 'root', 'x', 2), link('a', 'root', 'y', 1), link('c', 'y', 'z', 1), link('d', 'x', 'z', 1),
    ], 'root');
    expect(paths).toEqual([['a', 'c'], ['b', 'd']]);
    expect(truncated).toBe(false);
  });

  it('zeigt bei einem Zyklus genau eine Runde samt schließender Kante', () => {
    const { paths } = buildFlowPaths([link('1', 'r', 'a'), link('2', 'a', 'b'), link('3', 'b', 'a')], 'r');
    expect(paths).toEqual([['1', '2', '3']]);
  });

  it('ignoriert Selbstschleifen und liefert ohne Ausgang keinen Pfad', () => {
    expect(buildFlowPaths([link('1', 'r', 'r')], 'r').paths).toEqual([]);
    expect(buildFlowPaths([link('1', 'a', 'b')], 'r').paths).toEqual([]);
  });

  it('begrenzt Tiefe, Pfadanzahl und Suchaufwand und meldet die Kürzung', () => {
    const chain = Array.from({ length: 30 }, (_, i) => link(`e${i}`, `n${i}`, `n${i + 1}`));
    const deep = buildFlowPaths(chain, 'n0', { maxDepth: 5 });
    expect(deep.paths[0]).toHaveLength(5);
    expect(deep.truncated).toBe(true);

    const wide = Array.from({ length: 40 }, (_, i) => link(`w${i}`, 'root', `leaf${i}`));
    const many = buildFlowPaths(wide, 'root', { maxPaths: 6 });
    expect(many.paths).toHaveLength(6);
    expect(many.truncated).toBe(true);

    expect(buildFlowPaths(wide, 'root', { maxExpansions: 3 }).truncated).toBe(true);
  });
});

describe('nextFlowCursor', () => {
  const paths = [['a', 'b'], ['c']];

  it('läuft Kante für Kante, hält am Ende einen Takt und beginnt mit dem nächsten Pfad, endlos', () => {
    let cursor = { path: 0, step: 0 };
    const seen: Array<[number, number]> = [];
    for (let i = 0; i < 8; i += 1) {
      cursor = nextFlowCursor(paths, cursor, null);
      seen.push([cursor.path, cursor.step]);
    }
    expect(seen).toEqual([[0, 1], [0, 2], [1, 0], [1, 1], [0, 0], [0, 1], [0, 2], [1, 0]]);
  });

  it('bleibt bei einem festen Pfad und wiederholt ihn', () => {
    let cursor = { path: 1, step: 0 };
    const seen: number[] = [];
    for (let i = 0; i < 4; i += 1) {
      cursor = nextFlowCursor(paths, cursor, 0);
      seen.push(cursor.path * 10 + cursor.step);
    }
    expect(seen).toEqual([1, 2, 0, 1]);
  });

  it('bleibt ohne Pfade ruhig', () => {
    expect(nextFlowCursor([], { path: 3, step: 2 }, null)).toEqual({ path: 0, step: 0 });
  });
});

describe('flowView', () => {
  const endpoints = new Map([['a', { source: 'r', target: 'x' }], ['b', { source: 'x', target: 'y' }]]);

  it('markiert die aktive Kante, die bisherige Spur und den aktiven Knoten', () => {
    const view = flowView([['a', 'b']], { path: 0, step: 2 }, endpoints, 'r');
    expect(view.activeEdgeId).toBe('b');
    expect([...view.trailEdgeIds]).toEqual(['a', 'b']);
    expect(view.activeNodeId).toBe('y');
    expect([...view.trailNodeIds].sort()).toEqual(['r', 'x', 'y']);
  });

  it('beginnt an der Wurzel, solange noch keine Kante gezeigt wird', () => {
    const view = flowView([['a', 'b']], { path: 0, step: 0 }, endpoints, 'r');
    expect(view.activeEdgeId).toBeNull();
    expect(view.activeNodeId).toBe('r');
  });
});
