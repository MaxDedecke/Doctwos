import { describe, expect, it } from 'vitest';
import { layoutZones } from './processZones';

const node = (id: string, type: string) => ({ id, type });

describe('layoutZones', () => {
  it('sperrt Knoten gleichen Typs in ein gemeinsames Rechteck', () => {
    const nodes = [node('a', 'call'), node('b', 'call'), node('c', 'external_call')];
    const { zones, positions } = layoutZones(nodes, [], 1.5);
    expect(zones.map(z => [z.type, z.count])).toEqual([['call', 2], ['external_call', 1]]);
    for (const n of nodes) {
      const zone = zones.find(z => z.type === n.type)!;
      const p = positions.get(n.id)!;
      expect(p.x).toBeGreaterThan(zone.x);
      expect(p.x).toBeLessThan(zone.x + zone.w);
      expect(p.y).toBeGreaterThan(zone.y);
      expect(p.y).toBeLessThan(zone.y + zone.h);
    }
  });

  it('ordnet Zonen in Ablaufreihenfolge, unbekannte Typen zuletzt', () => {
    const nodes = [node('x', 'weird'), node('e', 'external_call'), node('s', 'entry'), node('b', 'branch')];
    expect(layoutZones(nodes, [], 4).zones.map(z => z.type)).toEqual(['entry', 'branch', 'external_call', 'weird']);
  });

  it('sortiert Knoten innerhalb der Zone nach Ablaufnummer', () => {
    const nodes = [node('late', 'call'), node('early', 'call')];
    const edges = [
      { source: 'r', target: 'late', sequence: 7 },
      { source: 'r', target: 'early', sequence: 2 },
    ];
    const { positions, order } = layoutZones(nodes, edges, 2);
    expect(order.get('early')).toBe(2);
    expect(positions.get('early')!.x).toBeLessThan(positions.get('late')!.x);
  });

  it('überlappt keine Zonen und bricht bei schmaler Ansicht in Zeilen um', () => {
    const nodes = ['entry', 'step', 'branch', 'call', 'external_call'].map(t => node(t, t));
    const { zones } = layoutZones(nodes, [], 0.4);
    for (let i = 0; i < zones.length; i++) for (let j = i + 1; j < zones.length; j++) {
      const a = zones[i], b = zones[j];
      const overlap = a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
      expect(overlap).toBe(false);
    }
    expect(new Set(zones.map(z => z.y)).size).toBeGreaterThan(1);
  });

  it('liefert für leere Eingabe ein leeres Layout', () => {
    expect(layoutZones([], [], 1).zones).toEqual([]);
  });
});
