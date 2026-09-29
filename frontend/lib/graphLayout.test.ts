import { describe, expect, it } from 'vitest';
import {
  ARROW_LENGTH,
  ARROW_MAX_EDGE_FRACTION,
  ARROW_MIN_SCREEN_PX,
  arrowLength,
  edgeLineWidth,
  ARROW_LENGTH_SELECTED,
  CHARGE_DISTANCE_MAX,
  GRAPH_COOLDOWN_MS,
  NEIGHBORHOOD_LAYER_GAP,
  NEIGHBORHOOD_ROW_GAP,
  chargeStrength,
  collisionRadius,
  linkDistance,
  radialRadius,
} from './graphLayout';

describe('graph layout parameters', () => {
  it('draws clearly visible arrowheads, larger for the selected edge (previously 4 / 6.5 px)', () => {
    expect(ARROW_LENGTH).toBeGreaterThanOrEqual(10);
    expect(ARROW_LENGTH_SELECTED).toBeGreaterThan(ARROW_LENGTH);
  });

  it('spreads nodes further apart than the previous layout at every degree', () => {
    // Vorherige Formeln: Link 100+min(260,e*24), Abstoßung -min(1000,120+n*1.8)-min(500,d*18),
    // Radialring 130+min(770,sqrt(d)*75), Kollisionsrand 24+sqrt(d)*4.
    for (const degree of [0, 1, 4, 16, 100]) {
      const previousLink = 100 + Math.min(260, (Math.sqrt(degree) * 2) * 24);
      expect(linkDistance(degree, degree)).toBeGreaterThan(previousLink * 1.4);
      expect(radialRadius(degree)).toBeGreaterThan(130 + Math.min(770, Math.sqrt(degree) * 75));
      expect(collisionRadius(8, degree)).toBeGreaterThan(8 + 24 + Math.sqrt(degree) * 4);
    }
    for (const nodeCount of [10, 200, 2000]) {
      const previous = -Math.min(1000, 120 + nodeCount * 1.8) - Math.min(500, 4 * 18);
      expect(chargeStrength(nodeCount, 4)).toBeLessThan(previous * 1.5);
    }
  });

  it('keeps repulsion, radial ring and link distance bounded on huge graphs', () => {
    expect(chargeStrength(1_000_000, 10_000)).toBe(-1700 - 850);
    expect(radialRadius(1_000_000)).toBe(220 + 1300);
    expect(linkDistance(1_000_000, 1_000_000)).toBe(170 + 440);
  });

  it('gives a lone node no extra spacing beyond the base values', () => {
    expect(linkDistance(0, 0)).toBe(170);
    expect(radialRadius(0)).toBe(220);
    expect(collisionRadius(8, 0)).toBe(48);
  });

  it('reaches further with repulsion and needs a longer simulation to settle', () => {
    expect(CHARGE_DISTANCE_MAX).toBeGreaterThan(1800);
    expect(GRAPH_COOLDOWN_MS).toBeGreaterThan(3000);
  });

  it('spaces the fixed neighborhood layers and rows wider than before (130 / 70)', () => {
    expect(NEIGHBORHOOD_LAYER_GAP).toBeGreaterThan(130);
    expect(NEIGHBORHOOD_ROW_GAP).toBeGreaterThan(70);
  });
});

describe('arrow length', () => {
  const at = (zoom: number, options: { selected?: boolean; score?: number | null; exposedLength?: number | null } = {}) => {
    const selected = options.selected ?? false;
    return arrowLength({ selected, lineWidth: edgeLineWidth(selected, options.score ?? null), zoom, exposedLength: options.exposedLength ?? null });
  };

  it('stands in a fair ratio to the edge: thicker (higher scored) edges get larger arrowheads', () => {
    expect(at(1, { score: 0.5 })).toBe(ARROW_MIN_SCREEN_PX); // Linienbreite 1,5 -> 9 < Mindestmaß auf dem Bildschirm (14)
    expect(at(1, { score: 0.5 })).toBeGreaterThanOrEqual(ARROW_LENGTH);
    expect(at(1, { score: 1 })).toBeGreaterThan(at(1, { score: 0.5 }));
    expect(at(1, { score: 1 })).toBe(edgeLineWidth(false, 1) * 6);
    expect(at(1, { selected: true })).toBe(edgeLineWidth(true, null) * 6); // 4,5 * 6 = 27
  });

  it('keeps the arrow at least ARROW_MIN_SCREEN_PX long on screen when zoomed far out', () => {
    for (const zoom of [0.5, 0.3, 0.2, 0.1, 0.05]) {
      expect(at(zoom) * zoom).toBeGreaterThanOrEqual(ARROW_MIN_SCREEN_PX - 1e-9);
    }
  });

  it('grows monotonically while zooming out and stays finite at extreme zoom levels', () => {
    const lengths = [1, 0.6, 0.3, 0.15, 0.08].map((zoom) => at(zoom));
    expect([...lengths].sort((a, b) => a - b)).toEqual(lengths);
    expect(Number.isFinite(at(0))).toBe(true);
    expect(at(0)).toBeLessThanOrEqual(ARROW_MIN_SCREEN_PX / 0.02);
  });

  it('makes the selected edge arrow larger than an ordinary one at every zoom', () => {
    for (const zoom of [1, 0.3, 0.1]) {
      expect(at(zoom, { selected: true })).toBeGreaterThan(at(zoom));
    }
  });

  it('never lets an arrow cover more than its share of a short visible edge', () => {
    expect(at(0.1, { exposedLength: 100 })).toBeCloseTo(100 * ARROW_MAX_EDGE_FRACTION, 6);
    expect(at(1, { exposedLength: 30 })).toBeLessThanOrEqual(30 * ARROW_MAX_EDGE_FRACTION);
    // Unbekannte Länge: kein Deckel
    expect(at(0.1, { exposedLength: null })).toBeGreaterThan(100);
  });
});
