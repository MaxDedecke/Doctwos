import { describe, expect, it } from 'vitest';
import {
  ARROW_LENGTH,
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
